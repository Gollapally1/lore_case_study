"""
Tests for the contract-driven transformation steps in run_pipeline.

These run the actual functions (no mocks) so a regression in dedup,
filter, or hash logic shows up here before it ships.
"""
import re

import pytest


def test_dedup_keeps_latest_by_ingest_ts(spark, sample_events):
    from run_pipeline import apply_transformations

    contract = {
        "contract": {"name": "engagement_events"},
        "transformations": [
            {"name": "dedup", "type": "deduplicate",
             "keys": ["event_id"], "keep": {"latest_by": "ingest_timestamp"}},
        ],
    }
    out = apply_transformations(sample_events, contract, spark)
    # 5 input rows, 1 duplicate -> 4 unique event_ids
    assert out.count() == 4
    assert out.select("event_id").distinct().count() == 4

    # The duplicate (e1) should be the one with the later ingest_timestamp.
    e1 = out.filter("event_id = 'e1'").collect()
    assert len(e1) == 1
    first = sample_events.filter("event_id = 'e1'").orderBy("ingest_timestamp").collect()
    assert e1[0]["ingest_timestamp"] == first[-1]["ingest_timestamp"]


def test_filter_quarantines_late_events(spark, sample_events, tmp_path):
    from run_pipeline import apply_transformations

    contract = {
        "contract": {"name": "engagement_events"},
        "transformations": [
            {"name": "late_event_handling", "type": "filter",
             "expr": "event_timestamp >= current_timestamp() - INTERVAL 7 DAYS",
             "on_violation": "route_to_quarantine"},
        ],
    }
    out = apply_transformations(sample_events, contract, spark, repo_root=tmp_path)
    # e4 is >10 days old — filtered out.
    assert out.filter("event_id = 'e4'").count() == 0
    assert out.count() == sample_events.count() - 1

    # Quarantine sink was written.
    qpath = tmp_path / "data" / "lakehouse" / "quarantine" / "engagement_events" / "late_event_handling"
    assert qpath.exists(), "quarantine table should be persisted"
    q = spark.read.parquet(str(qpath))
    assert q.count() == 1
    assert q.first()["event_id"] == "e4"
    assert q.first()["__quarantine_reason"] == "late_event_handling"


def test_filter_without_repo_root_drops_silently(spark, sample_events):
    """Backward-compat: if no repo_root passed, filter still works without writing."""
    from run_pipeline import apply_transformations

    contract = {
        "contract": {"name": "engagement_events"},
        "transformations": [
            {"name": "drop_late", "type": "filter",
             "expr": "event_timestamp >= current_timestamp() - INTERVAL 7 DAYS",
             "on_violation": "route_to_quarantine"},
        ],
    }
    out = apply_transformations(sample_events, contract, spark)  # no repo_root
    assert out.count() == sample_events.count() - 1


def test_hash_produces_sha256(spark, sample_events):
    from run_pipeline import apply_transformations

    contract = {
        "contract": {"name": "engagement_events"},
        "transformations": [
            {"name": "pseudonymize", "type": "hash", "column": "user_id"},
        ],
    }
    out = apply_transformations(sample_events, contract, spark)
    # user_id column should now hold sha256 hex (64 chars, [0-9a-f]).
    hex64 = re.compile(r"^[0-9a-f]{64}$")
    sample = out.select("user_id").distinct().collect()
    assert len(sample) > 0
    for row in sample:
        assert hex64.match(row["user_id"]), f"not a sha256 hex: {row['user_id']}"


def test_hash_is_deterministic(spark, sample_events):
    """Same user_id -> same hash. Critical for join-safety across tables."""
    from run_pipeline import apply_transformations

    contract = {
        "contract": {"name": "engagement_events"},
        "transformations": [
            {"name": "pseudonymize", "type": "hash", "column": "user_id"},
        ],
    }
    out = apply_transformations(sample_events, contract, spark)
    # user_001 appears on 3 rows in sample_events (e1, e1-dup, e2) — should hash identically.
    hashes = {r["user_id"] for r in out.filter("event_id IN ('e1','e2')").collect()}
    assert len(hashes) == 1, f"user_001 hashed to multiple values: {hashes}"
