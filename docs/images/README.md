# Screenshots for the case study artifact

Save screenshots here as PNG/JPG; both the README and [scripts/build_case_study.py](../../scripts/build_case_study.py) embed them by relative path.

## What to capture

| Filename | What it shows | How to capture |
|---|---|---|
| `dashboard_overview.png` | The Streamlit partner dashboard, all-partner view, with KPI cards + DAU chart visible | After `bash demo.sh`, run `streamlit run src/dashboard.py`. Browser at http://localhost:8501. Cmd+Shift+4 (macOS) for a region screenshot. |
| `dashboard_filtered.png` | Same dashboard filtered to a single partner (e.g. "acme-corp") and a narrow date range | Same as above, after clicking the sidebar filters. |
| `rollup_table.png` | The partner_dashboard rollup table at the bottom of the Streamlit view | Scroll to the bottom; capture the table. |
| `terminal_demo.png` | A clean terminal showing the tail end of `bash demo.sh` — the rollup table from query_results.py | After running `bash demo.sh`, region-capture the last ~30 lines. |
| `lineage_json.png` *(optional)* | A snippet of `data/lakehouse/_lineage/engagement_events/run_*.json` open in VSCode | Use VSCode's JSON formatting; capture ~20 lines. |

## Resolution & file size

- Aim for 1600–2000px wide; the case_study.html scales them to fit the page.
- Keep each under ~500 KB so the assembled artifact stays email-friendly.
- PNG is fine; JPG is fine; SVG is overkill.

## After you save them

Re-run the build:

```bash
python scripts/build_case_study.py
```

The script doesn't currently auto-embed these — to weave a screenshot into the artifact, either:

1. Reference them inline in the relevant markdown doc (e.g. add `![Dashboard](images/dashboard_overview.png)` near the Streamlit section in README.md), or
2. Embed them in the README under a new `## Screenshots` section.

The HTML generator picks them up automatically because it converts the markdown images.
