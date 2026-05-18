# Talking Points — Three Interview Lenses

The brief says: *"some [interviewers] more technical, some less. They'll be looking not just at your data engineering skills, but also at how you operate in an environment that's asynchronous, collaborative, and interdisciplinary."*

Three lenses. One artifact. Different emphasis per interview.

---

## Lens 1: Strategic / Leadership

**They're testing:** Can you articulate a vision, sequence work, manage risk, and bring an org along?

**Open with:** "The brief frames this as a tooling problem — too many systems, too much cognitive load. I read it as a contract problem. The tools are downstream of the fact that there's no shared definition of 'a user engagement event' or 'a partner KPI.' If we collapse the surface area without fixing that, in 18 months we'll be re-fragmented on a new stack."

**Key points to hit:**
- The **strangler fig** approach (in `MIGRATION_PLAN.md`), not big-bang
- Q1 deliverable is one data product **provably at parity** with the old system — that's how you buy trust
- I would not start by buying new tools. I'd start by writing the first contract and running it shadow.
- Org changes I'd ask for on day one: executive sponsorship, no-new-off-platform policy at week 8
- Success metrics (`REQUIREMENTS.md`): leading and lagging, and explicitly partner-NPS-driven

**Story anchor (TikTok labeling platform):**
> "I led a similar consolidation at TikTok — the labeling platform team had built infrastructure on three different stacks because three different ML teams had requested it at different times. I didn't try to convince them to migrate; I made the new platform the cheapest place to ship the *next* thing. Within two quarters, two of the three legacy stacks were dark because no one was building new on them."

**Story anchor (Wells Fargo NLPLyft):**
> "The contract-driven approach is a pattern I built at Wells Fargo. We had ML pipelines taking 10 weeks each to deliver — YAML-driven framework cut that to 4 weeks. The YAML wasn't the magic; the magic was that the data scientists could ship without me being in the loop. Same play here: squads ship data products without filing a ticket with my team."

**If they push back on multi-cloud / vendor independence:**
> "I'd push back on that as a goal. Multi-cloud is a CYA architecture. We're a 2-year-old startup; we need to win on speed, not on hypothetical portability. Pick one cloud, commit, and pay the migration cost in 5 years if we ever need to. Spending 2x today on portability we won't use is the wrong trade."

---

## Lens 2: Technical Depth

**They're testing:** Can you back the vision with engineering judgment? Streaming semantics, idempotency, schema evolution, CAP trade-offs.

**Open with:** "I'll walk you through the prototype. The thing I want to show is that the same runtime drives three data products from three YAML contracts. Then I'll go deep on whichever piece you want."

**The demo flow (live, ≤ 3 min):**
```
python src/generate_sample_data.py        # ~24K synthetic events with dirt baked in
python src/run_pipeline.py --contract configs/engagement_events.yaml
python src/run_pipeline.py --contract configs/partner_dashboard.yaml
python src/query_results.py
```

Things to point at while it runs:
- Dedup step removes ~500 duplicate event_ids — idempotency key working
- Late-event filter quarantines 50 stragglers — DQ in action
- Pseudonymization step replaces `user_id` with sha256 — show the hashed output
- `partner_dashboard` reads from silver, writes to gold, partitioned by `metric_date`

**Deep-dive topics they may probe, with your answer ready:**

**Q: Exactly-once semantics across Kafka → Spark → Delta — how?**
- Kafka: idempotent producer + transactional commits
- Spark Structured Streaming: checkpointed offsets in the same Delta transaction as the data write (atomic)
- Delta `MERGE` with idempotency key (`event_id`) handles the "at-least-once redelivery + dedup at sink" model
- Real exactly-once is exactly-once **effectively** — the math relies on dedup at the sink, not at the broker.

**Q: Why Spark Structured Streaming over Flink?**
- "Near real-time" in the brief means 2-5 min, not sub-second. Structured Streaming nails that.
- One runtime for batch and stream → one set of skills, smaller team, faster onboarding.
- When we hit a use case that genuinely needs sub-second (real-time chat content monitoring for crisis intervention, say), we add Flink for that one job, not the whole platform.

**Q: Why Delta over Iceberg?**
- ACID, schema evolution, time travel — both nail these
- Delta wins on the Databricks ecosystem integration (Unity Catalog, Liquid Clustering)
- Iceberg wins on vendor neutrality
- For a 2-year-old startup on a 4-quarter modernization, Databricks-native is the right trade

**Q: What about schema evolution? What happens when the app team adds a field?**
- Contract is versioned (`version: 1.2.0`). Producers register the new schema with the registry.
- Backward-compatible additions (new optional field) auto-flow through; consumers ignore unknown fields.
- Breaking changes require a major version bump and a parallel topic during migration window.
- The framework enforces this at CI: contract PR triggers a schema-compatibility check.

**Q: How does the framework handle late-arriving data without losing it?**
- Filter step in the contract routes events older than 7 days to a quarantine table, not /dev/null
- Quarantine table has a daily reconciliation job; owning squad reviews
- For events that are late but in-window, watermarks in Structured Streaming handle it; the silver table is updated via merge.

**Q: What if a quality check starts failing in prod at 3 AM?**
- Contract specifies `on_failure: block_silver_write` — bad data stops here, doesn't propagate
- Owning squad pages (not platform team — the squad owns the data product)
- Bronze still receives data; we replay to silver after fix.
- Time travel on Delta means we can roll back gold if a bad batch slipped through before the gate caught it.

**Q: How would you cost-optimize this?**
- Kafka: compress with zstd, set per-topic retention aggressively (bronze is the replay buffer, Kafka isn't)
- Bronze: 30-day retention, no Z-order — it's just landing
- Silver: Liquid Clustering (or Z-order) on the hot query columns (`user_id`, `partner_id`)
- Gold: ClickHouse serving layer is the expensive bit; partition pruning + materialized views
- Compute: serverless Databricks for ad-hoc, reserved capacity for known streaming jobs
- Per-contract cost reporting (Q4 in the migration plan) — each squad sees their bill

---

## Lens 3: Cross-Functional / Collaborative

**They're testing:** Do you ship in a vacuum or with the org? Async, interdisciplinary, opinionated-but-not-doctrinaire.

**Open with:** "The thing I'd want this team to know about how I work: I don't ship pipelines, I ship platforms. The success metric isn't 'I built a thing.' It's 'three squads built a thing without me being in the room.'"

**Key points to hit:**
- **The contract is the collaboration artifact.** A YAML file in a PR is more durable than a Slack thread or a meeting. Producer, consumer, and platform all comment on the same diff.
- **Squads own data products end-to-end.** Engagement squad owns the engagement events contract — schema, SLA, on-call. Platform owns the runtime that honors all contracts.
- **Async-first.** I'd push for written design docs over meetings. The contract framework here is one example — a new squad can read three files and ship something without scheduling time with me.
- **Interdisciplinary respect.** The `user_journey` contract has `derive_stage` as a `pyspark_function`, not SQL, because the **clinical team** owns that rule. I shouldn't be the bottleneck for a clinical insight; my framework should accommodate that.
- **What I'd push back on:** treating data engineering as a ticket queue. If product wants a new dashboard, we co-design the contract, not "throw a ticket over the wall."

**Story anchor (Wells Fargo platform team):**
> "I led a 20-engineer platform team at Wells Fargo. The biggest lesson: the platform team has to be a service org, not a gatekeeping org. We instrumented our 'engineer-days saved per quarter' metric and reported it to leadership monthly. That number aligned us with the rest of engineering — we weren't a cost center, we were a force multiplier."

**Story anchor (TikTok pod restructuring):**
> "At TikTok we restructured the team into pods aligned to data product domains. Before: every DE got pulled into every priority. After: each pod owned its data products end-to-end including on-call. Throughput went up because context-switching went down. I'd advocate for something similar at Lore if the team is north of 4-5 DEs."

**If they ask about working with non-technical partners:**
> "Partner-facing dashboards are a different beast from internal analytics. Partners don't care about 'we had a Kafka rebalance' — they care that today's number is right. I'd build a partner-status page that's honest about freshness and quality. Trust comes from telling them the truth before they have to ask."

---

## Things to NOT do in any of the three interviews

- Don't oversell. Say "I'd assume X, you'd correct me if I'm wrong" — you don't know Lore's actual stack.
- Don't bash named tools. Even if you'd never use Segment / Amplitude / Looker, frame it as "the trade we made vs. these alternatives" not "those are bad."
- Don't promise specific timelines without conditional language. "Assuming X engineers and Y prerequisites, Q1."
- Don't get stuck on streaming-vs-batch religious arguments. "Latency follows the consumer, not the producer" — repeat that line.
- Don't forget: this is a **mental health company**. PII gravity is real. Show that you instinctively reach for pseudonymization, audit logs, and "is this data even necessary?"
