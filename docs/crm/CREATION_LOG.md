# CRM Creation Log

Step-by-step build log for the CRM module. Append-only.

---

## 2026-07-13 — Phase 1 (Discovery + Head observable)

### Goal
Wire the CRM module end-to-end so that a single
`POST /run/pipeline/minimal` call produces observable artefacts in
`pipeline_runs`, `agent_runs`, `leads`, and `lead_events`, and is
readable via JSON API and a minimal Jinja2 UI.

### What was already in place
- `migrations/versions/20260711_0002_crm_agent_runs.py` (creates
  `pipeline_runs`, `agent_runs`, `lead_events`, `runstatus` enum)
- `db/models.py` ORM models for those tables
- `crm/__init__.py` package marker
- Empty `crm/templates/` directory

### What was added

| # | File | Purpose |
|---|---|---|
| 1 | `crm/schemas.py` | Pydantic v2 DTOs: `LeadCreate/Update/Read`, `PipelineRunCreate/Update/Read`, `AgentRunCreate/Update/Read`, `LeadEventRead`, `ApiConsumedEntry` |
| 2 | `crm/service.py` | Business logic — 14 functions, no FastAPI / agent / workflow imports. Idempotent lead create on `UNIQUE(url)`. |
| 3 | `crm/router.py` | FastAPI JSON API router (mounted at `/crm`) |
| 4 | `crm/client.py` | `AgentRunRecorder` + `_AgentRunContext` — in-process client for agents. |
| 5 | `crm/ui.py` | FastAPI router for Jinja2 templates (mounted at `/crm`) |
| 6 | `crm/templates/base.html` | Layout, nav, CSS |
| 7 | `crm/templates/leads.html` | Leads table |
| 8 | `crm/templates/lead_detail.html` | Lead detail + events |
| 9 | `crm/templates/runs.html` | Agent runs table (with duration + APIs summary) |
| 10 | `crm/templates/run_detail.html` | Run detail (input/output/apis/error) |
| 11 | `api/main.py` | Mount both CRM routers; thread `AgentRunRecorder` through `/run/pipeline/minimal` |
| 12 | `workflows/main_pipeline.py` | Accept `recorder=None`, pass to both agents |
| 13 | `agents/discovery_agent.py` | Enter `agent_run`, record `ddgs` + `litellm` APIs, persist `Lead` rows from search hits, set output |
| 14 | `agents/head_agent.py` | Enter `agent_run`, record `litellm` API, set output |
| 15 | `requirements.txt` | Add `jinja2>=3.1.0` |
| 16 | `tests/test_crm_api.py` | Real-DB integration tests for `/crm/health`, `/crm/leads`, `/crm/agent-runs`, `/crm/ui/*` |
| 17 | `docs/crm/README.md` | Module overview, decisions, lifecycle diagram |
| 18 | `docs/crm/SCHEMA.md` | ER diagram, columns, enums, growth path |
| 19 | `docs/crm/API.md` | Every endpoint, request/response, curl examples |
| 20 | `docs/crm/AGENT_INTEGRATION.md` | Recorder contract, `apis_consumed` schema, lead write rules |
| 21 | `docs/crm/CREATION_LOG.md` | This file |

### Decisions / deviations from the plan

- **Synchronous pipeline route** (not async + background task) per user
  preference. The route returns `{pipeline_run_id, status, result}` so
  callers can still correlate.
- **Backend + UI together** per user preference. The UI is read-only and
  uses Jinja2 + system CSS — no React build step.
- **Recorder wraps the LLM call, not the agent's lifetime** so the
  duration captured in `apis_consumed.duration_ms` is the actual model
  latency, not the agent's full lifetime.
- **Count only `created=True` leads** for `records_processed` to avoid
  inflating the count on re-runs.
- **No `apis_consumed` Postgres `GIN` index** for Phase 1 — JSONB scan is
  fine at current volumes. Add if `GET /crm/agent-runs?agent_name=...
  &api_name=...` becomes a hot path.

### Verification

```bash
# 1. Migrations
docker compose exec app alembic upgrade head
# -> 20260507_0001, 20260711_0002 applied

# 2. Tests
docker compose exec app pytest tests/test_crm_api.py -v

# 3. Live end-to-end
docker compose exec app python scripts/real_verification.py --pipeline
curl http://localhost:8000/crm/agent-runs | python -m json.tool | head -80
curl http://localhost:8000/crm/leads?status=raw | python -m json.tool | head -40
open http://localhost:8000/crm/ui/leads
open http://localhost:8000/crm/ui/runs
```

### Verification status (2026-07-14)

- Code wiring complete (routers mounted, agents record runs, leads persisted).
- `alembic upgrade head` → `20260711_0002`.
- `pytest tests/test_crm_api.py` — health, leads CRUD, agent-runs list, UI, pipeline CRM rows: **PASSED**.
- Live `/crm/ui/leads` and `/crm/ui/runs` return **200**.
- With LM Studio off, pipeline `status=failed` still leaves `pipeline_run_id`, discovery `agent_runs` (`apis_consumed`), and discovery-sourced leads.

### Out of scope (deferred)

- Categorization / Analysis / Outreach / Content agent wiring
  (schema + recorder contract support them; agent code is not yet
  written — see `TECHNICAL_IMPLEMENTATION_TRACKER.md` Phase D Step 2).
- Auth, edit/delete UI, separate `crm` Docker service on port 8001.
