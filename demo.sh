#!/usr/bin/env bash
# Live demo runner. Cuts through the Spark output noise.
# Usage: bash demo.sh
set -e
cd "$(dirname "$0")"

echo ""
echo "=================================================================="
echo "Lore Case Study: Contract-Driven Pipeline Modernization"
echo "=================================================================="
echo ""
echo "Step 1/4: Generating synthetic engagement events..."
python src/generate_sample_data.py 2>&1 | tail -4

echo ""
echo "Step 2/4: Running engagement_events contract (Bronze -> Silver)..."
python src/run_pipeline.py --contract configs/engagement_events.yaml 2>&1 \
  | grep -E "^\[|^Running|^==" | head -20

echo ""
echo "Step 3/4: Running partner_dashboard contract (Silver -> Gold)..."
python src/run_pipeline.py --contract configs/partner_dashboard.yaml 2>&1 \
  | grep -E "^\[|^Running|^==" | head -10

echo ""
echo "Step 4/4: Querying the lakehouse..."
python src/query_results.py 2>&1 \
  | grep -v -E "^[0-9]{2}/[0-9]{2}|WARN|INFO|Stage |Setting default|Using Spark|^\s*$" \
  | head -200

echo ""
echo "=================================================================="
echo "Demo complete."
echo "=================================================================="
echo ""
echo "Next: launch the partner dashboard (interactive, blocks the terminal):"
echo "  streamlit run src/dashboard.py"
echo ""
