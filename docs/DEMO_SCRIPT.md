# Demo recording — shot list & narration

A 3–4 minute Loom walkthrough that an interviewer can watch before the panel. The goal is to land three beats: **the contract is the API**, **the framework is real (not a slide)**, and **the customer-facing data product is end-to-end.**

Tools: [Loom](https://www.loom.com) (free; produces a shareable URL) or QuickTime (Cmd+Shift+5 on macOS for screen + camera).

---

## Pre-recording checklist

- [ ] Terminal at a comfortable font size (16–18pt). Dark theme is fine.
- [ ] Browser tab on http://localhost:8501 closed (you'll open it on camera).
- [ ] Repo open in VSCode in a second window — useful for show-the-code moments.
- [ ] Run `bash demo.sh` once beforehand so the warm-up isn't recorded; then `rm -rf data/lakehouse/ data/raw/` so the recording shows a real cold run.
- [ ] Have these files open in tabs: [configs/engagement_events.yaml](../configs/engagement_events.yaml), [src/run_pipeline.py](../src/run_pipeline.py), [src/dashboard.py](../src/dashboard.py).

---

## Beat 1 — The thesis (≤ 30s, no terminal yet)

> "The brief frames this as a tooling problem — too many systems, too much cognitive load. I read it as a contract problem. Every team ships its own pipeline because there's no shared definition of what 'a user engagement event' is. My response: collapse to one ingestion path, one storage layer, one transformation framework — driven by versioned YAML data contracts that any squad can author without touching pipeline code."

Show the [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) Mermaid diagram on screen during this. (Open in GitHub or in the rendered case_study.html — both render Mermaid cleanly.)

---

## Beat 2 — The contract is the API (≤ 45s)

Open [configs/engagement_events.yaml](../configs/engagement_events.yaml). Scroll through.

> "This is one of three live contracts. Schema with allowed_values and nullability, transformations (dedup, late-event filter with quarantine routing, pseudonymization), quality gates, PII classification, access groups. The runtime in src/run_pipeline.py reads this file and executes Bronze → Silver → Gold. The squad doesn't write pipeline code; they write this YAML."

Point at: `transformations:` block, `quality.on_failure: block_silver_write`, `access.read_groups`.

---

## Beat 3 — The runtime is real (≤ 90s)

Run:

```bash
bash demo.sh
```

While it runs (~30 seconds), narrate live:

> "Step 1 generates 24K synthetic events with intentional dirt baked in: duplicates, late arrivals, invalid partner_ids. Step 2 runs the engagement_events contract — watch the per-step output: 500 duplicates removed by event_id, 50 late events routed to a quarantine table, user_ids pseudonymized via salted sha256. The schema is enforced; quality checks pass; silver is written. Step 3 runs partner_dashboard which reads silver and writes the partner-facing gold table. Step 4 queries the rollup."

When step 4 prints the per-partner rollup, **pause briefly on it**:

> "This is the money shot. Per-partner, per-day: DAU, sessions, engagement minutes, exercise completions. This is what the partner contractually sees in their dashboard."

---

## Beat 4 — The customer view (≤ 45s)

```bash
streamlit run src/dashboard.py
```

Wait for the browser to open. Then:

> "Same Gold table, same numbers, partner-facing. Filter by partner — Acme Corp only. KPI tiles. DAU trend per partner. The Gold table is the contract; the dashboard is one consumer. In production this is ClickHouse-backed for sub-second p95 — locally it's pandas reading the same Parquet."

Click the partner multiselect, change the date range, scroll to the raw rollup at the bottom.

---

## Beat 5 — The platform proof points (≤ 60s)

Back in the terminal, **show three artifacts** without spending more than ~15s on each:

**(a) Lineage sidecar** — every run emits a JSON record:

```bash
cat data/lakehouse/_lineage/engagement_events/run_*.json | head -40
```

> "Contract version, source, transformations, row counts, duration. This is what feeds Unity Catalog in production — and it's the 30-min-to-root-cause guarantee from REQUIREMENTS.md."

**(b) Schema compatibility check** — for the PR that proposes v2:

```bash
python src/check_schema_compat.py \
  --old configs/engagement_events.yaml \
  --new configs/engagement_events_v2_proposed.yaml
```

> "CI runs this on every contract PR. It classifies the diff and enforces the version bump policy. Breaking change without a major bump fails the build."

**(c) Right-to-deletion** — HIPAA-aligned posture:

```bash
python src/delete_user.py --user-id user_00001 --dry-run
```

> "Mental-health data; PII gravity is real. This script computes the silver-side pseudonym, cascades the delete across silver and gold, and writes an immutable tombstone for audit. Tested in CI."

---

## Beat 6 — Close (≤ 20s)

> "Three data products from three YAML files. One runtime. Schema enforcement, quality gates, lineage, quarantine, right-to-deletion — all driven by the contracts, not by hand-written pipeline code. The full case study is at the GitHub link below; happy to deep-dive on any of this in the interview."

Stop recording. Loom will give you a shareable URL.

---

## After the recording

- Trim the dead air at the start and end.
- Verify Loom shows your face in the bottom corner — interviewers respond better to a face than to a pure screencast.
- Paste the Loom URL into [scripts/build_case_study.py](../scripts/build_case_study.py) under `LINKS["Demo recording"]`, then re-run the build so the HTML/PDF artifact links to it.
- Also paste into the [Email template](EMAIL_TEMPLATE.md) before sending.
