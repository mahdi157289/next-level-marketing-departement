# CRM Module — README

**Status:** Phase 1 wired (Discovery + Head observable) + Agents control UI (Start/Finish scout).
**Path:** `crm/`
**HTTP mount:** `/crm/*` on the existing FastAPI app (port 8000).

**Ops:** [docs/ops/START_DEPARTMENT.md](../ops/START_DEPARTMENT.md)  
**Incident (scout context / leads):** [docs/crm/SCOUT_FAILURE_2026-07-19.md](SCOUT_FAILURE_2026-07-19.md)

---

## 1. Why this module exists

The marketing-department agents (Discovery, Head, Categorization, Analysis,
Outreach, Content) each run an end-to-end pipeline that, today, returns a
JSON dict and forgets everything. The CRM module is the **observability +
control surface** that:

- **Persists every agent execution** as a row in `agent_runs` so you can
  answer *"what did the discovery agent do at 14:32, which model, which
  search backend, how long, did it succeed?"*.
- **Persists every pipeline invocation** as a row in `pipeline_runs`,
  threading the `agent_runs` rows to it via a foreign key.
- **Persists every lead** that the agents touch (today: search hits from
  Discovery), plus an audit trail in `lead_events`.
- **Exposes a JSON REST API** for programmatic read/write.
- **Renders a read-only Jinja2 UI** for humans to inspect.

It is intentionally **a module, not a service** today. The `crm/service.py`
layer has zero imports from `agents/` or `workflows/`, so it can later be
lifted into a standalone Docker service on port 8001 (the extraction rule,
see `.cursor/plans/department_crm_module_2b6f4dc7.plan.md`).

---

## 2. Layout

```
crm/
  __init__.py        # package docstring
  schemas.py         # Pydantic v2 DTOs (transport contract)
  service.py         # business logic (no FastAPI, no agent imports)
  router.py          # FastAPI APIRouter (JSON)
  ui.py              # FastAPI APIRouter (Jinja2 HTML)
  client.py          # AgentRunRecorder — in-process client used by agents
  templates/
    base.html
    leads.html
    lead_detail.html
    runs.html
    run_detail.html

docs/crm/
  README.md          # this file
  SCHEMA.md          # tables, columns, enums
  API.md             # every endpoint, request/response shape
  AGENT_INTEGRATION.md  # how agents log runs
  CREATION_LOG.md    # step-by-step build log

tests/test_crm_api.py  # integration tests (real Postgres)
```

---

## 3. Architectural decisions

| Decision | Rationale |
|---|---|
| `crm/service.py` has **no** FastAPI / agent / workflow imports | The plan's "extract later" rule. If we ever spin up `crm` as a separate Docker service, the business logic moves unchanged. |
| `crm/client.py` is the **only** thing agents import | Keeps the `agents -> crm` dependency one-directional. Future HTTP client drops in here. |
| Schema is in `db/models.py` (not `crm/`) | One source of truth for the DB; `crm/schemas.py` is the *transport* contract and mirrors the ORM with Pydantic. |
| Run lifecycle: `pipeline_run -> agent_runs[] -> lead_events[]` | The `pipeline_run` is the unit a user triggers. `agent_runs` are the units each agent emits. `lead_events` are the per-lead audit trail. |
| Lead insert is **idempotent on `Lead.url` (UNIQUE)** | Re-running the same pipeline doesn't duplicate leads. We track `created=true/false` so the agent can report "X new, Y duplicates". |
| `apis_consumed` is a **JSON array**, not a relational table | Simple technical trace (which backend, which model, how long). If the schema evolves, we migrate to a table — not preemptively. |
| Synchronous route (no Celery yet) | Matches the current `/run/pipeline/minimal` shape. The route returns `{pipeline_run_id, status, result}` so the caller can correlate. |

---

## 4. How to run it locally

```bash
# 1. Postgres up (port 5433 per project default)
docker compose up -d postgres

# 2. Apply migrations (creates pipeline_runs, agent_runs, lead_events)
docker compose run --rm app alembic upgrade head
# or on host with DATABASE_URL set:
alembic upgrade head

# 3. Start the app
uvicorn api.main:app --reload --port 8000

# 4. Trigger a pipeline run
curl -X POST http://localhost:8000/run/pipeline/minimal \
     -H "Content-Type: application/json" \
     -d '{"seed_query":"software agency Tunisia","max_search_results":5}'

# 5. Inspect what the agents did
curl http://localhost:8000/crm/agent-runs | python -m json.tool
curl http://localhost:8000/crm/leads?status=raw | python -m json.tool
curl http://localhost:8000/crm/pipeline-runs | python -m json.tool

# 6. Or open the UI
open http://localhost:8000/crm/ui/leads
open http://localhost:8000/crm/ui/runs
```

---

## 5. Run-lifecycle state machine

```
            POST /run/pipeline/minimal
                       │
                       ▼
            ┌─────────────────────┐
            │  pipeline_runs      │  status=running
            │  (1 row)            │
            └─────────────────────┘
                       │
       ┌───────────────┴───────────────┐
       ▼                               ▼
  DiscoveryAgent                HeadAgent
       │                               │
       ▼                               ▼
  ┌──────────────────┐          ┌──────────────────┐
  │ agent_runs       │          │ agent_runs       │
  │ status=running   │          │ status=running   │
  │  → success|failed│          │  → success|failed│
  │ apis_consumed[]  │          │ apis_consumed[]  │
  │ records_processed│          │ records_processed│
  └──────────────────┘          └──────────────────┘
       │
       ▼
  ┌──────────────────┐
  │ leads (N rows)   │  status=raw, source=discovery
  │ + lead_events[]  │  event_type=created
  └──────────────────┘
                       │
                       ▼
            ┌─────────────────────┐
            │  pipeline_runs      │  status=success|failed
            │  finished_at set    │
            └─────────────────────┘
```

---

## 6. Out of scope (Phase 1)

- Categorization / Analysis agent wiring (the schema and `apis_consumed`
  contract support them, but the agent code is not yet written — see
  `TECHNICAL_IMPLEMENTATION_TRACKER.md` Phase D Step 2).
- Edit / delete lead endpoints (UI is read-only).
- Auth (single-tenant, local Docker).
- Separate `crm` Docker service (extraction is structurally supported, not
  performed).

See `SCHEMA.md`, `API.md`, `AGENT_INTEGRATION.md`, and `CREATION_LOG.md` for
the contract and the build log.
