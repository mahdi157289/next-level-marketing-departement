# Agent Chat + Editable agent.md (Head & Qualifier): Design Spec

> **Date:** 2026-08-08  **Status:** Design approved — pending implementation.
> **Stack:** Docker (postgres, janusgraph, redis, litellm, app, web), Windows host, React + TS + @tanstack/react-query, FastAPI.
> **Goal:** Let the operator talk to the Head and Qualifier agents directly in a chat UI (same experience as Scout), and let them author each agent's role via an editable `agent.md` file (already half-supported via `prompts/*.md`).

---

## 0. Context

Scout (the `discovery` agent) already has a full chat: persisted threads/messages in `scout_threads`/`scout_messages`, SSE streaming via `POST /api/scout/threads/{id}/messages`, tool calls, and a `ScoutChat.tsx` UI. File-backed system prompts already exist (`prompts/discovery.md`, `prompts/head.md`) resolved by `knowledge/prompts.py::load_agent_prompt` with precedence **DB override → file → fallback**.

Head and Qualifier have **no chat** and **no editable prompt**: their system prompts are hardcoded (`_PLAN_MISSION` / `_DEFAULT_MISSION`) or resolved from the file/DB only for head via `HeadAgent.__init__`. Qualifier has **no agent profile row** and no `prompts/qualifier.md`.

This phase generalizes the scout chat pipeline to be agent-agnostic and adds an `agent.md` editor, targeting **head** and **qualifier**.

## 1. Architecture Overview

Two subsystems:

1. **Agent-agnostic chat** — reuse scout's thread/message/SSE machinery. Add `agent_name` to the thread/message tables, parameterize the chat engine (`crm/scout.py::run_scout_turn` → shared `run_agent_turn`), expose agent-scoped REST+SSE endpoints (`/api/agents/{name}/threads*`), and extract the generic `AgentChat` frontend component.
2. **Editable system prompt (agent.md)** — a `GET/PUT /api/agents/{name}/prompt` API that reads/writes `prompts/{name}.md` (same resolution the agents already use), plus an `AgentPromptEditor` UI panel on the agent detail page.

```
AgentChat.tsx (generic) ──► /api/agents/{name}/threads*  ──► crm/scout.run_agent_turn(name, ...)
                                    │                             │ load_agent_prompt(name) → prompts/{name}.md
                                    │                             │ enabled_tools filtered tool schemas
                                    └── scout_threads/messages (+ agent_name column)

AgentPromptEditor.tsx ──► GET/PUT /api/agents/{name}/prompt  ──► prompts/{name}.md (file on disk)
```

## 2. Chat backend

### 2.1 Schema — `agent_name` column

- Migration `000X`: add nullable `agent_name` String column to `scout_threads` and `scout_messages`, defaulting to `'discovery'` for existing rows.
- `db/models.py`: `ScoutThread.agent_name = Column(String(32), default="discovery", nullable=False)`, same for `ScoutMessage`.
- Existing scout rows backfill to `'discovery'`; new threads always carry the agent.

### 2.2 Service layer (`crm/service.py`)

- `create_scout_thread(title=None, agent_name="discovery")` — stores agent_name.
- `list_scout_threads(agent_name="discovery", limit=50)` — filters by agent_name.
- `add_scout_message(...)` — gains `agent_name="discovery"` param, stores it.
- `list_scout_messages(thread_id, limit=200)` — unchanged (threads are per-agent already via ownership).
- Scout callers keep defaults, so existing behavior is identical.

### 2.3 Chat engine (`crm/scout.py`)

- Introduce `run_agent_turn(agent_name, thread_id, user_text, *, max_tool_iterations=..., profile=None)`:
  - `profile` default = `_load_agent_profile(agent_name)`:
    - `model`: `get_agent_profile(agent_name).model` else settings (`agent_model_discovery` for discovery, `agent_model_head` otherwise).
    - `mission_prompt`: `load_agent_prompt(agent_name, profile.get("mission_prompt"))`.
    - `enabled_tools`: profile's list (default `["llm_chat"]` when none).
  - Tool advertising: filter `_TOOLS_SCHEMA` to `enabled_tools` (as today); with head/qualifier defaults that's just `llm_chat` → no advertised tools → pure chat.
  - System prompt build appends brain context (`build_brain_context(agent_name, ...)`) — already generic.
  - Records user/assistant/tool messages via `add_scout_message` with `agent_name`.
- `run_scout_turn(thread_id, user_text, ...)` becomes a thin wrapper: `run_agent_turn("discovery", ...)`. Keep the `profile` passthrough so existing tests still inject profiles.
- `_load_scout_profile` stays (wraps `_load_agent_profile("discovery")` or is inlined); scout callers in `crm/scout.py` and tests keep working.

### 2.4 API (`api/router.py`)

- `GET /api/agents/{name}/threads?limit=` → `list_scout_threads(agent_name=name)`.
- `POST /api/agents/{name}/threads` `{title?}` → `create_scout_thread(title, agent_name=name)`.
- `GET /api/agents/{name}/threads/{thread_id}/messages` → `list_scout_messages(thread_id)`.
- `POST /api/agents/{name}/threads/{thread_id}/messages` `{content}` → SSE stream via shared `_agent_chat_events(name, thread_id, content)` (identical frame shape to scout: `start`/`delta`/`done`/`error`), calling `run_agent_turn(name, ...)` in `asyncio.to_thread`.
- Validate `name` in `{head, qualifier, discovery}` (400 otherwise). Keep the existing `/scout/*` routes untouched (they delegate to the same service/engine).

## 3. Editable system prompt (agent.md)

### 3.1 Prompt resolution (`knowledge/prompts.py`)

- Add `_DEFAULT_QUALIFIER_PROMPT` fallback (current qualifier `_DEFAULT_MISSION` text).
- `_fallback("qualifier")` returns it. `discovery`/`head` unchanged.
- Create `prompts/qualifier.md` seeded with the current qualifier mission text (so the file becomes the source of truth, matching head/discovery).

### 3.2 Prompt editor API

- `GET /api/agents/{name}/prompt` → `{agent_name, exists, content, resolved_prompt}` where `content` is the raw file (or `""`), `resolved_prompt` is `load_agent_prompt(name, None)` for preview. Validates `name in {head, qualifier, discovery}`.
- `PUT /api/agents/{name}/prompt` `{content}` → writes `prompts/{name}.md` (via `knowledge.prompts.prompt_dir()`), returns the same GET shape. Empty content allowed (deletes authority → falls back to DB/constant).
- Note: file writes hit the app container's mounted repo (same as existing `PROMPT_DIR` behavior); a git diff shows the change.

### 3.3 UI note on precedence

- The existing DB `mission_prompt` override wins over the file. The editor shows `resolved_prompt` and a hint: "If a DB profile override exists, it takes precedence; edit the profile Mission prompt to clear it."

## 4. Frontend

### 4.1 `web/src/api/agent-chat.ts` (new)

Mirror `scout.ts` with an agent_name arg:
- `fetchAgentThreads(agentName)` → GET `/api/agents/{name}/threads?limit=50`
- `createAgentThread(agentName, title?)` → POST
- `fetchAgentMessages(agentName, threadId)` → GET messages
- `streamAgentTurn(agentName, threadId, content, handlers)` → POST with SSE parse (reuse `takeFrames` from `api/sse.ts`).

### 4.2 Generic `AgentChat` component

- Extract `ScoutChat.tsx` into `web/src/components/AgentChat.tsx` taking `{ agentName: string; label: string }`.
- Reuses `useScoutChat` hook generalized (or a parallel `useAgentChat`) — prefers generalizing the existing hook to keep streaming behavior identical.
- `ScoutHQ.tsx` keeps using it (Scout = `agentName="discovery"`, label "Scout").
- `AgentsDetail.tsx` mounts it for head + qualifier.

### 4.3 `AgentPromptEditor` component

- `useQuery(["agent-prompt", name])` → `fetchAgentPrompt(name)`; textarea pre-filled; Save → `PUT` via mutation; flash success/error; shows `exists`/`resolved_prompt` hint.
- `web/src/api/agent-chat.ts` (or `agents.ts`) exports `fetchAgentPrompt`/`saveAgentPrompt`.
- `AgentsDetail.tsx` mounts it for head + qualifier.

### 4.4 Types (`web/src/api/types.ts`)

- `AgentPrompt` `{agent_name, exists, content, resolved_prompt}`.
- Reuse `ScoutThread`/`ScoutMessage` shapes for agent threads/messages.

## 5. Error handling & degradation

- Chat endpoint: unknown agent → 400; bad thread UUID → 422 (matches scout). Engine never raises to caller on LLM/tool failure (existing `_run_fallback_tools` / try/except patterns).
- Prompt GET: missing file → `{exists: false, content: ""}` (200), not 404. PUT: filesystem errors → 500 with detail.
- `build_brain_context` / graph/Redis failures degrade to `""` / empty (existing behavior) — chat still works when the brain is down.

## 6. Testing

### Backend

- `tests/test_agent_chat.py` (hermetic, monkeypatched like `test_scout_engine.py`): `run_agent_turn("head")` uses head model + `load_agent_prompt("head")`; tool advertisement filters to `enabled_tools`; messages persist with `agent_name`.
- `tests/test_agent_chat_api.py` (TestClient, hermetic where possible): list/create/messages routes scoped by agent; unknown agent → 400; SSE `POST` streams frames (mock `run_agent_turn`).
- `tests/test_agent_prompt_api.py`: GET missing → `exists:false`; GET/PUT round-trip against a temp `PROMPT_DIR` (monkeypatch env + reload `prompts`); PUT writes file; unknown agent → 400.
- Update `tests/test_scout_engine.py` / `tests/test_dispatch_meta.py` if any signature changes ripple (they shouldn't — defaults preserved).
- Migration test/`alembic upgrade head` + verify columns.

### Frontend

- `web/src/api/agent-chat.test.ts` (fetch stubs): URLs include `{name}`.
- `web/src/components/AgentChat.test.tsx` (mirrors existing ScoutChat/useScoutChat tests): threads, streaming, tool activity, error flash.
- `web/src/components/AgentPromptEditor.test.tsx`: loads prompt, saves, flash, precedence hint.
- `web/src/pages/AgentsDetail.test.tsx`: renders chat + editor panels for head/qualifier.

### Verification commands

- Backend: `python -m pytest tests/ -q --no-header` (full suite) after `docker exec marketing_app python -m alembic upgrade head`.
- Frontend: `npm test -- --run` + `npm run build` (workdir `web`).
- Live: `docker compose build web && docker compose up -d web`; open an agent detail page, send a chat message, edit the agent.md, confirm the chat uses the new prompt.

## 7. Out of scope

- Replacing the Scout chat UI (it is reused, not rewritten).
- Tool execution for qualifier in chat (only `llm_chat` enabled by default; tool advertising is purely driven by `enabled_tools`).
- Changing DB `mission_prompt` override semantics.
- Agent memory / cross-agent context.
- Chat for any future agent not in `{head, qualifier, discovery}` (the `name` allowlist is explicit).
