"""
Contract-driven Spark pipeline framework.

Reads a YAML data contract and executes Bronze -> Silver -> Gold for that
data product. The same engine runs all three contracts in this repo.

This is the structural pattern behind NLPLyft (Wells Fargo) and the
Informatica metadata-driven onboarding framework: the pipeline is metadata,
not code. New data products = new YAML. Squads ship data products without
filing a ticket with the platform team.

Usage:
    python src/run_pipeline.py --contract configs/engagement_events.yaml
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import os
import yaml
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F
from pyspark.sql.window import Window


# In production this is Delta on Databricks. The framework abstracts the
# storage format via the contract, so the demo runs on plain Parquet without
# needing Delta JARs on the local classpath. Set LORE_STORAGE_FORMAT=delta
# (with Delta JARs on the classpath) to flip back.
STORAGE_FORMAT = os.environ.get("LORE_STORAGE_FORMAT", "parquet")


# ---------------------------------------------------------------------------
# Spark bootstrap
# ---------------------------------------------------------------------------
def get_spark() -> SparkSession:
    builder = (
        SparkSession.builder
        .appName("lore-contract-pipeline")
        .master("local[*]")
        .config("spark.sql.shuffle.partitions", "4")
        .config("spark.driver.memory", "2g")
    )
    if STORAGE_FORMAT == "delta":
        builder = (builder
                   .config("spark.sql.extensions",
                           "io.delta.sql.DeltaSparkSessionExtension")
                   .config("spark.sql.catalog.spark_catalog",
                           "org.apache.spark.sql.delta.catalog.DeltaCatalog"))
    return builder.getOrCreate()


# ---------------------------------------------------------------------------
# Contract loading
# ---------------------------------------------------------------------------
def load_contract(path: str) -> dict:
    with open(path) as f:
        contract = yaml.safe_load(f)
    # Minimal validation; in prod this is a JSON Schema check in CI.
    assert "contract" in contract, "Missing 'contract' top-level key"
    assert "schema" in contract, "Missing 'schema' definition"
    return contract


# ---------------------------------------------------------------------------
# Bronze: raw landing
# ---------------------------------------------------------------------------
def ingest_bronze(spark: SparkSession, contract: dict, repo_root: Path) -> DataFrame:
    """
    In production, Bronze is fed by Kafka -> Structured Streaming.
    For the demo we read JSONL produced by generate_sample_data.py.
    """
    source = contract["source"]
    name = contract["contract"]["name"]

    if source["type"] == "kafka":
        # Demo: read from local JSONL that stands in for the Kafka topic
        raw_path = repo_root / "data" / "raw" / f"{name}.jsonl"
        if not raw_path.exists():
            raise FileNotFoundError(
                f"Demo data not found at {raw_path}. "
                "Run: python src/generate_sample_data.py"
            )
        df = (spark.read.json(str(raw_path))
              .withColumn("event_timestamp", F.to_timestamp("event_timestamp"))
              .withColumn("ingest_timestamp", F.to_timestamp("ingest_timestamp"))
              .withColumn("ingest_date", F.to_date("ingest_timestamp")))

    elif source["type"] == "delta_table":
        # Derived products read from another contract's silver/gold
        table_path = repo_root / "data" / "lakehouse" / source["table"].replace(".", "/")
        df = spark.read.format(STORAGE_FORMAT).load(str(table_path))

    else:
        raise NotImplementedError(f"Source type: {source['type']}")

    bronze_path = repo_root / "data" / "lakehouse" / "bronze" / name
    df.write.format(STORAGE_FORMAT).mode("overwrite").save(str(bronze_path))
    print(f"[bronze] wrote {df.count()} rows -> {bronze_path}")
    return df


# ---------------------------------------------------------------------------
# Silver: apply contract transformations
# ---------------------------------------------------------------------------
def apply_transformations(
    df: DataFrame,
    contract: dict,
    spark: SparkSession,
    repo_root: Path = None,
) -> DataFrame:
    """Walk the transformations list in the contract and apply each step.

    If ``repo_root`` is provided, filter steps with
    ``on_violation: route_to_quarantine`` persist rejected rows to
    ``data/lakehouse/quarantine/<contract_name>/<step_name>/`` so the owning
    squad can reconcile rather than silently dropping them.
    """
    out = df
    contract_name = contract["contract"]["name"]
    for step in contract.get("transformations", []):
        stype = step["type"]
        name = step["name"]

        if stype == "deduplicate":
            keys = step["keys"]
            order_col = step.get("keep", {}).get("latest_by") or "ingest_timestamp"
            w = Window.partitionBy(*keys).orderBy(F.col(order_col).desc())
            out = (out.withColumn("__rn", F.row_number().over(w))
                   .filter(F.col("__rn") == 1).drop("__rn"))
            print(f"[transform:{name}] dedup on {keys}")

        elif stype == "filter":
            quarantine = out.filter(f"NOT ({step['expr']})")
            kept = out.filter(step["expr"])
            q_count = quarantine.count()

            if q_count > 0 and step.get("on_violation") == "route_to_quarantine" \
               and repo_root is not None:
                qpath = (repo_root / "data" / "lakehouse" / "quarantine"
                         / contract_name / name)
                (quarantine
                 .withColumn("__quarantine_reason", F.lit(name))
                 .withColumn("__quarantine_at", F.current_timestamp())
                 .write.format(STORAGE_FORMAT).mode("overwrite").save(str(qpath)))
                print(f"[transform:{name}] filtered {q_count} rows -> quarantine at {qpath}")
            else:
                print(f"[transform:{name}] filtered {q_count} rows (no quarantine sink)")
            out = kept

        elif stype == "hash":
            col = step["column"]
            salt = "demo-salt-not-for-prod"   # real impl: pull from secrets manager
            # Pseudonymize: hash(salt || value). Same input -> same output (join-safe).
            out = out.withColumn(
                f"{col}_pseudo",
                F.sha2(F.concat(F.lit(salt), F.col(col)), 256)
            ).drop(col).withColumnRenamed(f"{col}_pseudo", col)
            print(f"[transform:{name}] pseudonymized {col}")

        elif stype == "sql":
            out.createOrReplaceTempView("__input")
            sql = step["sql"].replace("silver.engagement_events", "__input")
            out = spark.sql(sql)
            print(f"[transform:{name}] applied SQL transform")

        elif stype == "merge":
            # Demo: write as overwrite. Production: DeltaTable.merge(...).
            pass

        else:
            print(f"[transform:{name}] WARN: unhandled type {stype}")

    return out


# ---------------------------------------------------------------------------
# Lineage: emit a JSON sidecar per run
# ---------------------------------------------------------------------------
def emit_lineage(contract: dict, repo_root: Path, run_metadata: dict) -> Path:
    """
    Write a lineage record next to the silver/gold output.

    In production this is what feeds Unity Catalog / OpenLineage / Atlas.
    Locally it's a JSON file you can open to answer "where did this number
    come from?" — the 30-min-to-root-cause promise in REQUIREMENTS.md.
    """
    name = contract["contract"]["name"]
    lineage_dir = repo_root / "data" / "lakehouse" / "_lineage" / name
    lineage_dir.mkdir(parents=True, exist_ok=True)
    ts = run_metadata["run_finished_at"].replace(":", "").replace("-", "")
    path = lineage_dir / f"run_{ts}.json"

    record = {
        "contract": {
            "name": name,
            "version": contract["contract"]["version"],
            "owner_squad": contract["contract"].get("owner_squad"),
        },
        "source": contract.get("source", {}),
        "transformations": [
            {"name": s["name"], "type": s["type"]}
            for s in contract.get("transformations", [])
        ],
        "outputs": {
            tier: {
                "path": str(repo_root / "data" / "lakehouse" / tier / name),
                "format": STORAGE_FORMAT,
                "partition_by": contract["storage"].get(tier, {}).get("partition_by", []),
            }
            for tier in ("bronze", "silver", "gold")
            if contract["storage"].get(tier, {}).get("enabled") is not False
            and tier in contract["storage"]
        },
        **run_metadata,
    }
    with path.open("w") as f:
        json.dump(record, f, indent=2, default=str)
    print(f"[lineage] wrote {path.name}")
    return path


# ---------------------------------------------------------------------------
# Schema enforcement: the contract IS the API
# ---------------------------------------------------------------------------
def enforce_schema(df: DataFrame, contract: dict) -> list:
    """
    Validate the post-transformation DataFrame against the contract schema.

    Checks (cheap, runtime-safe):
      - Every required (nullable: false) column is present.
      - allowed_values constraints are honored (no row outside the set).
    Type validation is deliberately skipped — PySpark dtype names don't map
    cleanly to the contract's portable type strings (e.g. array<struct<...>>),
    and we want this check to be a friendly first line of defense, not a
    type-system reimplementation.

    Returns a list of human-readable violations. Empty list = pass.
    """
    violations = []
    df_cols = set(df.columns)

    for field in contract.get("schema", []):
        name = field["name"]
        if name not in df_cols:
            if not field.get("nullable", True):
                violations.append(f"schema.{name}: required column missing from output")
            continue

        allowed = field.get("allowed_values")
        if allowed:
            bad = df.filter(F.col(name).isNotNull() & ~F.col(name).isin(*allowed)).count()
            if bad > 0:
                violations.append(
                    f"schema.{name}: {bad} rows with value not in allowed_values={allowed}"
                )

    return violations


# ---------------------------------------------------------------------------
# Quality: gate the silver/gold write
# ---------------------------------------------------------------------------
def run_quality_checks(df: DataFrame, contract: dict) -> list:
    """Returns list of violations. Empty list = pass."""
    violations = []
    q = contract.get("quality", {})

    for check in q.get("completeness", []):
        col = check["column"]
        if check["check"] == "not_null":
            actual = df.filter(F.col(col).isNotNull()).count() / max(df.count(), 1)
            if actual < check["threshold"]:
                violations.append(
                    f"completeness.{col}: actual={actual:.4f} "
                    f"< threshold={check['threshold']}"
                )

    for check in q.get("uniqueness", []):
        cols = check["columns"]
        total = df.count()
        distinct = df.select(*cols).distinct().count()
        if total > 0 and distinct / total < check["threshold"]:
            violations.append(
                f"uniqueness.{cols}: distinct/total={distinct/total:.4f} "
                f"< threshold={check['threshold']}"
            )

    return violations


# ---------------------------------------------------------------------------
# Silver write
# ---------------------------------------------------------------------------
def write_silver(df: DataFrame, contract: dict, repo_root: Path):
    storage = contract["storage"].get("silver", {})
    if not storage or storage.get("enabled") is False:
        return None
    name = contract["contract"]["name"]
    path = repo_root / "data" / "lakehouse" / "silver" / name
    partition_cols = storage.get("partition_by", [])
    # Derive event_date if partitioning on it
    if "event_date" in partition_cols and "event_date" not in df.columns:
        df = df.withColumn("event_date", F.to_date("event_timestamp"))
    writer = df.write.format(STORAGE_FORMAT).mode("overwrite")
    if partition_cols:
        writer = writer.partitionBy(*partition_cols)
    writer.save(str(path))
    print(f"[silver] wrote {df.count()} rows -> {path} partitioned by {partition_cols}")
    return path


# ---------------------------------------------------------------------------
# Gold write (for derived products)
# ---------------------------------------------------------------------------
def write_gold(df: DataFrame, contract: dict, repo_root: Path):
    storage = contract["storage"].get("gold", {})
    if not storage or storage.get("enabled") is False:
        return None
    name = contract["contract"]["name"]
    path = repo_root / "data" / "lakehouse" / "gold" / name
    partition_cols = storage.get("partition_by", [])
    writer = df.write.format(STORAGE_FORMAT).mode("overwrite")
    if partition_cols:
        writer = writer.partitionBy(*partition_cols)
    writer.save(str(path))
    print(f"[gold]   wrote {df.count()} rows -> {path}")
    return path


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def run(contract_path: str):
    repo_root = Path(__file__).parent.parent
    contract = load_contract(contract_path)
    name = contract["contract"]["name"]
    print(f"\n{'=' * 60}\nRunning contract: {name} v{contract['contract']['version']}\n{'=' * 60}")

    run_started_at = datetime.now(timezone.utc)

    spark = get_spark()
    spark.sparkContext.setLogLevel("ERROR")

    # Bronze
    bronze_df = ingest_bronze(spark, contract, repo_root)
    bronze_count = bronze_df.count()

    # Silver (if applicable)
    silver_df = apply_transformations(bronze_df, contract, spark, repo_root=repo_root)

    # Schema enforcement (contract-as-API) — runs before quality checks because
    # a structural failure makes downstream checks ambiguous.
    schema_violations = enforce_schema(silver_df, contract)
    if schema_violations:
        print("\n[schema] VIOLATIONS:")
        for v in schema_violations:
            print(f"  - {v}")
        print("[schema] blocking write — contract schema is the API.")
        spark.stop()
        sys.exit(2)
    print("[schema] contract schema honored.")

    # Quality gate
    violations = run_quality_checks(silver_df, contract)
    if violations:
        print("\n[quality] VIOLATIONS:")
        for v in violations:
            print(f"  - {v}")
        on_failure = contract.get("quality", {}).get("on_failure", "warn")
        if on_failure == "block_silver_write":
            print("[quality] blocking write per contract.")
            spark.stop()
            sys.exit(1)
    else:
        print("[quality] all checks passed.")

    # Write
    output_count = silver_df.count()
    if contract["storage"].get("silver", {}).get("enabled") is not False:
        write_silver(silver_df, contract, repo_root)
    if contract["storage"].get("gold", {}).get("enabled") is not False \
       and "gold" in contract["storage"]:
        write_gold(silver_df, contract, repo_root)

    # Lineage sidecar
    run_finished_at = datetime.now(timezone.utc)
    emit_lineage(contract, repo_root, {
        "run_started_at": run_started_at.isoformat(),
        "run_finished_at": run_finished_at.isoformat(),
        "duration_seconds": (run_finished_at - run_started_at).total_seconds(),
        "row_counts": {
            "bronze": bronze_count,
            "output": output_count,
            "dropped_or_quarantined": bronze_count - output_count,
        },
        "quality_violations": violations,
    })

    print(f"[done] {name}\n")
    spark.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True, help="Path to YAML contract")
    args = parser.parse_args()
    run(args.contract)
