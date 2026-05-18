# Requirements: Functional, Non-Functional, and Success Criteria

## Functional requirements

| ID | Requirement | Driver |
|---|---|---|
| F-1 | Ingest events from iOS, Android, Web clients via a single Kafka topic per domain | App teams ship without filing platform tickets |
| F-2 | Ingest partner data (eligibility, contracts, financial terms) via SFTP and partner-specific REST APIs | Partner-team-owned, no central ETL gatekeeper |
| F-3 | Support exactly-once semantics from Kafka to silver | Partner dashboards are contractually correct |
| F-4 | Support point-in-time replay of any silver/gold table from bronze | Incident recovery, schema migrations, audit |
| F-5 | Publish per-partner daily and hourly engagement rollups to a sub-second OLAP store | Partner dashboard latency |
| F-6 | Provide a single discovery surface (catalog) where any analyst can find any data product and see its owner, schema, freshness, and quality status | Cross-squad collaboration |
| F-7 | Squads can register a new data product by adding a YAML contract; no platform-team code changes required | Self-service is the lever for scaling without growing the platform team linearly |
| F-8 | All PII is pseudonymized at the bronze → silver boundary; raw PII lives only in a separate, access-restricted vault | HIPAA-adjacent posture for mental health data |
| F-9 | Support both streaming (≤ 2 min) and batch (≤ 24 hr) cadences from the same framework | Latency follows the consumer, not the producer |
| F-10 | Quality checks gate writes; failures alert the owning squad without blocking unrelated pipelines | Single bad upstream doesn't take down everything |

## Non-functional requirements

### Latency SLAs

| Data product | Freshness SLA (p95) | Tier |
|---|---|---|
| `partner_dashboard` (customer-facing) | ≤ 5 min | Tier 0 — page on-call |
| `engagement_events` (silver foundation) | ≤ 2 min | Tier 1 — page on-call |
| `user_journey` (analytics + clinical) | ≤ 15 min (batch) | Tier 2 — alert squad |
| ML feature store | ≤ 2 min | Tier 1 — page on-call |

### Reliability SLAs

| Component | Availability target | Notes |
|---|---|---|
| Kafka ingest | 99.95% | 3 brokers per AZ, MSK or Confluent Cloud |
| Spark Structured Streaming jobs | 99.9% | Checkpointed; auto-restart on transient failure |
| Delta Lake | 99.99% | S3 backed; concurrency-controlled writes |
| ClickHouse partner-serving | 99.95% | Multi-replica per shard |
| Partner dashboard API | 99.9% end-to-end | Includes app tier; SLO budget alarms |

### Scalability

- Event volume: design for 10× current (today's ~500K events/day → 5M/day in 18 months)
- Partner count: design for 100 partners (current ~10 assumed) — partition keys and ClickHouse shard scheme must not require re-sharding at that scale
- Squad count: design for 8 product squads each registering 1-3 contracts. Framework must support 50+ contracts without runtime degradation.

### Data quality

- **Completeness:** ≥ 99.9% of events have a valid `user_id` and `partner_id`
- **Uniqueness:** zero duplicate `event_id`s in silver (idempotency key enforced at dedup step)
- **Validity:** 100% of `event_type` values in the contract's `allowed_values` set
- **Timeliness:** ≥ 99% of events in silver within the freshness SLA
- **Volume anomaly:** alert if event rate drops > 50% from 7-day rolling mean
- **Business rules:** product-specific (e.g., `dau ≤ total_sessions` per partner-day) — defined in each contract

### Security and compliance

- All PII encrypted at rest (S3 SSE-KMS) and in transit (TLS 1.3)
- Pseudonymization at silver boundary; raw PII vault accessible only by named identity service
- Audit log of all reads of any table tagged `pii_classification: amber` or higher
- HIPAA-aligned controls (Lore handles mental-health data — even if not strictly a covered entity, the posture matters for partner contracts)
- Right-to-deletion: tested workflow that propagates a user deletion from PII vault through silver and gold within 30 days

### Operational efficiency

- Onboarding a new data product: ≤ 2 engineer-days (was ≥ 2 engineer-weeks in fragmented state)
- Time to root-cause a partner-dashboard discrepancy: ≤ 30 min via lineage + time travel
- Number of platform engineers required: scales sub-linearly with number of data products (target: 1 platform engineer per 15 contracts)

## Success criteria (how we measure that the modernization worked)

### Leading indicators (months 1-3 of post-launch)
- ✅ ≥ 3 data products migrated to the contract framework
- ✅ ≥ 2 squads have authored their own contract without platform-team coding
- ✅ Partner dashboard freshness SLA met for 95% of 5-min windows
- ✅ Zero partner-reported data discrepancies traced to pipeline inconsistency

### Lagging indicators (months 6-12)
- ✅ ≥ 80% of all "engagement" or "partner KPI" queries routed through canonical data products (vs. ad-hoc SQL against raw)
- ✅ Cost-per-event ingested-to-served down ≥ 40% from current fragmented baseline
- ✅ New data product time-to-production median ≤ 2 days
- ✅ Net Promoter Score from internal data consumers (analysts, ML, clinical) > +30
- ✅ Number of distinct tools in the critical path: from N (today) to 5 (Kafka, Spark, Delta, ClickHouse, dbt for batch transforms)

## Cost Fermi estimate (back-of-envelope, defensible)

The "≥ 40% cost reduction" claim isn't a slogan. Here's the math. All numbers are list-price / public estimates; real spend will be 20-40% lower with reserved capacity and committed-use discounts. The point is the *ratio*, not the absolute.

### Assumptions

| Variable | Value | Source |
|---|---|---|
| Event volume today | 500K events/day | Inferred from "small but growing partner book" |
| Event volume target (18mo) | 5M events/day | 10× design point in NFRs |
| Avg event size on wire | 1 KB (JSON) / 300 B (Avro on Kafka) | Typical for engagement events |
| Partners today / 18mo | 10 / 100 | Stated 10× scale-out |
| Active dashboards | ~30 (one core + ~3 custom per partner) | Conservative |

### Current state (fragmented) — estimated monthly spend at today's volume

| Component | Driver | Monthly cost |
|---|---|---|
| Segment / Amplitude event ingest | 500K/day × 30 = 15M MTUs/mo at ~$0.10/MTU equivalent | ~$1,500 |
| BigQuery storage + query | ~1 TB hot + ~10K queries/mo | ~$700 |
| Snowflake (secondary analytics warehouse) | Small but constantly running | ~$1,200 |
| Looker (per-seat, 20 analysts) | $50/seat × 20 | ~$1,000 |
| Ad-hoc Lambdas + S3 + Athena (the "glue") | Hard to attribute; ~3 always-on functions + scans | ~$400 |
| Per-partner cached JSON / Postgres replica | RDS small + S3 | ~$300 |
| **Total estimated** | | **~$5,100/mo** |
| Cost per event ingested-to-served | $5,100 / 15M events | **~$0.34 / 1K events** |

The hidden cost is engineering time: every dashboard discrepancy is a multi-team investigation because no one owns the canonical definition. Estimating ~10 engineer-hours/week across the org reconciling numbers = ~$10K/mo in fully-loaded labor. That's > 2× the tooling spend.

### Future state (consolidated) — estimated monthly spend at today's volume

| Component | Driver | Monthly cost |
|---|---|---|
| MSK Serverless or Confluent Cloud | 15M events/mo × 1 KB = ~15 GB ingress, 3× for fan-out = 45 GB | ~$400 |
| Databricks compute (Structured Streaming, 2 jobs always-on, small) | ~6 DBU/hr × 730 hr × $0.40 (jobs compute) | ~$1,750 |
| Delta on S3 (bronze 30d + silver 2y + gold 7y) | ~5 TB total at $0.023/GB | ~$120 |
| ClickHouse Cloud (1 small cluster) | Partner-facing serving, ~$0.50/hr × 730 | ~$365 |
| Unity Catalog + lineage | Included with Databricks | $0 |
| Looker (or replace with Hex / Mode) | $50/seat × 20 (or sub-out) | ~$1,000 |
| **Total estimated** | | **~$3,635/mo** |
| Cost per event ingested-to-served | $3,635 / 15M events | **~$0.24 / 1K events** |

**Tooling savings: ~$1,500/mo (~29%).** That alone doesn't hit the 40% target. The 40% claim depends on:

1. **Killing the engineering-time reconciliation tax.** The pitch isn't "tools got cheaper" — it's "tools got cheaper AND the org stops paying for the same number to be computed three times." If we recover even half the ~$10K/mo labor cost, total cost-to-serve drops from ~$15K to ~$8.6K = **~42% reduction**.
2. **Sub-linear scaling.** At 10× volume (5M events/day), Segment/Amplitude pricing scales ~linearly; Kafka + Databricks scale closer to log/sqrt because the always-on overhead dominates. Projected 18-month cost-per-event in the new architecture: ~$0.10 / 1K events vs. ~$0.30 if we'd stayed on the fragmented stack. **~3× delta at the scale-out point.**

### What we are NOT counting

- Migration cost: ~1 platform-engineer-quarter + ~1 squad-engineer-month per migrated product. Sunk during Q1-Q3 of the plan. Pays back in Q4 of year 1 at the cost-per-event delta above.
- Cost of *not* doing this: a partner-visible discrepancy that triggers a contract dispute. One incident's worth of leadership attention pays for the entire migration.

### Where the numbers can move

- Real Databricks compute could be 2× higher if streaming jobs run hotter than estimated. Mitigation: serverless SQL for ad-hoc, reserved capacity for the two always-on streaming jobs.
- ClickHouse Cloud is the rate-of-spend risk: if partner dashboards generate unexpectedly high query volume, this line scales with QPS. Mitigation: materialized views for the top 10 query shapes; cache aggressively at the API tier.
- The labor recovery number is the most uncertain. Audit at 6 months: are we still spending engineer-hours on "why is this number different from that number"?
