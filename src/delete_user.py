"""
Right-to-deletion workflow for the Lore lakehouse.

GDPR Article 17 / CCPA / HIPAA-aligned posture: when a user requests
deletion, we must:

  1. Remove them from the PII vault (handled by the identity service, not
     this script — we only deal with derived/analytics data here).
  2. Compute their pseudonymized ID using the same salted-sha256 used at
     bronze -> silver, so we know which rows to target.
  3. Delete matching rows from silver, and from every gold table derived
     from silver. (In Delta this is a MERGE-with-delete; in this parquet
     prototype we rewrite the partition.)
  4. Emit a tombstone audit record so the deletion is itself a trackable,
     auditable event.

This is the script the "right-to-deletion tested workflow" goal in
REQUIREMENTS.md / MIGRATION_PLAN.md Q4 refers to. It is intentionally
narrow: deletion is a high-stakes, low-volume operation, so the code
optimizes for legibility and audit, not throughput.

Usage:
    python src/delete_user.py --user-id user_001
    python src/delete_user.py --user-id user_001 --dry-run
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from pyspark.sql import SparkSession, functions as F

STORAGE_FORMAT = os.environ.get("LORE_STORAGE_FORMAT", "parquet")

# Must match the salt used in the contract framework. In prod this is fetched
# from the same secrets path as run_pipeline.py (configured per contract).
SALT = "demo-salt-not-for-prod"


def get_spark() -> SparkSession:
    return (SparkSession.builder
            .appName("lore-delete-user")
            .master("local[*]")
            .config("spark.sql.shuffle.partitions", "4")
            .getOrCreate())


def pseudonymize(raw_user_id: str) -> str:
    """Same hash function the framework uses at silver write time."""
    return hashlib.sha256((SALT + raw_user_id).encode()).hexdigest()


def delete_from_path(spark, path: Path, pseudo_id: str, column: str,
                     dry_run: bool) -> int:
    """Delete rows where `column == pseudo_id` from a parquet table.

    Returns row count deleted. In Delta this would be a single MERGE; in
    parquet we read, filter, and overwrite. Both shapes are idempotent.
    """
    if not path.exists():
        return 0
    df = spark.read.format(STORAGE_FORMAT).load(str(path))
    if column not in df.columns:
        return 0
    before = df.count()
    keep = df.filter(F.col(column) != pseudo_id)
    after = keep.count()
    n = before - after
    if n == 0:
        return 0
    if not dry_run:
        # In prod: DeltaTable.forPath(spark, path).delete(F.col(column) == pseudo_id)
        # Local parquet: rewrite the table. Slow but correct.
        keep.write.format(STORAGE_FORMAT).mode("overwrite").save(str(path))
    return n


def write_tombstone(repo_root: Path, record: dict) -> Path:
    """Append an immutable audit record. In prod this is a Delta append-only
    table with strict access controls; here it's a JSONL log."""
    audit_dir = repo_root / "data" / "lakehouse" / "_audit" / "deletions"
    audit_dir.mkdir(parents=True, exist_ok=True)
    path = audit_dir / "tombstones.jsonl"
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", required=True,
                        help="Raw user_id (pre-pseudonymization). The script "
                             "will compute the silver-side hash and propagate.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be deleted, don't write.")
    args = parser.parse_args()

    repo_root = Path(__file__).parent.parent
    lh = repo_root / "data" / "lakehouse"
    pseudo = pseudonymize(args.user_id)

    print(f"\n{'=' * 60}")
    print(f"Right-to-deletion: {args.user_id}")
    print(f"  pseudonym (silver-side id): {pseudo}")
    print(f"  mode: {'DRY-RUN' if args.dry_run else 'EXECUTE'}")
    print(f"{'=' * 60}")

    spark = get_spark()
    spark.sparkContext.setLogLevel("ERROR")

    # Tables to scan. Each (path, column) pair is a derived data product
    # known to potentially carry the pseudonym.
    targets = [
        (lh / "silver" / "engagement_events", "user_id"),
        # Gold tables derived from silver. Add new tables here as new
        # contracts are onboarded.
        (lh / "gold" / "user_journey", "pseudonymized_user_id"),
    ]

    deleted = {}
    for path, col in targets:
        n = delete_from_path(spark, path, pseudo, col, args.dry_run)
        deleted[str(path.relative_to(repo_root))] = n
        marker = "WOULD DELETE" if args.dry_run else "deleted"
        print(f"  [{marker}] {n} rows from {path.relative_to(repo_root)} "
              f"(column={col})")

    total = sum(deleted.values())
    print(f"\nTotal: {total} rows {'would be' if args.dry_run else ''} deleted")

    # Tombstone audit record — written even on dry-run so the request itself
    # is logged.
    tombstone = {
        "event": "user_deletion_request",
        "raw_user_id_sha256": hashlib.sha256(args.user_id.encode()).hexdigest(),
        "silver_pseudonym": pseudo,
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "executed": not args.dry_run,
        "rows_deleted_by_table": deleted,
        "total_rows_deleted": total,
    }
    tpath = write_tombstone(repo_root, tombstone)
    print(f"\n[audit] tombstone appended -> {tpath.relative_to(repo_root)}")

    spark.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
