# Agent Platform v2 — Design Spec

> **Date:** 2026-08-07  **Status:** Implementation started (Phase 1 live).
> **Branch:** `feat/scout-hq-backend`. **Stack:** Docker (postgres:16, litellm, redis, app, web), Windows host.
> **Goal:** Make the agents behave like defined personas (system prompt `agent.md`) with explicit rules, plus a shared RAG+Graphify brain, per-agent memory, and a supervisor UI. "No paid APIs / local LLM only."

---

## 0. Phases (delivered one at a time, each production-verified in the running stack)

| Phase | Scope | Container change | Status |
|---|---|---|---|
| P1 | System-prompt `agent.md` (file-backed) + loader; dispatch w/ mission `meta`; secret-store table scaffold | none | **in progress** |
| P2 | Per-agent persistent memory + lesson reports | none | planned |
| P3 | RAG (pgvector) brain — local Postgres `vector` extension | postgres image → `pgvector/pgvector:pg16` + `CREATE EXTENSION` | planned |
| P4 | Graphify (JanusGraph+BerkeleyDB) brain + scoped retrieval + cache + metrics | add `janusgraph` service | planned |
| P5 | Provider/API-key inputs (hashed) + catalog UI | none | planned |

P1 is built **first** because it fixes the core complaint (vague persona + "tools not listed") with zero infra risk on the live, working stack.

---

## 1. P1 — System-prompt `agent.md` + dispatch metadata

### 1.1 Files
- `prompts/discovery.md` — Scout (Discovery) system prompt: explicit persona, the 5-iteration cap, RAG+memory brain, the tool whitelist (only what's `enabled_tools`), qualified-prospect rules (company name + business needing our services; skip dirs/news/social/Wikipedia; match our 5 service categories: development/data/marketing/automation/migration), output format (markdown bullets or tool calls only).
- `prompts/head.md` — Head Agent system prompt: librarian/manager persona, scoped-retrieval rules ("Discovery sees `prospects` slice only"), dispatch rules ("dispatch via /pipeline-runs with meta.mission"), memory rules ("read/write each agent's memory; lesson summaries stay reports"), terse output.

### 1.2 Resolution order (code) — DONE (verified live)
`knowledge/prompts.py::load_agent_prompt(agent_name, db_prompt)` precedence:
1. **DB `mission_prompt`** if it is non-empty **and customized** (i.e. not the seeded legacy prompt — see `_SEED_DEFAULTS`). This is the operator override written via the SPA.
2. Else the **file-backed** `prompts/<agent_name>.md` (the authoritative `agent.md`).
3. Else the hardcoded fallback constant (`"You are the Scout."` / `"You are the Head Agent."`).

Why this order: on a stock install the DB holds the seeded default prompt, which is treated as "not customized," so the `agent.md` file takes effect automatically. An operator who edits the prompt in the SPA writes a *different* string, which then overrides the file. File is authoritative-by-default; DB is explicit override. Never raises (file missing → fallback).

Verified live: `load_agent_prompt("discovery", <seeded DISCOVERY_MISSION>)` returns the contents of `prompts/discovery.md`.

### 1.3 Engine wiring — DONE
- `crm/scout.py`: `run_scout_turn` resolves `profile["mission_prompt"] = load_agent_prompt("discovery", profile.get("mission_prompt"))` via `knowledge.prompts.scout_profile_with_prompt`; the persona is injected as the first `system` message.
- `agents/head_agent.py`: `HeadAgent.__init__` resolves its prompt via `load_agent_prompt("head", ...)`.

### 1.4 Dispatch w/ mission metadata — DONE (verified live)
- `crm/schemas.py`: `DiscoveryStartRequest` gained `mission: Optional[str]`.
- `crm/router.py`: `/api/agents/discovery/start` passes `mission` → `runner.start_discovery_scout`.
- `crm/runner.py`: `start_discovery_scout(..., mission=None)` stores `mission` in the run `meta`.
- **New** `POST /api/agents/{agent_name}/dispatch` body `{seed_query, mission?}`:
  - `discovery` → delegates to `runner.start_discovery_scout` (live scout), returns the full `PipelineRunOut` (looked up via `service.get_pipeline_run`).
  - other agents → `service.dispatch_agent_task` records a `PipelineRun` with `meta={mission, from_agent, mode:"dispatch"}` (execution left to the agent's own start endpoint/scheduler). Returns `PipelineRunOut`.
  - unknown agent → 404.

### 1.5 Tests — DONE (8/8)
- `tests/test_prompt_loader.py`: DB customizable override wins over file; seeded-default DB prompt falls through to file; empty DB → file; file missing → fallback constant; `file_prompt` returns `""` when absent; `scout_profile_with_prompt` is non-mutating and resolves.
- `tests/test_dispatch_meta.py` (DB-gated): `head` dispatch persists `meta.mission`/`from_agent`/`mode`; unknown agent → 404. (discovery dispatch is not exercised by the unit test to avoid launching a live LLM run.)

### 1.6 Verify (live stack) — DONE
1. Edited `prompts/discovery.md` → app `--reload` picked it up → created a thread + sent a Scout chat message, got 33 SSE frames (`start → 31× delta → done`), assistant replied.
2. Confirmed via direct call: DB has seeded `DISCOVERY_MISSION`; `load_agent_prompt("discovery", <seed>)` returns the file content (`prompts/discovery.md`).
3. `POST /api/agents/head/dispatch {seed_query: null, mission:"..."}` → 201 with `id`; `SELECT meta` shows `mission`/`from_agent`/`mode` persisted.
4. `POST /api/agents/nope/dispatch` → 404. Frontend `npm test` + `npm run build` unaffected by P0 backend (no SPA change in this phase).

---

## 2. Skeletons for later phases (forward-compatible)

---

## 2. Skeletons for later phases (so P1 stays forward-compatible)

### P2 — per-agent memory (`agents/memory_v2.py`)
- `append_interaction(agent_name, role, text)`, `get_summary(agent_name)`, `search_memory(agent_name, query)`.
- `GET /api/agents/{name}/memory/report`.
- Wired into scout/head message list as an extra `system` block (`## Your recent notes\n{summary}`).

### P3 — RAG brain (pgvector)
- Switch compose `postgres` image to `pgvector/pgvector:pg16`, migration adds `Vector(768)` column on `vector_embeddings(agent_name, domain, scope, text, embedding)`.
- `knowledge/vector.py` (upsert + scoped similarity search), `knowledge/ingest.py` (chunks `company_profile.md` + leads into `domain="prospects"` slices).

### P4 — Graphify (JanusGraph) brain
- `docker-compose.yml`: `janusgraph` (BerkeleyDB, :8182). `knowledge/graph.py` (ingest company/services/leads/runs; traversal queries); `knowledge/rag.py::scoped_query(agent_name, domain, query)` = cache → pgvector → graph-expand → cache. Redis cache (`brain:{agent}:{domain}:{sha256}`) + `brain_query_metrics`.

### P5 — UI
- Agent hub page per agent (prompt editor "load from agent.md", tool toggles, green lamp, chat, providers/keys).
- `/tools` catalog page; dashboard provider-card + brain-health card.

## 3. Risks log
- **P3 postgres image swap** will restart the DB; the running prod backend will drop briefly. Will schedule the image swap + `CREATE EXTENSION vector` + migration as an explicit, communicated step (data volume persists).
- JanusGraph (P4) is a JVM container — heavy. Will keep it off by default in compose (`profiles: ["brain"]`) so it only runs when RAG/graph is actively used.
