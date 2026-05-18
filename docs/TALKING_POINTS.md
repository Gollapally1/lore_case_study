# Engineering Trade-offs & Operating Principles

This document captures the *why* behind the rest of the case study — the engineering decisions, the explicit trade-offs they ride on, and how I'd operate the team that owns this platform.

---

## Framing: a contract problem, not a tooling problem

The brief reads like a tooling problem (too many systems, too much cognitive load). I read it as a contract problem.

Every team ships its own pipeline because there's no shared, versioned definition of what "a user engagement event" or "a partner-level KPI" actually is. Collapse the surface area without fixing that and we re-fragment on a new stack within 18 months. The first artifact I'd ship isn't a Kafka cluster; it's the first YAML contract, run in shadow mode, with a parity report against the legacy event store.

---

## Strategy: strangler fig, not big-bang

Big-bang migrations of customer-facing data have a near-100% failure mode: a 6-month outage of trust in the numbers while teams debug parity. The strangler-fig approach in [MIGRATION_PLAN.md](MIGRATION_PLAN.md) is deliberate:

- New platform runs in parallel; dashboards switch one at a time.
- A published parity report keeps everyone honest until decommissioning.
- The forcing function is policy ("no new pipelines off-platform after week 8"), not exhortation.

I've shipped this exact pattern before. At TikTok, the labeling platform team had built on three different stacks because three different ML teams had requested it at different times. I didn't try to convince them to migrate — I made the new platform the *cheapest place to ship the next thing*. Within two quarters, two of the three legacy stacks were dark because no one was building new on them.

---

## Engineering choices and the trade-offs

### Why Spark Structured Streaming, not Flink

"Near real-time" in the brief is 2–5 minutes, not sub-second. Structured Streaming hits that comfortably with one runtime that also handles batch — same skills, smaller team, faster onboarding. Flink is technically superior for true sub-second streaming, but adopting it now means two runtime stacks for a marginal latency win nobody is asking for.

If we hit a use case that genuinely needs sub-second (real-time chat content monitoring for crisis intervention, say), we add Flink for that *one* job, not for the platform.

### Why Delta Lake, not Iceberg

Both nail ACID, schema evolution, and time travel. The differentiators:
- **Delta** wins on the Databricks ecosystem (Unity Catalog, Liquid Clustering, MERGE performance).
- **Iceberg** wins on vendor neutrality and the Trino/Flink-native story.

For a 2-year-old company on a 4-quarter modernization, Databricks-native is the right trade. If the company's strategic direction shifts toward Snowflake or a multi-engine future, the data is portable — that's the value of an open format. We're not locked in; we've optimized for present-day velocity.

### Why ClickHouse for the partner dashboards

Partner-facing analytics queries are predictable shapes: group by `partner_id` and `date`, aggregate. ClickHouse beats every alternative on sub-second p95 at this query pattern. Pinot is the close competitor (and what Walmart uses for similar workloads); ClickHouse has the edge for OLAP query flexibility and is cheaper to operate at our scale.

The Delta-to-ClickHouse mirror is continuous (CDC-driven). Delta is the system of record for audit and replay; ClickHouse is the serving layer for the UI. Two layers, two jobs.

### Exactly-once semantics — what this actually means

"Exactly-once" is a marketing word. What you actually get is **exactly-once effectively** through this chain:
1. **Kafka**: idempotent producer + transactional commits.
2. **Spark Structured Streaming**: checkpointed offsets in the same Delta transaction as the data write (atomic — the only durable correctness guarantee).
3. **Delta `MERGE`** with `event_id` as the idempotency key handles at-least-once redelivery + dedup at the sink.

The math relies on dedup at the sink, not exactly-once at the broker. The contract's `deduplicate` step (visible in [src/run_pipeline.py](../src/run_pipeline.py)) is what makes the guarantee real.

### Schema evolution — additive flows; breaking changes get a major bump

The contract is versioned (semver). [src/check_schema_compat.py](../src/check_schema_compat.py) is the CI check that runs on every contract PR:
- **Additive** changes (new optional field, widened enum) flow through; consumers ignore unknown fields.
- **Breaking** changes (removed field, narrowed enum, type change, nullable → required) require a major version bump and a parallel topic during the migration window.

[configs/engagement_events_v2_proposed.yaml](../configs/engagement_events_v2_proposed.yaml) is a worked example — a real diff (`event_properties` map → struct, `event_type` enum narrowed) and a 6-week parallel-topic plan.

### Late-arriving data goes to a quarantine sink, not /dev/null

The contract specifies `on_violation: route_to_quarantine` for late events. The runtime writes them to `data/lakehouse/quarantine/<contract>/<step>/` with a `__quarantine_reason` and `__quarantine_at` column. The owning squad has a daily reconciliation job; nothing is silently dropped. This is the difference between a pipeline that "filters" and a pipeline that's auditable.

### When quality checks fail at 3 AM

The contract's `on_failure: block_silver_write` is doing real work: bad data stops at the silver boundary, doesn't propagate to gold, doesn't reach the partner dashboard. Bronze still receives data (it's the replay buffer); we re-run silver after fix. Delta's time travel means we can roll back gold if a bad batch ever slips through before the gate catches it.

The squad that owns the data product pages, not the platform team. Platform owns the runtime; squads own the contracts.

### How I'd cost-optimize

- **Kafka**: zstd compression, per-topic retention aggressively short (bronze on S3 is the replay buffer, not Kafka).
- **Bronze**: 30-day retention, no Z-order — it's just landing.
- **Silver**: Liquid Clustering (or Z-order) on the hot query columns (`user_id`, `partner_id`).
- **Gold**: ClickHouse is the expensive bit; materialized views for the top-10 query shapes, partition pruning, query-tier caching.
- **Compute**: serverless Databricks for ad-hoc; reserved capacity for the two always-on streaming jobs.
- **Per-contract cost reporting**: each squad sees their own bill — accountability without finger-pointing. (Q4 deliverable in [MIGRATION_PLAN.md](MIGRATION_PLAN.md).)

The cost Fermi in [REQUIREMENTS.md](REQUIREMENTS.md) backs out to ~$3.6K/month future-state vs. ~$5.1K current-state at today's volume, and roughly 3× cheaper per event at the 18-month scale-out point.

---

## How I operate

**I don't ship pipelines; I ship platforms.** The success metric isn't "I built a thing" — it's "three squads built a thing without me being in the room."

**The contract is the collaboration artifact.** A YAML file in a PR is more durable than a Slack thread or a meeting. Producer, consumer, and platform comment on the same diff. The [HOWTO_NEW_DATA_PRODUCT.md](HOWTO_NEW_DATA_PRODUCT.md) is the self-service path — review SLA is 2 business days, not "let's schedule a meeting."

**Squads own data products end-to-end.** Engagement squad owns the `engagement_events` contract — schema, SLA, on-call. Platform owns the runtime that honors all contracts. That separation is the difference between a platform team that scales and one that becomes a bottleneck.

**Async-first.** Written design docs over meetings. A new squad should be able to read three files in this repo and ship a fourth data product without scheduling time with me.

**Interdisciplinary respect.** [configs/user_journey.yaml](../configs/user_journey.yaml) has `derive_stage` as a `pyspark_function`, not SQL, because the **clinical team** owns that rule. I shouldn't be the bottleneck for a clinical insight; my framework should accommodate that.

**The platform team is a service org, not a gatekeeping org.** At Wells Fargo I led a 20-engineer platform team. The biggest lesson: we instrumented "engineer-days saved per quarter" as our headline metric and reported it to leadership monthly. That number aligned us with the rest of engineering — we weren't a cost center, we were a force multiplier.

---

## Where I'd push back

**Multi-cloud as a goal.** Multi-cloud is a CYA architecture. For a 2-year-old company, the trade is wrong — we need to win on speed, not on hypothetical portability. Pick one cloud, commit, pay the migration cost in five years *if* we ever need to. Spending 2× today on portability we won't use is the wrong call.

**Data engineering as a ticket queue.** If product wants a new dashboard, we co-design the contract; we don't take a ticket over the wall. The contract becomes the durable artifact; the ticket disappears.

**"Modernization" projects that last more than four quarters.** Past that, momentum and budget evaporate. If we can't show Q1 value, we restructured the wrong way and need to ship something small before continuing.

**Treating partner-facing data the same as internal analytics.** Partners don't care about "we had a Kafka rebalance" — they care that today's number is right. I'd build a partner-facing status page that's honest about freshness and quality. Trust comes from telling them the truth before they have to ask.

---

## What I'd ask leadership for on day one

1. **Executive sponsor** for the contract-as-API model. Without buy-in, squads will keep building their own pipelines, and we end up with the new platform AND the old fragmentation.
2. **EM partnership**: I'll commit to one platform-engineer-month for every five engineer-weeks of squad migration time. The math gives us a 5:1 leverage ratio.
3. **A "no new pipelines off-platform" policy starting week 8.** Existing pipelines stay running; new ones go through the contract review.
4. **A standing 30-minute weekly with one product leader and one engineering leader** — not for status, but to surface where the platform is friction. Platform teams that don't have this signal end up shipping things squads don't need.

---

## Prior art this draws on

The contract-driven framework is a pattern I built at Wells Fargo (NLPLyft). ML pipelines were taking ~10 weeks each to deliver; the YAML-driven framework cut that to ~4 weeks. The YAML wasn't the magic — the magic was that data scientists could ship without me being in the loop. Same play here: squads ship data products without filing a ticket with my team.

The pod-by-data-product team structure draws on what we did at TikTok: each pod owned its data products end-to-end including on-call. Before: every DE got pulled into every priority. After: throughput went up because context-switching went down. I'd advocate for this structure at Lore once the DE team is north of 4–5 engineers.
