"""
Shared pytest fixtures. The SparkSession is session-scoped because Spark
startup is ~10s and we don't want to pay that per test.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# Make src/ importable without packaging it.
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))


@pytest.fixture(scope="session")
def spark():
    from pyspark.sql import SparkSession
    s = (SparkSession.builder
         .appName("lore-tests")
         .master("local[2]")
         .config("spark.sql.shuffle.partitions", "2")
         .config("spark.ui.enabled", "false")
         .getOrCreate())
    s.sparkContext.setLogLevel("ERROR")
    yield s
    s.stop()


@pytest.fixture
def now():
    return datetime.now(timezone.utc).replace(microsecond=0)


@pytest.fixture
def sample_events(spark, now):
    """A tiny in-memory engagement_events frame with intentional dirt:
    - one duplicate event_id (different ingest_timestamp)
    - one late event (>7 days old)
    - all other rows are clean.
    """
    rows = [
        # (event_id, user_id, partner_id, event_type, event_ts, ingest_ts, session_id)
        ("e1", "user_001", "acme-corp", "session_start",
         now, now, "s1"),
        ("e2", "user_001", "acme-corp", "exercise_complete",
         now, now, "s1"),
        ("e3", "user_002", "globex", "session_start",
         now - timedelta(hours=1), now, "s2"),
        # Duplicate of e1 with later ingest_timestamp — dedup should keep this one.
        ("e1", "user_001", "acme-corp", "session_start",
         now, now + timedelta(seconds=30), "s1"),
        # Late event — should be filtered to quarantine.
        ("e4", "user_003", "initech", "session_end",
         now - timedelta(days=10), now, "s3"),
    ]
    cols = ["event_id", "user_id", "partner_id", "event_type",
            "event_timestamp", "ingest_timestamp", "session_id"]
    return spark.createDataFrame(rows, cols)
