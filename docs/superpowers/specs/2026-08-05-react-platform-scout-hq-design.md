# Design: React Platform Redesign + Scout HQ

Date: 2026-08-05
Status: Approved (design)
Scope: Full React SPA rewrite of the CRM platform, dark bold-accent redesign, and a new "Scout HQ" (chat + mission board) for the Discovery agent.

## 1. Goal

Transform the current Jinja2 CRM UI into a React SPA with an innovative dark, bold-accent
visual identity, and give the Scout (Discovery agent — which runs on its own model) a
dedicated home: a **chat interface with live tool calling** plus a **mission board**.

## 2. Context (as-built)

- Backend: FastAPI (`api/main.py`) mounts `crm_router` at `/crm` and `crm_ui_router` at `/crm/ui/*`.
- Current UI: 7 Jinja2 templates in `crm/templates/` (`base`, `agents`, `agent_detail`, `leads`, `lead_detail`, `runs`, `run_detail`) — plain light-gray admin theme, horizontal top-nav.
- Agents: `discovery` (Scout, own `model` override in `agent_profiles`), `head`, `qualifier`.
  - Scout model resolution: `agent_profiles.discovery.model` → `settings.agent_model_discovery` (agents/discovery_agent.py:110).
  - Scout mission + tools: `agent_profiles.discovery.mission_prompt` + `enabled_tools` (agents/discovery_agent.py:113,119).
- LLM client: `agents/lm_client.py` — OpenAI-compatible client, `base_url`/`api_key` from settings. In prod: OpenRouter (`https://openrouter.ai/api/v1`), model `google/gemma-4-26b-a4b-it:free`.
- Tools: `tools/registry.py` (`resolve_callable`, `tool_enabled`); `web_search_tool`, `google_maps_search` (Node.js scraper), `meta_ads_search`, `scrape_tool`, `seo_audit_tool`.
- Runs: `agent_runs` / `pipeline_runs` tables recorded via `crm/client.py` `AgentRunRecorder`.
- Scout runner: `crm/runner.py` — in-process background thread, cooperative cancel, active-slot.
- Existing REST API under `/crm`: leads CRUD, agent-runs CRUD, pipeline-run single-get, agents CRUD, discovery start/finish. No pipeline-runs **list** endpoint, no stats.
- DB: Postgres via SQLAlchemy + Alembic (`db/models.py`, `migrations/`).
- Prod: docker-compose (`app`, `litellm`, `postgres`, `redis`). Node.js used for Google Maps scraper.

## 3. Approach (decided)

- **React 18 + Vite + React Router + TypeScript** SPA in a new `web/` folder.
- Served as a **separate frontend service** (compose `web`: nginx serving built assets, proxying `/api` → `app:8000`). Dev: Vite dev-server proxy to `localhost:8000`.
- Backend exposes everything under a single `/api` prefix (existing `crm` router included) plus new endpoints.
- Scout chat persists to Postgres (`scout_threads`, `scout_messages`).
- Dark + bold accent visual: electric-violet → fuchsia signature, cyan secondary, sidebar + topbar layout.
- Legacy Jinja2 UI moved to `/legacy/*`; deleted only after the SPA is verified twice against it.

## 4. Data Model (new — Alembic `0004_scout_chat`)

```
scout_threads
  id UUID PK
  title TEXT
  created_at TIMESTAMP
  updated_at TIMESTAMP

scout_messages
  id UUID PK
  thread_id UUID (FK scout_threads.id)
  role VARCHAR(16)          -- user | assistant | tool
  content TEXT              -- assistant/user text; null for tool rows
  tool_name VARCHAR(64) NULL
  tool_args JSON NULL
  tool_result JSON NULL
  created_at TIMESTAMP
```

Tool messages store executed call + result so the UI can render tool-activity cards and the
audit trail survives reloads.

## 5. Backend API

New router `api/router.py` mounted at `/api`, including the existing `crm` router so one
consistent prefix serves the SPA: `/api/leads`, `/api/agent-runs`, `/api/agents`,
`/api/pipeline-runs`, etc.

New endpoints:
- `GET /api/pipeline-runs` — list missions (status, seed, head_assignment, timestamps, run count). New service `list_pipeline_runs()`.
- `GET /api/stats` — KPI aggregates: total leads, leads by status, avg lead_score, runs today, success rate, active scout, recent runs.
- `GET /api/scout/status` — active scout + latest missions (for topbar badge).
- `GET /api/scout/threads` — list threads.
- `POST /api/scout/threads` — create thread (`{title}` or auto).
- `GET /api/scout/threads/{id}/messages` — list messages in thread.
- `POST /api/scout/threads/{id}/messages` — send a user message; returns an **SSE stream**.
- `POST /api/scout/threads/{id}/cancel` — cancel the in-flight chat turn.

## 6. Scout Chat Engine

New `crm/scout.py` service (pure logic, no FastAPI) + SSE wiring in `api/`.

Per user message:
1. Load thread; load Scout profile (`agent_profiles.discovery`: own model, mission prompt, enabled tools).
2. Build OpenAI-style messages: mission as `system` → conversation history → new user message.
3. **Hybrid tool invocation**:
   - Primary: native OpenAI `tools=` function calling (Scout may request `web_search` / `google_maps_search`).
   - Fallback: if the model rejects `tools` (common on OpenRouter free models), retry with a JSON-decision prompt (same structured-prompt pattern the existing agents already use). Both paths yield the same tool-call objects.
4. Execute requested tools via `tools.registry.resolve_callable`; feed results back; **max 5 tool iterations**.
5. Final answer completion using the Scout's model.

`lm_client` gets one addition: a tool-capable completion that accepts `tools=` and returns
tool-call objects when the model requests them (used by the primary path); the existing
`chat_completion` stays for the JSON-fallback path and final answer.
6. Stream SSE events: `tool_start`, `tool_result`, `delta`, `done`, `error`; heartbeat to keep the connection alive.
7. Persist user + assistant + tool messages.

Concurrency: chat turns run per-thread; each turn has a `cancel_event`. Tool calls streamed
so the UI shows live progress. No interaction with `crm/runner.py`'s single active-slot —
chat is conversational and does not start the full pipeline recorder.

## 7. Frontend (React SPA)

Design tokens (CSS variables):
- bg `#0B0F17`, surface `#131926`, border `#1E2735`, text `#E6EDF7`, muted `#8B98AD`.
- Signature accent: electric-violet → fuchsia gradient (`#7C3AED → #D946EF`) for logo, active nav, buttons, Scout identity.
- Secondary: cyan `#22D3EE` for data/highlights.
- Status colors: success `#22C55E`, warning `#F59E0B`, danger `#EF4444`.

Layout:
- Fixed left sidebar: Dashboard, Scout HQ, Leads, Runs, Agents.
- Topbar: page title, live "Scout active" badge, LLM status dot.

Pages:
- `/` Dashboard — KPI cards (leads, avg score, runs today, success rate), active Scout widget + quick-start, recent runs feed.
- `/scout-hq` — split view: left mission board (missions list + start/finish Scout), right persisted chat with SSE streaming + tool-activity cards.
- `/leads` + `/leads/:id`.
- `/runs` + `/runs/:id`.
- `/agents` + `/agents/:name` (mission/tools editor).

State: TanStack Query for server state; fetch-stream reader for SSE chat. Plain CSS (no UI
framework) for full design control.

## 8. Deployment & Rollout

Build:
- `web/` Vite project. Prod Dockerfile (`web/Dockerfile`): build with Node, serve with `nginx:alpine`, proxy `/api` → `app:8000`.
- docker-compose adds `web` service (depends on `app`). Dev: Vite proxy to `localhost:8000`.

Rollout order (each phase independently verifiable):
1. Backend: migration + `list_pipeline_runs` + `/api/stats` + scout chat engine (mocked + live tests).
2. SPA shell + dark design system + Dashboard.
3. Leads / Runs / Agents pages.
4. Scout HQ (mission board + chat).
5. Mount legacy at `/legacy`, double-verify SPA parity, then delete Jinja2 UI.

Verification:
- Existing pytest suite still green; new tests for endpoints + chat engine (mocked `lm_client`, `web_search_tool`).
- Extended prod smoke test: `/api/stats`, scout chat ping, dashboard JSON.
- Manual SPA check against compose.
- Commit per phase.

## 9. Success Criteria

- Scout chat persists, streams, and can call live tools with visible tool-activity.
- All pages dark-redesigned and functional in the SPA.
- `/api/*` serves the whole platform.
- SPA verified twice against legacy before Jinja2 deletion.
- Prod compose boots `web` + `app`; existing backend tests green.

## 10. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| OpenRouter free models reject `tools=` | Hybrid fallback to JSON-decision prompt |
| SSE idle timeout | Heartbeat events + auto-reconnect |
| Chat turn hangs on slow tool (Maps ~30s) | Per-turn timeout + cancel endpoint |
| SPA parity gaps vs Jinja2 | Two-pass verification before legacy deletion |
| New `web` service build complexity | Standard Vite→nginx pattern, same as current single-artifact model |
