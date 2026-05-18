# Demo recording — script, prep, and interview-fallback plan

A 3–4 minute walkthrough you can:
1. **Send pre-panel** as a Loom link (so interviewers can pre-read the artifact at their own pace).
2. **Play during the panel** if the live demo hits an unforeseen issue (laptop hibernation, network flake, Spark JVM tantrum). This is the real reason to record — risk insurance.

The script is timed for 3:30 with comfortable pacing. Hit RECORD only after running the prep script and reading the checklist.

---

## Step 0 — Tools

**Recommended: macOS built-in screen recording (Cmd-Shift-5) + Loom upload.**

- Cmd-Shift-5 → "Record Selected Portion" → drag a region → click Record → narrate → Esc to stop → save as `.mov`.
- The `.mov` is your **interview-fallback** asset. Save it somewhere you can find fast (`~/Desktop/lore_demo.mov`).
- Then upload the `.mov` to Loom (drag-and-drop into loom.com) and get a public share URL for the email.

Why not just Loom? Loom is cloud-hosted; if the venue Wi-Fi is bad during the panel, the fallback recording loads slowly. Keeping a local `.mov` you can drop into QuickTime / VLC works offline.

Alternatives:
- **Loom desktop app** — easiest end-to-end, but cloud-only.
- **OBS Studio** — best quality, steepest learning curve. Overkill here.
- **QuickTime → File → New Screen Recording** — equivalent to Cmd-Shift-5, slightly older UI.

---

## Step 1 — Pre-record checklist

Run this before every take:

```bash
bash scripts/prep_demo.sh
```

It cleans generated data, warms the JVM with a throwaway pipeline run (so the recorded run doesn't pay the cold-start tax), and confirms the dashboard's deps import. Takes ~30 seconds.

Then, manually:

- [ ] Terminal font 18pt (Cmd-+ a few times). Dark theme is fine; the screencap reads either way.
- [ ] Terminal window ~120 cols × 36 rows. Big enough to read, small enough to fit the recording region.
- [ ] **Clear the scrollback (Cmd-K)** so the recording starts on a blank prompt.
- [ ] Close every other window. Slack, Notes, Mail — close them. Notifications are recording poison; turn on Do Not Disturb (Cmd-Option-D).
- [ ] Second window open with `https://github.com/Gollapally1/lore_case_study` for Beat 1 (architecture diagram).
- [ ] Camera on if using Loom — a face in the corner reads as more trustworthy than a faceless screencast. Microphone level checked (one quick test recording first).

---

## Step 2 — The script (≈ 3:30 total)

### Beat 1 — Thesis (0:00 – 0:25, ~25s)

**Stay on the GitHub README page or the architecture diagram — no terminal yet.**

> "Hey, I'm Naveen. This is a 3-minute walkthrough of my Lore case-study response.
>
> The brief frames this as a tooling problem — too many systems, too much cognitive load. I read it as a **contract problem**. Every team ships its own pipeline because there's no shared definition of what 'a user engagement event' is. My response is to collapse to one ingestion path, one storage layer, one transformation framework — driven by versioned YAML data contracts that any squad can author without touching pipeline code.
>
> Here's the future-state architecture."

*(scroll briefly through the Mermaid diagram on GitHub)*

### Beat 2 — The contract is the API (0:25 – 1:05, ~40s)

**Switch to the editor; open [configs/engagement_events.yaml](../configs/engagement_events.yaml).**

> "This is one of three live contracts. Schema with `allowed_values` and nullability, transformations — dedup, late-event filter with quarantine routing, pseudonymization — quality gates, PII classification, access groups.
>
> The runtime in `src/run_pipeline.py` reads this file and executes Bronze → Silver → Gold. The squad doesn't write pipeline code; they write this YAML.
>
> Let's run it."

### Beat 3 — Live pipeline run (1:05 – 2:00, ~55s)

**Switch to the terminal at a clean prompt.**

```bash
bash demo.sh
```

While it scrolls (~25-30s after the warm-up), narrate:

> "Step 1 generates ~24,000 synthetic events with intentional dirt baked in: duplicates, late arrivals, invalid partner_ids. *(beat)* Step 2 runs the engagement_events contract — watch the per-step output. *(beat)* 500 duplicates removed by event_id, 50 late events routed to a quarantine table, user_ids pseudonymized via salted sha256. Schema enforced; quality checks pass; silver is written. *(beat)* Step 3 runs partner_dashboard — reads silver, writes the partner-facing gold table."

When step 4 prints the per-partner rollup, **pause on it visibly**:

> "And this is the money shot. Per-partner, per-day: DAU, sessions, engagement minutes, exercise completions. This is exactly what partners contractually see in their dashboard."

### Beat 4 — Customer-facing dashboard (2:00 – 2:35, ~35s)

```bash
streamlit run src/dashboard.py
```

Wait for the browser to open (or switch to a pre-opened tab to save time). Then:

> "Same Gold table, partner-facing. *(filter to one partner; numbers change)* Filter by partner — Acme Corp only — and the KPIs recompute. DAU trend per partner over the last 7 days. *(scroll to bottom)* And the same rollup table, sortable. In production this is ClickHouse-backed for sub-second p95 — locally it's pandas reading the same Parquet, which is good enough for the demo."

### Beat 5 — Platform proof points (2:35 – 3:20, ~45s)

**Switch back to the terminal.** Three quick artifacts, ~12 seconds each:

```bash
cat data/lakehouse/_lineage/engagement_events/run_*.json | head -40
```

> "Lineage sidecar per run. Contract version, source, transformations, row counts, duration. In production this feeds Unity Catalog — locally it's the answer to 'where did this number come from'."

```bash
python src/check_schema_compat.py \
  --old configs/engagement_events.yaml \
  --new configs/engagement_events_v2_proposed.yaml
```

> "Schema compatibility check — CI runs this on every contract PR. Classifies the diff, enforces the version bump policy. A breaking change without a major bump fails the build."

```bash
python src/delete_user.py --user-id user_00001 --dry-run
```

> "And right-to-deletion. Mental-health data; PII gravity matters. Computes the silver-side pseudonym, cascades the delete across silver and gold, writes an immutable audit tombstone. Tested in CI."

### Beat 6 — Close (3:20 – 3:35, ~15s)

> "Three data products from three YAML files, one runtime. Schema enforcement, quality gates, lineage, quarantine, right-to-deletion — all driven by the contracts, not by hand-written pipeline code. Full repo and PDF write-up are linked in the email. Thanks for watching."

**Stop recording.** Save as `~/Desktop/lore_demo.mov`.

---

## Step 3 — After the recording

1. Trim the dead air at the start and end (Cmd-Shift-T in QuickTime Player to start, or in Loom's editor).
2. Watch the take once muted, then once with audio. If it's not clean, retake — recording takes ~5 minutes; awkward audio is forever.
3. **Save the local `.mov`** to a place you'll find fast (`~/Desktop/lore_demo.mov` or pinned in Finder).
4. **Upload to Loom** (drag the `.mov` to loom.com) for the email link. Set sharing to "anyone with the link".
5. Paste the Loom URL into `scripts/build_case_study.py` (`LINKS["Demo recording"]`), then rerun `python scripts/build_case_study.py && python scripts/build_pdf.py` so the PDF artifact carries the working link.

---

## Step 4 — Interview-day fallback plan

If the live demo fails (laptop hibernation, network issue, Spark JVM hang, Streamlit port conflict), say something like:

> "Looks like X is misbehaving — let me skip the live run and play the recorded version so we don't burn panel time on the toolchain. I can answer questions on the underlying code as it plays."

Then:
1. Open `~/Desktop/lore_demo.mov` in QuickTime Player.
2. Cmd-F to fullscreen.
3. Pause whenever an interviewer interrupts with a question.

**Key reframe:** the video failing-over to fallback is itself a signal — it shows you anticipated failure modes and prepared for them. Don't apologize too much; ship the demo and move on.

---

## Step 5 — If you don't record

The case-study brief doesn't require a recording. The repo + PDF + live demo at the panel is a complete artifact set. Skip Steps 1–4 and:

- Run `bash scripts/prep_demo.sh` immediately before the panel so the warmup is already done — first live run is fast.
- Don't paste a Loom link into the email; replace that line with: *"Happy to walk through the demo live in the panel."*

Pick the path that minimizes anxiety for *you*. Both are credible.
