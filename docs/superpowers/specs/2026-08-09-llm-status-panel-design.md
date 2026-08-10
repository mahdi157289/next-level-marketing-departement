# LLM Provider Status Panel: Design Spec

> **Date:** 2026-08-09  **Status:** Implemented.
> **Stack:** Docker (app, web), FastAPI, React + TS + @tanstack/react-query.
> **Goal:** Add a toolbar button on both HQ pages (Scout + Head) that shows the active LLM provider, its API base URL, the model aliases per agent, and live reachability — never exposing the API key itself.

---

## 1. Context

The LLM runtime wiring lives entirely in `config/settings.py`:
- `openai_api_base` (Optional) — full OpenAI-compatible base URL. In Docker this is `https://openrouter.ai/api/v1`; an empty value means direct LM Studio (`lm_studio_base_url`).
- `lm_studio_base_url` — default `http://127.0.0.1:1234/v1`.
- `agent_model_discovery`, `agent_model_head` — model aliases per agent.
- `openai_api_key` — the bearer key.

`agents/lm_client.py::ensure_llm_reachable()` already performs a live reachability probe against the configured endpoint (models list + fallback tiny chat). Nothing currently exposes any of this to the SPA; the existing `/api/agents/{name}/providers` endpoint reports per-agent API *keys* (openai/serpapi/...), not the LLM runtime.

The frontend runs in a separate static `nginx` container, so LLM info must come from the backend.

## 2. Architecture Overview

```
ScoutHQ / HeadHQ toolbar
   │  LlmStatusPill (provider name + colored dot, polled)
   │  on click → drawer
   ▼
LlmStatusPanel ──► GET /api/llm/status ──► crm.service.llm_status()
                                          │   get_settings() provider/base_url/model aliases
                                          │   ensure_llm_reachable() live probe
                                          ▼
                          {provider, base_url, api_key_set, models[], reachable, detail, checked_at}
```

## 3. Backend

### 3.1 Service (`crm/service.py`)

`def llm_status() -> Dict[str, Any]`:
- `provider`: derived from settings — `openai_api_base` set → "OpenRouter" if the base contains `openrouter`, else "LiteLLM" if it contains `:4000` or `litellm`, else "OpenAI-compatible"; unset → "LM Studio (local)".
- `base_url`: `settings.openai_base_url()`.
- `api_key_set`: `bool(settings.openai_api_key)` and the configured value differs from the `"lm-studio"` default.
- `models`: `[{agent: "discovery", model: <agent_model_discovery>}, {agent: "head", model: <agent_model_head>}]`.
- `reachable` / `detail`: `ensure_llm_reachable()`.
- `checked_at`: ISO timestamp.
- The response must never include the raw API key.

### 3.2 Schema (`crm/schemas.py`)

`class LlmStatus(BaseModel)`:
- `provider: str`
- `base_url: str`
- `api_key_set: bool`
- `models: List[LlmModelAlias]` (nested: `agent: str`, `model: str`)
- `reachable: bool`
- `detail: str`
- `checked_at: str`

### 3.3 Endpoint (`api/router.py`)

- `GET /api/llm/status` → `service.llm_status()` with `response_model=schemas.LlmStatus`.
- No auth params; safe because it returns no secrets.

## 4. Frontend

### 4.1 API (`web/src/api/llm.ts`)

- `fetchLlmStatus(): Promise<LlmStatus>` → GET `/api/llm/status` via `apiGet`.
- Types added to `web/src/api/types.ts`: `LlmStatus`, `LlmModelAlias`.

### 4.2 Components

- `web/src/components/LlmStatusPanel.tsx`:
  - Takes `{ open, onClose }`; rendered inside a `.scout-drawer` on the HQ pages.
  - `useQuery(["llm-status"], fetchLlmStatus, { refetchInterval: 30_000 })`.
  - Shows provider, base URL, API-key-set badge, model list, reachability detail, checked-at time, and a "Refresh" button (`refetch`).
- `web/src/components/LlmStatusPill.tsx`:
  - A `.btn` in the toolbar labeled with the provider name plus a colored dot (`.dot.ok` green, `.dot.err` red, `.dot.pending` amber when loading).
  - Shares the same `["llm-status"]` query so the pill and drawer stay consistent.

### 4.3 Wiring

- `ScoutHQ.tsx`: toolbar gains a "LLM" status pill; `open === "llm"` renders `LlmStatusPanel` in a drawer.
- `HeadHQ.tsx`: same.
- `scout.css`: `.llm-dot`, `.llm-dot.ok/.err/.pending`, `.llm-status-row` styles.

## 5. Error handling

- Probe failure → red dot; panel shows `detail` explaining why unreachable.
- Query error (backend down) → pill shows amber/pending; drawer shows an error message and Refresh retries.
- No secret leakage: only `api_key_set` boolean is exposed.

## 6. Testing

### Backend

`tests/test_llm_status.py` (hermetic, monkeypatch settings):
- Provider detection: OpenRouter base, LiteLLM base, OpenAI-compatible base, and unset → LM Studio.
- `api_key_set` true/false; response contains no raw key.
- Models list contains discovery + head aliases.
- `ensure_llm_reachable` result flows into `reachable`/`detail`.
- `/api/llm/status` endpoint returns 200 with expected fields (monkeypatch `ensure_llm_reachable` to avoid network).

### Frontend

- `web/src/components/LlmStatusPanel.test.tsx`: renders provider/base URL/models; refresh refetches; error shows retry.
- `web/src/pages/ScoutHQ.test.tsx` / `HeadHQ.test.tsx`: mock `fetchLlmStatus`; pill renders; drawer opens/closes.

### Verification commands

- Backend: `python -m pytest tests/test_llm_status.py -q`.
- Frontend: `npm test -- --run` + `npm run build` (workdir `web`).
- Live: `docker compose build web && docker compose up -d web`; open Scout/Head HQ, click the LLM pill, confirm provider/base URL/models/reachability.

## 7. Out of scope

- Editing LLM config from the UI.
- Per-agent provider key management (already in AgentsDetail).
- LLM chat-model switching or multiple concurrent providers.
