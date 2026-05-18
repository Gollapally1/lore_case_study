"""
Partner-facing dashboard for the gold.partner_dashboard data product.

Reads the partitioned parquet table written by run_pipeline.py and renders
the per-partner daily metrics that the partner_dashboard contract promises:
DAU, sessions, engagement minutes, exercise completions, new sign-ups.

Run with:  streamlit run src/dashboard.py
"""
import os
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

STORAGE_FORMAT = os.environ.get("LORE_STORAGE_FORMAT", "parquet")
GOLD_PATH = Path(__file__).parent.parent / "data" / "lakehouse" / "gold" / "partner_dashboard"


@st.cache_data(show_spinner="Loading partner_dashboard from Gold...")
def load_gold() -> pd.DataFrame:
    if STORAGE_FORMAT != "parquet":
        st.error(
            f"Dashboard currently supports LORE_STORAGE_FORMAT=parquet "
            f"(got '{STORAGE_FORMAT}'). For Delta, install the `deltalake` "
            f"package and adapt this loader."
        )
        st.stop()
    if not GOLD_PATH.exists():
        st.error(
            f"Gold table not found at {GOLD_PATH}. "
            f"Run `bash demo.sh` first to populate the lakehouse."
        )
        st.stop()
    df = pd.read_parquet(GOLD_PATH)
    df["metric_date"] = pd.to_datetime(df["metric_date"]).dt.date
    return df


def filter_panel(df: pd.DataFrame) -> pd.DataFrame:
    partners = sorted(df["partner_id"].unique().tolist())
    selected_partners = st.sidebar.multiselect(
        "Partner", partners, default=partners,
        help="Employer partners contractually receiving these metrics.",
    )

    min_d, max_d = df["metric_date"].min(), df["metric_date"].max()
    date_range = st.sidebar.date_input(
        "Date range",
        value=(min_d, max_d),
        min_value=min_d,
        max_value=max_d,
    )
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_d, end_d = date_range
    else:
        start_d, end_d = min_d, max_d

    mask = (
        df["partner_id"].isin(selected_partners)
        & (df["metric_date"] >= start_d)
        & (df["metric_date"] <= end_d)
    )
    return df.loc[mask].copy()


def kpi_row(df: pd.DataFrame) -> None:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Avg DAU / partner-day", f"{df['dau'].mean():,.0f}" if len(df) else "—")
    c2.metric("Total sessions", f"{int(df['total_sessions'].sum()):,}")
    c3.metric("Engagement minutes", f"{df['total_engagement_min'].sum():,.0f}")
    c4.metric("Exercise completions", f"{int(df['exercise_completions'].sum()):,}")


def main() -> None:
    st.set_page_config(page_title="Lore — Partner Dashboard", layout="wide")
    st.title("Lore — Partner Dashboard")
    st.caption(
        "Source: `gold.partner_dashboard` (Tier-0, partner-facing). "
        "Contract: configs/partner_dashboard.yaml."
    )

    df = load_gold()
    last_refresh = pd.to_datetime(df["last_refreshed_at"]).max()
    st.caption(f"Last refreshed in Gold: **{last_refresh:%Y-%m-%d %H:%M:%S}**")

    st.sidebar.header("Filters")
    fdf = filter_panel(df)

    if fdf.empty:
        st.warning("No rows match the current filters.")
        return

    kpi_row(fdf)

    st.subheader("DAU over time")
    dau_pivot = (
        fdf.pivot_table(
            index="metric_date", columns="partner_id", values="dau", aggfunc="sum"
        )
        .sort_index()
    )
    st.line_chart(dau_pivot)

    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Engagement minutes by day")
        eng = (
            fdf.groupby("metric_date")["total_engagement_min"].sum().sort_index()
        )
        st.bar_chart(eng)
    with col_b:
        st.subheader("Exercise completions by partner")
        comp = (
            fdf.groupby("partner_id")["exercise_completions"].sum().sort_values(ascending=False)
        )
        st.bar_chart(comp)

    st.subheader("Per-partner daily rollup")
    display_cols = [
        "partner_id", "metric_date", "dau", "total_sessions",
        "total_engagement_min", "exercise_completions", "new_signups",
    ]
    st.dataframe(
        fdf[display_cols].sort_values(["metric_date", "partner_id"], ascending=[False, True]),
        use_container_width=True,
        hide_index=True,
    )


if __name__ == "__main__":
    main()
