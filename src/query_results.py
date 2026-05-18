"""
Quick query script to demonstrate the lakehouse outputs after running the
pipelines. Use this to show the end-to-end story in the panel.
"""
import os
from pathlib import Path
from pyspark.sql import SparkSession

STORAGE_FORMAT = os.environ.get("LORE_STORAGE_FORMAT", "parquet")


def get_spark():
    builder = (
        SparkSession.builder
        .appName("lore-query-results")
        .master("local[*]")
        .config("spark.sql.shuffle.partitions", "4")
    )
    if STORAGE_FORMAT == "delta":
        builder = (builder
                   .config("spark.sql.extensions",
                           "io.delta.sql.DeltaSparkSessionExtension")
                   .config("spark.sql.catalog.spark_catalog",
                           "org.apache.spark.sql.delta.catalog.DeltaCatalog"))
    return builder.getOrCreate()


def main():
    repo = Path(__file__).parent.parent
    lh = repo / "data" / "lakehouse"
    spark = get_spark()
    spark.sparkContext.setLogLevel("ERROR")

    print("\n" + "=" * 70)
    print("SILVER: engagement_events (atomic, deduped, pseudonymized)")
    print("=" * 70)
    silver = spark.read.format(STORAGE_FORMAT).load(str(lh / "silver" / "engagement_events"))
    silver.printSchema()
    print(f"Row count: {silver.count()}")
    silver.show(5, truncate=60)

    # Verify pseudonymization — user_id should be a 64-char sha256
    print("Pseudonymization check (user_id should be sha256):")
    silver.select("user_id").distinct().show(3, truncate=False)

    # Demo a partner-dashboard-shaped aggregation directly from silver
    print("\n" + "=" * 70)
    print("DERIVED: per-partner daily rollup (what partner_dashboard.yaml produces)")
    print("=" * 70)
    silver.createOrReplaceTempView("engagement_events")
    rollup = spark.sql("""
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
        ORDER BY metric_date DESC, partner_id
    """)
    rollup.show(20, truncate=False)

    spark.stop()


if __name__ == "__main__":
    main()
