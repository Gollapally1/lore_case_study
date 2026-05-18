# How to add a new data product

This is the self-service path. A non-platform squad (engagement, growth, clinical, ML) ships a new data product by writing one YAML file and opening a PR. The platform team reviews the contract; the runtime does the rest.

Target onboarding time: **≤ 2 engineer-days** from "we want this" to "it's in production with quality gates and a dashboard."

---

## The contract is the only file you have to write

Worked example: the clinical squad wants a `partner_clinical_outcomes` data product — per-partner weekly aggregates of clinical signals derived from `silver.engagement_events`.

**Step 1.** Create [configs/partner_clinical_outcomes.yaml](../configs/partner_clinical_outcomes.yaml):

```yaml
contract:
  name: partner_clinical_outcomes
  version: 0.1.0
  owner_squad: growth-clinical
  owner_email: clinical-data@lore.co
  description: >
    Per-partner weekly rollups of clinical signals (PHQ-9 deltas, session
    intensity, drop-off risk). Consumed by the clinical research dashboard
    and the partner success team.

source:
  type: delta_table
  table: silver.engagement_events
  read_mode: batch
  schedule_cron: "0 3 * * 1"        # Monday 3 AM PT

schema:
  - { name: partner_id,            type: string, nullable: false, pk: true }
  - { name: week_start,            type: date,   nullable: false, pk: true }
  - { name: avg_session_min,       type: double, nullable: false }
  - { name: high_intensity_users,  type: long,   nullable: false }
  - { name: drop_off_risk_users,   type: long,   nullable: false }
  - { name: last_refreshed_at,     type: timestamp, nullable: false, system_assigned: true }

storage:
  bronze: { enabled: false }
  silver: { enabled: false }
  gold:
    format: delta
    path: s3://lore-lakehouse/gold/partner_clinical_outcomes
    partition_by: [week_start]
    retention_days: 1825

transformations:
  - name: aggregate_weekly
    type: sql
    sql: |
      SELECT
        partner_id,
        DATE_TRUNC('week', event_timestamp) AS week_start,
        AVG(CAST(event_properties['duration_seconds'] AS DOUBLE) / 60.0)
            FILTER (WHERE event_type = 'session_end') AS avg_session_min,
        COUNT(DISTINCT CASE WHEN event_properties['intensity'] = 'high'
                            THEN user_id END) AS high_intensity_users,
        COUNT(DISTINCT CASE WHEN event_properties['drop_off_signal'] = 'true'
                            THEN user_id END) AS drop_off_risk_users,
        CURRENT_TIMESTAMP() AS last_refreshed_at
      FROM silver.engagement_events
      GROUP BY partner_id, DATE_TRUNC('week', event_timestamp)

quality:
  freshness_sla_minutes: 60
  completeness:
    - column: partner_id
      check: not_null
      threshold: 1.0
  on_failure: block_gold_write

discovery:
  catalog: unity_catalog
  tags: [clinical, partner-facing, weekly]
  pii_classification: amber
  sla_tier: tier_2

access:
  read_groups: [clinical-research, partner-success, growth-squad]
  write_groups: [dp-platform]
```

**Step 2.** Run it locally to confirm it parses and produces output:

```bash
python src/run_pipeline.py --contract configs/partner_clinical_outcomes.yaml
```

The runtime will:
- read `silver.engagement_events` as bronze input,
- execute the SQL transformation,
- enforce the schema (every nullable=false column present; allowed_values honored),
- run the quality checks (block the write if any violation triggers `block_gold_write`),
- write to `data/lakehouse/gold/partner_clinical_outcomes/` partitioned by `week_start`.

**Step 3.** Open a PR with the YAML + a test in [tests/](../tests/) asserting any business invariant specific to this product (e.g., `drop_off_risk_users <= dau`).

**Step 4.** The platform team reviews the contract for:
- Schema sanity (PK fields make sense; types portable),
- PII classification correct,
- SLA tier matches consumer expectations,
- Cost ballpark (rough partition + retention math).

That's the entire onboarding checklist.

---

## What you do NOT have to do

- **No pipeline code.** The runtime in [src/run_pipeline.py](../src/run_pipeline.py) handles bronze → silver → gold for every contract shape we currently support (`kafka` source, `delta_table` source; `deduplicate`, `filter`, `hash`, `sql`, `pyspark_function` transforms).
- **No Airflow DAG.** The contract's `source.schedule_cron` is the scheduler input; platform team wires it.
- **No discovery / catalog onboarding.** The `discovery:` block feeds Unity Catalog directly.
- **No access-control tickets.** The `access:` block feeds IAM directly.
- **No "data team standup" to negotiate timeline.** Open the PR; review SLA is 2 business days.

---

## When you SHOULD talk to the platform team first

- Your transformation doesn't fit the supported types (you need a custom join across two silver tables, or a streaming window with non-default watermarks). We'll either add support or hand-roll one job and document the gap.
- Your data product is a new **producer** (not a derivation of an existing silver table). New producers mean a new Kafka topic + schema registry subject; we co-design those.
- Your latency SLA is < 2 min. Sub-2-minute latency means Structured Streaming, not batch — the contract's `read_mode` and the Kafka topic config both matter.
- Your product is **partner-facing** (Tier 0). We do a joint design review for anything a customer sees.

---

## When a contract is rejected (and why)

- **PII in the wrong place.** Raw `user_id` or anything PHI-adjacent in a non-PII-vault path. Use the pseudonym from silver.
- **A definition that already exists.** "Active user" already has a canonical definition in [configs/partner_dashboard.yaml](../configs/partner_dashboard.yaml). If your definition diverges, version it and explain why; don't silently re-define it.
- **No owner.** Every contract has a single owning squad and on-call rotation. No exceptions.
- **No quality gate.** A contract without a `quality:` block is a contract without a promise. Even a single `not_null` check on the primary key counts; nothing is not acceptable.

---

## The 30-second mental model

> The YAML is the API. The runtime is the implementation. The platform team owns the implementation; squads own the APIs.

If you can describe your data product as YAML, you can ship it.
