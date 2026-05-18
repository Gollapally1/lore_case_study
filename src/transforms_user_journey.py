"""
Custom PySpark transforms referenced by the user_journey contract.

The contract framework supports two transform types: declarative SQL for
simple aggregations, and pyspark_function for logic that doesn't translate
cleanly to SQL (sessionization, stage derivation, etc).

This keeps the contract YAML stable while still letting squads ship
real logic in code, owned in their own module.
"""
from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.window import Window


def sessionize_user_day(df: DataFrame) -> DataFrame:
    """
    Collapse engagement_events into one row per (user, day) with:
      - events array
      - session_count (30-min inactivity = new session)
      - total_engagement_min
    """
    w = Window.partitionBy("user_id").orderBy("event_timestamp")

    # Mark session boundaries: any gap > 30 minutes starts a new session
    df = df.withColumn("prev_ts", F.lag("event_timestamp").over(w))
    df = df.withColumn(
        "gap_seconds",
        F.coalesce(
            F.unix_timestamp("event_timestamp") - F.unix_timestamp("prev_ts"),
            F.lit(0),
        ),
    )
    df = df.withColumn("new_session_flag", (F.col("gap_seconds") > 1800).cast("int"))
    df = df.withColumn("derived_session_id", F.sum("new_session_flag").over(w))

    df = df.withColumn("journey_date", F.to_date("event_timestamp"))

    agg = (df.groupBy("user_id", "partner_id", "journey_date")
           .agg(
               F.collect_list(
                   F.struct(
                       F.col("event_type"),
                       F.col("event_timestamp").alias("ts"),
                       F.col("session_id"),
                   )
               ).alias("events"),
               F.countDistinct("derived_session_id").alias("session_count"),
               F.sum(
                   F.when(
                       F.col("event_type") == "session_end",
                       F.col("event_properties.duration_seconds").cast("double") / 60.0,
                   ).otherwise(F.lit(0))
               ).alias("total_engagement_min"),
           )
           .withColumnRenamed("user_id", "pseudonymized_user_id"))
    return agg


def derive_resilience_stage(df: DataFrame) -> DataFrame:
    """
    Clinical-team-owned rule. Maps engagement signals to a stage in the
    resilience-building journey. Conservative default; the clinical squad
    iterates on the thresholds in code review.
    """
    return df.withColumn(
        "derived_stage",
        F.when(F.col("session_count") == 0, "churned")
         .when(F.col("session_count") >= 5, "habitual")
         .when(F.col("session_count") >= 3, "engaged")
         .when(F.col("total_engagement_min") < 2, "lapsing")
         .otherwise("exploring"),
    )
