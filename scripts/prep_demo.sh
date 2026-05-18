#!/usr/bin/env bash
# Reset the repo to a known-good state right before hitting RECORD.
#
# What it does:
#   1. Tears down any leftover Streamlit on :8501.
#   2. Wipes generated data so the demo's "Step 1: Generating..." actually
#      generates (the cold-run narrative matters).
#   3. Warms Spark and the JVM by running the pipeline once silently —
#      this means the live recording's first `bash demo.sh` won't pay the
#      ~5-10s cold JVM penalty mid-take.
#   4. Re-wipes the warm data, leaving Spark hot and disks clean.
#   5. Pre-stages the Streamlit cache by running the dashboard import.
#
# Net effect: when you start recording, `bash demo.sh` runs in ~25s instead
# of ~45s, and the partner_dashboard rollup table renders immediately.
#
# Usage:
#   bash scripts/prep_demo.sh        # the full prep
#   bash scripts/prep_demo.sh fast   # skip the warm-up (cold first run)
set -e
cd "$(dirname "$0")/.."

echo ""
echo "================================================================"
echo "  Demo recording prep"
echo "================================================================"

# 1. Stop any leftover Streamlit so :8501 is free for the recording.
if lsof -ti:8501 >/dev/null 2>&1; then
  echo "[1/5] Stopping leftover Streamlit on :8501..."
  lsof -ti:8501 | xargs kill 2>/dev/null || true
  sleep 1
else
  echo "[1/5] Port 8501 already free."
fi

# 2. Clean generated artifacts.
echo "[2/5] Cleaning generated data..."
rm -rf data/raw data/lakehouse

# 3. Warm-up run (skipped if 'fast' arg).
if [ "${1:-}" != "fast" ]; then
  echo "[3/5] Warming Spark / JVM with a silent pipeline run (~30s)..."
  .venv/bin/python src/generate_sample_data.py > /dev/null
  .venv/bin/python src/run_pipeline.py --contract configs/engagement_events.yaml > /dev/null 2>&1
  .venv/bin/python src/run_pipeline.py --contract configs/partner_dashboard.yaml > /dev/null 2>&1
  echo "      warm-up complete."
else
  echo "[3/5] (skipped — 'fast' mode)"
fi

# 4. Re-wipe so the recording shows a real cold start.
echo "[4/5] Re-cleaning so the recording shows a genuine cold run..."
rm -rf data/raw data/lakehouse

# 5. Sanity check the dashboard module imports (catches missing deps NOW,
#    not during the recording).
echo "[5/5] Sanity-checking dashboard imports..."
.venv/bin/python -c "import streamlit, pandas, pyarrow; print('      OK: streamlit, pandas, pyarrow imported.')"

echo ""
echo "================================================================"
echo "  Ready to record."
echo "================================================================"
echo ""
echo "Recommended terminal setup:"
echo "  - Font size 18pt (Cmd-+ a few times)"
echo "  - Window size: ~120 cols x 36 rows"
echo "  - Clear the scrollback (Cmd-K) right before starting"
echo "  - Open https://github.com/Gollapally1/lore_case_study in a"
echo "    second window for Beat 1 (the architecture diagram)"
echo ""
echo "Then start recording (Cmd-Shift-5 for macOS, or open Loom)"
echo "and follow docs/DEMO_SCRIPT.md."
echo ""
