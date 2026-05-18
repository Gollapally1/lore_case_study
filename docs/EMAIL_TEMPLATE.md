# Email template — sending the case study

Copy-paste, fill in the bracketed bits, send. Keep it short — the artifacts speak for themselves.

---

## Subject line (pick one)

- `Lore case study — Strategic Pipeline Modernization (Naveen Gollapally)`
- `Case Study 1 response — repo + demo + write-up`
- `Pipeline modernization case study — ahead of the panel`

The first is the safest; the second is friendlier; the third hints at preparedness.

---

## Body

> Hi [interviewer first names, comma-separated],
>
> Ahead of the panel on [DATE], I wanted to share my response to Case Study 1 (Strategic Pipeline Modernization) so you can skim or deep-dive at your own pace.
>
> **TL;DR.** I read the brief as a contract problem more than a tooling problem. My proposal: collapse to one ingestion path, one storage layer, one transformation framework — driven by versioned YAML data contracts that any squad can author without writing pipeline code. The architecture is Kafka → Spark Structured Streaming → Delta Lake → ClickHouse, governed by Unity Catalog.
>
> **Three artifacts:**
> 1. 📄 **PDF write-up** (attached) — architecture, requirements with cost Fermi estimate, phased migration plan, HOWTO for adding a new data product, and panel talking points by interview lens. Same content as the repo, in one printable file.
> 2. 💻 **Repo with runnable prototype:** [GITHUB_URL]
>    - Three live YAML data contracts driving the same PySpark Bronze → Silver → Gold runtime
>    - Schema enforcement, quality gates, lineage emission, quarantine sink, right-to-deletion script
>    - 16 pytest tests in CI; Streamlit dashboard for the partner-facing gold table
>    - `bash demo.sh` runs the full pipeline end-to-end in ~30 seconds
> 3. 🎬 **Demo walkthrough (3-4 min):** [LOOM_URL]
>
> Happy to deep-dive on the streaming-vs-batch trade-off, the schema versioning workflow, the migration sequencing, or anything else you'd like to probe in the panel.
>
> Thanks for the opportunity — looking forward to the conversation.
>
> Best,
> Naveen

---

## What to attach

- `case_study.pdf` — generated from `case_study.html` via Chrome's "Save as PDF". See [scripts/build_case_study.py](../scripts/build_case_study.py).

## What NOT to attach

- The full repo as a zip. Send the GitHub link instead — they'll get more signal from browsing the structure than from a zip.
- A separate slide deck. The case study is the artifact; the panel is the slide deck.
- Screenshots as separate files. Embed them in the HTML/PDF or in the README; don't make the interviewer manage attachments.

---

## Before sending — final checklist

- [ ] GitHub repo is **public** and the URL works in an incognito window.
- [ ] CI badge in the README is green.
- [ ] `bash demo.sh` runs clean on a fresh clone (test it in a tmp dir).
- [ ] Loom video is **public** (or "anyone with the link can view") — not "team only".
- [ ] PDF opens, renders Mermaid + tables correctly, links to GitHub + Loom are clickable.
- [ ] No real secrets, real PII, or `.env` files in the repo. `git log -p | grep -i 'pass\|key\|secret\|token'` returns nothing surprising.
- [ ] You can articulate the cost Fermi math without reading from notes. Same for the migration plan.

---

## Optional: follow-up email if you want a softer ramp

Day before the panel:

> Quick note ahead of tomorrow's session — the GitHub repo at [URL] now has the demo recording linked from the README, and `bash demo.sh` will reproduce the full pipeline end-to-end if you want to kick the tires before we meet.
>
> See you tomorrow!
