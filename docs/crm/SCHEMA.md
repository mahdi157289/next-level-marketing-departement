# CRM Schema

Three new tables sit alongside the existing `leads`, `outreach_records`,
`task_log`, `company_knowledge`, `campaign_metrics`. They are owned by
`crm/` but live in `db/models.py` (single source of truth for the schema).

The migration that creates them is
`migrations/versions/20260711_0002_crm_agent_runs.py`.

---

## 1. ER diagram

```
   pipeline_runs (1) ───< (N) agent_runs (1) ───< (N) lead_events >─── (1) leads
```

- One `pipeline_runs` row = one user-triggered pipeline invocation.
- Many `agent_runs` rows = one per agent step (Discovery, Head, ...).
- Many `lead_events` rows = audit trail of changes to a lead.
- `leads` is the existing CRM table (`migrations/versions/20260507_0001_*`).

---

## 2. Tables

### 2.1 `pipeline_runs`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | default `gen_random_uuid()` |
| `trigger` | VARCHAR(32) | `api`, `cli`, `pytest`, `celery` |
| `seed_query` | TEXT | discovery seed passed by the caller |
| `status` | ENUM `runstatus` | `running` / `success` / `failed` |
| `started_at` | TIMESTAMP | default `now()` |
| `finished_at` | TIMESTAMP | null until `complete_pipeline_run` |
| `meta` | JSONB | env snapshot, model aliases, anything useful for debugging |

### 2.2 `agent_runs`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `pipeline_run_id` | UUID FK -> `pipeline_runs.id` ON DELETE CASCADE | |
| `agent_name` | VARCHAR(64) NOT NULL | `discovery`, `head`, future `categorization`/`analysis`/... |
| `model` | VARCHAR(128) | LM Studio / LiteLLM model id used |
| `status` | ENUM `runstatus` | |
| `input_summary` | TEXT | short human-readable input |
| `output_summary` | TEXT | short output (truncated markdown) |
| `output_json` | JSONB | structured payload (search hits count, etc.) |
| `apis_consumed` | JSONB | **technical trace** — see `AGENT_INTEGRATION.md` §3 |
| `records_processed` | INT | leads touched |
| `error_message` | TEXT | on failure |
| `started_at` | TIMESTAMP | default `now()` |
| `finished_at` | TIMESTAMP | null until completion |

### 2.3 `lead_events`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `lead_id` | UUID FK -> `leads.id` ON DELETE CASCADE | |
| `agent_run_id` | UUID FK -> `agent_runs.id` ON DELETE SET NULL | null when an event is from outside an agent run |
| `event_type` | VARCHAR(32) NOT NULL | `created`, `status_changed`, `field_updated`, `skipped_duplicate` |
| `payload` | JSONB | `{field, old, new}` for status changes; `{source: ...}` for creation |
| `created_at` | TIMESTAMP | default `now()` |

---

## 3. Enums

```sql
CREATE TYPE leadstatus AS ENUM (
  'raw', 'categorized', 'enriched', 'contacted',
  'converted', 'unreachable', 'low_priority'
);

CREATE TYPE runstatus AS ENUM (
  'running', 'success', 'failed'
);
```

`leadstatus` already exists from migration 0001.
`runstatus` is created in migration 0002.

---

## 4. Idempotency

`leads.url` has a `UNIQUE` constraint. `crm.service.create_lead` does a
pre-check; on a duplicate URL it returns the existing row with
`created=False`. The Discovery agent uses that flag to count true inserts.

---

## 5. Growth path (not in Phase 1)

- **Add an `agent_runs.pipeline_run_id` index** if you start running many
  pipelines in parallel and find `list_agent_runs(pipeline_run_id=...)`
  slow. For Phase 1 volumes this is fine.
- **Materialize `apis_consumed`** into a relational table
  (`agent_run_api_calls`) only when you need SQL aggregations like
  "average LiteLLM latency per model". Today, JSONB is enough.
- **Add a `category` column on `agent_runs`** if you start running
  "discovery batch" vs "discovery spot-check" and want to slice.
- **Add a `crm_audit` table** for write operations performed via the REST
  API (not via agents), if you need an audit trail there too.
