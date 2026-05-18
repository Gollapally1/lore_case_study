"""
Tests for partner_dashboard business invariants.

These are the contractual promises Lore makes to its employer partners.
If one of these fails, the partner sees a wrong number — that's a
trust-eroding event, not a normal bug.
"""
from datetime import datetime, timezone

from pyspark.sql import functions as F


def _build_silver(spark):
    """Minimal silver.engagement_events with two partners, one day."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    rows = [
        # acme-corp: user_001 has 1 session_start + 1 session_end (60s dur)
        ("a1", "user_001", "acme-corp", "session_start", now, "s1", {}),
        ("a2", "user_001", "acme-corp", "session_end", now, "s1",
         {"duration_seconds": "60"}),
        ("a3", "user_001", "acme-corp", "exercise_complete", now, "s1", {}),
        # globex: user_002, user_003 each have a session
        ("g1", "user_002", "globex", "session_start", now, "s2", {}),
        ("g2", "user_002", "globex", "session_end", now, "s2",
         {"duration_seconds": "300"}),
        ("g3", "user_003", "globex", "session_start", now, "s3", {}),
        ("g4", "user_003", "globex", "session_end", now, "s3",
         {"duration_seconds": "120"}),
    ]
    return spark.createDataFrame(
        rows, ["event_id", "user_id", "partner_id", "event_type",
               "event_timestamp", "session_id", "event_properties"],
    )


def _rollup(spark, silver):
    silver.createOrReplaceTempView("engagement_events")
    return spark.sql("""
        SELECT
          partner_id,
          DATE(event_timestamp) AS metric_date,
          COUNT(DISTINCT user_id) AS dau,
          COUNT(DISTINCT session_id) AS total_sessions,
          SUM(CASE WHEN event_type = 'session_end'
                   THEN CAST(event_properties['duration_seconds'] AS DOUBLE) / 60.0
                   ELSE 0 END) AS total_engagement_min,
          SUM(CASE WHEN event_type = 'exercise_complete' THEN 1 ELSE 0 END)
              AS exercise_completions
        FROM engagement_events
        GROUP BY partner_id, DATE(event_timestamp)
    """)


def test_dau_never_exceeds_total_sessions(spark):
    """Invariant from partner_dashboard.yaml: dau <= total_sessions per partner-day.

    A partner can never have more daily active users than sessions; if they
    do, our session-counting logic is broken. This is the canonical
    'partner sees a wrong number' guard.
    """
    rollup = _rollup(spark, _build_silver(spark))
    bad = rollup.filter(F.col("dau") > F.col("total_sessions")).count()
    assert bad == 0, f"{bad} partner-days violate dau <= total_sessions"


def test_engagement_minutes_reasonable(spark):
    """No partner-day can have more engagement-minutes than dau * 24 * 60."""
    rollup = _rollup(spark, _build_silver(spark))
    bad = rollup.filter(F.col("total_engagement_min") > F.col("dau") * 24 * 60).count()
    assert bad == 0


def test_rollup_shape_matches_contract(spark):
    """Rollup output columns match the partner_dashboard contract schema."""
    rollup = _rollup(spark, _build_silver(spark))
    expected = {"partner_id", "metric_date", "dau", "total_sessions",
                "total_engagement_min", "exercise_completions"}
    assert expected.issubset(set(rollup.columns))


def test_rollup_aggregates_correctly(spark):
    """Concrete sanity check: globex has 2 users, 2 sessions, 7 engagement min."""
    rollup = _rollup(spark, _build_silver(spark))
    globex = rollup.filter("partner_id = 'globex'").first()
    assert globex["dau"] == 2
    assert globex["total_sessions"] == 2
    # (300s + 120s) / 60 = 7.0 min
    assert abs(globex["total_engagement_min"] - 7.0) < 1e-9
