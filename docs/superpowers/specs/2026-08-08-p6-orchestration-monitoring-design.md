# P6 — Orchestration + Monitoring: Design Spec

> **Date:** 2026-08-08  **Status:** Design approved (mockup v3) — plan pending.
> **Branch:** `feat/scout-hq-backend`. **Stack:** Docker (postgres, janusgraph, redis, litellm, app, web), Windows host.
> **Goal:** Make the agents actually use the RAG/graph brain they already advertise, add concurrent async dispatch, and surface brain/monitoring telemetry on the Dashboard.

---

## 0. Context

P4 delivered the brain but **no agent calls it**. `knowledge/rag.py::scoped_query` (cache → pgvector → graph-expand → cache, with `brain_query_metrics`) exists only behind `/api/brain/*`. The prompt files (`prompts/discovery.md:13-15`, `prompts/head.md:8-11`) already tell the models about a "RAG index" and "scoped slices (`prospects`)" that no code implements — P6 makes the prompts honest.

The spec's P6 row says "scoped retrieval filters, Redis cache, async batch dispatch, `brain_query_metrics`". Redis cache + `brain_query_metrics` were already delivered in P4; this phase covers the remainder: **agent retrieval wiring, async batch dispatch, and a Dashboard monitoring card**.

## 1. Architecture Overview

Three subsystems, each independently testable:

1. **Retrieval wiring** — one shared helper `knowledge/retrieval.py::build_brain_context` injects scoped brain results into the four agents' prompt builds. Reads each agent's `default_domain` profile field.
2. **Async dispatch** — `crm/orchestrator.py`: an N-worker `ThreadPoolExecutor` (default 3) with a per-agent runner registry, Postgres-backed queue state, and a new `POST /api/agents/{name}/batch` endpoint.
3. **Monitoring UI** — a `BrainHealthCard` on the Dashboard (lamps + telemetry + recent brain requests), backed by new frontend `api/brain.ts` and one new backend endpoint (`GET /api/brain/worker/status`).

```
Agent prompts (scout/head/discovery/qualifier)
   │  build_brain_context(agent, query)            ──► knowledge/rag.py::scoped_query
   │                                                    │ cache(redis) → pgvector → graph
   │                                                    ▼
   └── prompt + context block                    brain_query_metrics (+ query column)
                                                       │
Dispatcher: POST /api/agents/{name}/batch  ──► crm/orchestrator.py (N workers)
                                                       │ pipeline_runs (queued/running/...)
                                                       ▼
Dashboard: BrainHealthCard ◄── /api/brain/worker/status + /api/brain/metrics + /api/brain/graph/status
```

## 2. Retrieval wiring

### 2.1 New `knowledge/retrieval.py`

```python
def default_domain(agent_name: str) -> str:
    """AgentProfile.default_domain, else 'global'."""

def build_brain_context(agent_name: str, query: str, limit: int = 5) -> str:
    """scoped_query(agent_name, default_domain(agent_name), query, limit).
    Formats non-empty results into:
      ## Brain context
      - [chunk|lead] <content> (<source>)
    Returns "" when no results. Never raises (scoped_query degrades internally).
    """
```

- Reuses `scoped_query` exactly — so agent retrieval automatically hits the Redis cache and writes `brain_query_metrics` rows.
- Function-local imports (`from knowledge.rag import scoped_query`) to keep the patch target testable (established convention from P4).
- Query is truncated client-side in the helper to ~200 chars before `scoped_query`? No — `scoped_query`'s cache key already hashes the full query; truncation happens only for the new `query` column (see §2.3).

### 2.2 `AgentProfile.default_domain`

- Migration `0008` adds nullable `default_domain` to `agent_profiles`.
- `get_agent_profile` / `update_agent_profile` expose it (service layer, same pattern as `default_seed_query`).
- SPA agent-detail form gains a "Default brain domain" text input (like `default_seed_query`). Frontend field in `AgentProfileUpdate` schema.

### 2.3 `brain_query_metrics.query` column

To show "what the agent asked for" in the UI, `record_query` must persist the query text (today it stores only a hash). This changes:

- Migration `0009`: add nullable `query` to `brain_query_metrics`.
- `db/brain_metrics.py::record_query` gains a `query: Optional[str]` param (insert it); `recent_queries` SELECT includes it.
- `knowledge/rag.py::scoped_query` passes a truncated query (`query[:200]`) to `record_query` on both the cache-hit and cache-miss paths.
- `crm/service.py` passthroughs (`record_brain_query`) if any — none exist today; the only caller is `scoped_query`. Existing tests `test_brain_metrics.py`, `test_rag.py`, `test_brain_api.py` update for the new arg/column.

### 2.4 Injection points (4 sites)

| Agent | File:line | Where | Query used |
|---|---|---|---|
| Scout | `crm/scout.py:131` | first `system` message list | latest user chat message |
| Discovery | `agents/discovery_agent.py` `_llm_report` (~:320) | prompt content | seed query |
| Head | `agents/head_agent.py` `_plan_core` (~:143) + `_llm_report` (~:203) | plan + report | mission / seed |
| Qualifier | `agents/qualifier_agent.py` `_DEFAULT_MISSION` (~:41) | mission prompt | lead name / URL |

Each site: `ctx = build_brain_context("discovery", query); if ctx: messages/prompt += ctx`. Empty context → no change to existing behavior.

## 3. Async batch dispatch — `crm/orchestrator.py`

### 3.1 Worker pool

- `WorkerPool` singleton: `ThreadPoolExecutor(max_workers=N)` with `N` from settings `orchestrator_workers` (default 3).
- `enqueue_run(agent_name, seed_query, mission=None) -> Dict` (the run dict):
  - Creates a `PipelineRun` via `service.start_pipeline_run(trigger=f"agent:{agent_name}", meta={mission, from_agent:agent_name, mode:"dispatch"})` (existing helper — status starts `running`; workers re-claim at startup, see §3.3).
  - Submits to the pool: worker executes `_RUNNERS[agent_name](run_id, seed_query, mission)`.
  - Returns the run.
- `_RUNNERS` registry (per-agent runner functions):
  - `discovery` → thin wrapper over `crm/runner.py::start_discovery_scout` internals: instead of creating its own `PipelineRun`, the orchestrator passes the pre-created `pipeline_run_id` and `recorder` so the run lifecycle is owned by the queue. Implemented as `_run_discovery(run_id, seed, mission)` calling `workflows.discovery_only.run_discovery_only(...)` with a recorder bound to `run_id` (mirrors `runner.py::_worker` body but using the queue-owned run).
  - `head` → `_run_head(run_id, seed, mission)`: instantiates `agents/head_agent.py::HeadAgent` and runs its plan+report path, recording via `AgentRunRecorder` bound to `run_id`.
  - `qualifier` → `_run_qualifier(...)`: runs the qualifier agent the same way.
- Each runner wraps in `try/except`: on failure calls `service.complete_pipeline_run(run_id, "failed", {error})`; on success `"success"`.

### 3.2 What stays as-is

- **`POST /api/agents/{agent_name}/dispatch`** (single) is rewritten to call `orchestrator.enqueue_run` for every agent (previously: discovery → live single-slot; others → record-only). Keeps the same response shape (`PipelineRunOut`) so the SPA is unaffected.
- **`POST /api/agents/discovery/start`** (Scout HQ) keeps using `crm/runner.py::start_discovery_scout` (single-slot + cooperative cancel for the interactive Scout HQ). The orchestrator's discovery runner is a separate path for batch dispatch. Rationale: preserve the existing cancel/Finish UX on Scout HQ without entangling the new pool.
- **`crm/runner.py`** `get_active`/`request_finish` untouched.

### 3.3 Recovery

- On module import / app start, the orchestrator re-claims stale `running` runs (status `running`, `finished_at IS NULL`, trigger `agent:%`) and marks them `failed` with meta `{error: "app restarted mid-run"}`. Simple, honest, no job-loss complexity.

### 3.4 New endpoint

- `POST /api/agents/{name}/batch` body `{missions: [{seed_query, mission}]}` (new schema `BatchDispatchRequest`) → enqueues each, returns `{runs: [PipelineRunOut...]}` (201).
- Registered on `api/router.py` (next to the single `dispatch`), not `crm_router`, matching the existing generic-dispatch home.

## 4. Monitoring UI

### 4.1 Backend: `GET /api/brain/worker/status`

New route in `api/brain_router.py` returning:

```json
{"active": 2, "max_workers": 3, "queued": 1}
```

`active` = running pool tasks (`orchestrator.active_count()`), `queued` = submitted-not-started (`orchestrator.queued_count()`), `max_workers` from settings.

### 4.2 Frontend

- New `web/src/api/brain.ts`: `fetchBrainStatus()` → `GET /api/brain/graph/status`; `fetchBrainMetrics(limit)` → `GET /api/brain/metrics`; `fetchWorkerStatus()` → `GET /api/brain/worker/status`.
- New types in `web/src/api/types.ts`: `BrainMetric` (id, agent_name, domain, query, latency_ms, cache_hit, vector_hits, graph_hits, created_at), `BrainStatus`, `WorkerStatus`.
- New `web/src/components/BrainHealthCard.tsx` rendered on `Dashboard.tsx` below the KPI grid, auto-refresh via `useQuery` `refetchInterval` (8s, matching scout-status):
  - **Lamps row** (reuse the exported `Lamp` component from `web/src/pages/Tools.tsx`): `RAG` (embedding skill green from `POST /api/agents/tools/health`), `Graph` (from `fetchBrainStatus` → available), `Cache` (redis ping — derive from `/api/agents/tools/health` if a redis skill exists, else `available` from metrics having rows; simplest: green when `fetchBrainMetrics` returns without error).
  - **Telemetry strip**: cache-hit % (cache_hit true/total over the window), avg latency ms, workers `active/max`, queued count.
  - **Recent brain requests table**: rows from `fetchBrainMetrics(10)` — columns `Agent | Asked for | Hit | Started | Took`. `Hit` = `graph×N` if graph_hits>0 else `vector×N` if vector_hits>0 else `cache` if cache_hit else `—`. `Took` color: <200ms green, ≥200ms amber.
- Empty state: "No brain activity yet" when no metric rows.

### 4.3 No other Dashboard changes

Recent missions, KPIs, Active Scout panel unchanged.

## 5. Settings

- `orchestrator_workers: int = 3` (new field, `config/settings.py`).

## 6. Tests

Backend (`tests/`, follow existing conventions — flat files, DB-gated `skipif`, `TestClient(app)`, function-local imports for patchability):

- `tests/test_retrieval.py` — `default_domain` (profile field / fallback), `build_brain_context` formats results, returns `""` on empty results and when `scoped_query` is patched to raise (never raises).
- `tests/test_brain_metrics.py` — update: `record_query(..., query=...)` round-trips the query text.
- `tests/test_rag.py` — update: assert `record_query` receives the truncated query on miss and hit paths.
- `tests/test_brain_api.py` — update metrics shape to include `query`.
- `tests/test_orchestrator.py` — `enqueue_run` calls the runner for each agent, records success/failed on the PipelineRun, unknown agent → ValueError; runner registry maps all four agents; worker status counts.
- `tests/test_batch_dispatch.py` (DB-gated) — `POST /api/agents/head/batch` with 2 missions returns 2 runs; runs reach `success` (mock the runner functions so no LLM runs).
- `tests/test_brain_api.py` — add `GET /api/brain/worker/status` shape (mock orchestrator counts).

Frontend (`web/src`, vitest + testing-library):

- `components/BrainHealthCard.test.tsx` — renders lamps + telemetry + request rows; empty state.
- `pages/Dashboard.test.tsx` — update to include the new card (mock `api/brain.ts`).

## 7. Risks log

- **Discovery has two run paths** (Scout HQ single-slot vs orchestrator batch). Kept separate deliberately; the batch discovery path must reuse `run_discovery_only` with a queue-owned recorder. Watch for double `AgentRun`/`PipelineRun` records in tests.
- **`record_query` signature change** touches P4 tests; update together with the column migration so the suite stays green at each commit.
- **Thread pool + `--reload`**: app `--reload` (uvicorn) restarts the process → workers die; recovery (§3.3) marks stale runs failed on next start. Acceptable for this phase.
- **LLM reachability**: batch dispatch of head/qualifier/discovery requires the LLM provider; runners surface failures as run `failed` rather than raising (consistent with current runner behavior).
