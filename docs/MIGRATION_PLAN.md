# Phased Migration Plan

The wrong way to do this: stop the old pipelines, build a new one, cut over. That guarantees a 6-month outage of trust in the data while we debug parity.

The right way: **strangler fig**. The new platform runs in parallel with the old, dashboards switch one at a time, and a published parity report keeps everyone honest until the old stuff is decommissioned.

## Q1 — Foundation (weeks 1-12)

**Goal:** the new platform exists, can ingest one data product end-to-end, and is provably correct.

| Week | Deliverable | Owner |
|---|---|---|
| 1-2 | Decision: cloud + Kafka + lakehouse vendor. Document and circulate. | Staff DE (me) |
| 3-4 | Kafka cluster (MSK or Confluent), schema registry, IAM | Platform DE + Infra |
| 5-6 | Databricks workspace (or self-managed Spark), Unity Catalog, S3 buckets, KMS keys | Platform DE + Infra |
| 7-8 | Contract framework v1 (the runtime in this prototype, productionized) | Platform DE (me) |
| 9-10 | `engagement_events` data product live in shadow mode (writes to silver but not yet authoritative) | Platform DE + Engagement squad |
| 11-12 | Parity report: silver `engagement_events` vs. legacy event store. Target: < 0.1% row delta after dedup. | Platform DE + Analytics |

**Exit criteria:** parity report green for 2 consecutive weeks. Engagement squad signs off.

**Risks:**
- Schema registry adoption requires app-team changes. Mitigate: provide a SDK that wraps the schema-registry serializer; app teams change one import.
- Kafka cost. Mitigate: start with MSK Serverless, move to provisioned only if proven needed.

## Q2 — Migrate the customer-facing path (weeks 13-24)

**Goal:** Partner dashboards run on the new platform. Old path is dark but not yet deleted.

| Week | Deliverable |
|---|---|
| 13-14 | `partner_dashboard` contract live; ClickHouse serving cluster stood up |
| 15-16 | New partner-dashboard UI reads from ClickHouse in shadow mode; old UI still authoritative |
| 17-18 | Parity report per partner per day; SLA-budget tracking |
| 19-20 | Switch one pilot partner to new dashboard; old dashboard available as fallback link |
| 21-22 | Switch remaining partners in cohorts of 3; one cohort per week |
| 23-24 | Old partner-dashboard pipeline frozen (no new development); 30-day deletion timer starts |

**Exit criteria:** all partners on new dashboard, zero parity-driven escalations for 30 days.

**Risks:**
- One partner uses a metric in a contract dispute. Cutover for that partner waits until legal sign-off; everyone else proceeds.
- ClickHouse query patterns surprise us at full traffic. Mitigate: load test with 3× peak traffic before cohort 1.

## Q3 — Migrate analytics and ML paths (weeks 25-36)

**Goal:** Internal analytics, clinical research, and ML feature store all consume the new data products. Legacy event store can be deleted.

| Week | Deliverable |
|---|---|
| 25-28 | `user_journey` contract live; clinical team's existing notebooks pointed at it |
| 29-32 | ML feature store reads from silver instead of legacy event store. Online + offline parity tested. |
| 33-34 | Decommission legacy event store (cold-archive to S3 Glacier for compliance retention) |
| 35-36 | Run a "platform demo week" — each squad presents what they built on the new framework |

**Exit criteria:** ≥ 5 data products live, ≥ 3 squads have authored their own contract.

**Risks:**
- ML team's feature engineering is tightly coupled to the old event store schema. Mitigate: dedicated office hours from platform team during weeks 25-30; the feature store wrapper isolates the change.

## Q4 — Hardening, governance, second-wave products (weeks 37-48)

**Goal:** The platform is the obvious choice, not the new choice.

| Week | Deliverable |
|---|---|
| 37-40 | Right-to-deletion workflow tested end-to-end |
| 41-44 | Lineage and discovery UI tied to Unity Catalog; one-click "who owns this table" |
| 45-46 | Cost reporting per data product, per squad — accountability for runtime spend |
| 47-48 | Year-in-review: success metrics from `REQUIREMENTS.md` reported to leadership |

## What I would NOT do

- **No big-bang launch.** Strangler fig or nothing.
- **No new data product on the old system after week 12.** Forcing-function: if it's worth shipping, it's worth shipping on the platform.
- **No platform team writing application logic.** Squads write contracts and consumer logic; the platform team owns the runtime that makes contracts honor themselves.
- **No "modernization" project that lasts more than 4 quarters.** Past that, momentum and budget evaporate. If we can't show Q1 value, we restructured the wrong way.

## What I'd ask Lore leadership for, day one

1. Executive sponsor for the contract-as-API model. Without buy-in, squads will keep building their own pipelines, and we end up with the new platform AND the old fragmentation.
2. Engineering manager partnership: I'll commit to one platform-engineer-month for every five engineer-weeks of squad migration time. The math gives us a 5:1 leverage ratio.
3. A "no new pipelines off-platform" policy starting week 8. Existing pipelines stay running; new ones go through the contract review.
