# Agent Roster Pages (all agents) — Design Spec

> **Date:** 2026-08-08  **Status:** Implemented (committed).
> **Stack:** Docker (postgres, janusgraph, redis, litellm, app, web), Windows host, React + TS + @tanstack/react-query, FastAPI.
> **Goal:** Give every agent in the department a dedicated page (not just Scout/Head HQs). Planned-but-unbuilt agents get working pages too, so their system prompt and provider keys can be configured ahead of implementation.
> **Scope note:** This phase ships the roster + pages only. The per-agent **LLM provider** card (model + base URL + API key) and the runtime wiring so agents use their own LLM config are **deferred** to a follow-up phase.

---

## 1. Agent roster

The department roster comes from `docs/crm/README.md` and `docs/crm/AGENT_INTEGRATION.md`:

| name | display_name | Status today | Page today |
|---|---|---|---|
| `discovery` | Discovery (Scout) | live | Scout HQ + `/agents/discovery` |
| `head` | Head (Supervisor) | live | Head HQ + `/agents/head` |
| `qualifier` | Qualifier | live (orchestrator, `prompts/qualifier.md`, no DB row) | `/agents/qualifier` 404s |
| `categorization` | Categorization | planned | — |
| `analysis` | Analysis | planned | — |
| `outreach` | Outreach | planned | — |
| `content` | Content | planned | — |

Only `discovery` and `head` have `agent_profiles` DB rows. `get_agent_profile` returns `None` for the rest, so `/api/agents/{name}` 404s and the detail page never renders.

## 2. Backend changes

### 2.1 New `crm/agents_registry.py`

A static roster constant (name is the key; a profile row can override display_name/etc.):

```python
AGENT_ROSTER = [
    {
        "name": "discovery", "display_name": "Discovery (Scout)",
        "description": "Searches the web/maps/ad library and writes leads.",
        "default_tools": ["web_search", "google_maps_search", "meta_ads_search", "crm_write_leads", "llm_chat", "scrape"],
        "providers": ["openai", "serpapi", "google_maps", "meta_ads"],
    },
    {
        "name": "head", "display_name": "Head (Supervisor)",
        "description": "Plans missions and dispatches subordinate agents.",
        "default_tools": ["llm_chat"], "providers": ["openai"],
    },
    {
        "name": "qualifier", "display_name": "Qualifier",
        "description": "Scores and qualifies leads against the service catalog.",
        "default_tools": ["llm_chat"], "providers": ["openai"],
    },
    {
        "name": "categorization", "display_name": "Categorization",
        "description": "Tags leads with country, industry, business type.",
        "default_tools": ["llm_chat"], "providers": ["openai"],
    },
    {
        "name": "analysis", "display_name": "Analysis",
        "description": "Enriches leads with SEO score, email, phone, lead score.",
        "default_tools": ["llm_chat"], "providers": ["openai"],
    },
    {
        "name": "outreach", "display_name": "Outreach",
        "description": "Contacts leads (planned: SMTP/WhatsApp).",
        "default_tools": ["llm_chat"], "providers": ["openai", "smtp", "whatsapp"],
    },
    {
        "name": "content", "display_name": "Content",
        "description": "Produces marketing content (planned: WordPress/social).",
        "default_tools": ["llm_chat"], "providers": ["openai", "wordpress"],
    },
]

def roster_names() -> set[str]: ...
def roster_entry(name: str) -> dict | None: ...
```

`providers` is metadata only in this phase (the provider-keys panel keeps its fixed `KNOWN_PROVIDERS` list; per-agent provider filtering ships with the LLM phase).

### 2.2 `crm/service.py`

- `list_agent_profiles()`: return DB rows first, then append roster entries whose `name` is not present (each with `available_tools = catalog_for_agent(name)`).
- `get_agent_profile(name)`: DB row if present; otherwise return roster defaults as a profile-shaped dict (`display_name`, `mission_prompt=None`, `enabled_tools=default_tools`, `model=None`, `default_seed_query=None`, `default_domain=None`, `updated_at=None`, `available_tools=catalog_for_agent(name)`).
- `update_agent_profile(name, data)`: **upsert** — insert a fresh row when none exists, then apply the patch. This makes `PATCH /api/agents/qualifier` (and planned agents) create a real profile row on first edit.

### 2.2b `tools/registry.py`

Roster agents default to `enabled_tools: ["llm_chat"]`, and `update_agent_profile` validates `enabled_tools` via `validate_tool_ids(..., agent_name=...)`. Today `llm_chat` is advertised for `["discovery", "head"]` only, so `catalog_for_agent("qualifier")` is empty and validation would reject it. Expand the `llm_chat` catalog entry's `agents` to all roster names (or compute it from the roster) so chat is available to every agent.

### 2.3 `api/router.py`

Replace the hardcoded `_AGENT_CHAT_ALLOWED = {"head", "qualifier", "discovery"}` with `roster_names()` from `crm.agents_registry`. This is the single allowlist already used by:
- `GET/POST /api/agents/{agent_name}/threads`
- `GET/POST /api/agents/{agent_name}/threads/{thread_id}/messages` (SSE chat)
- `GET/PUT /api/agents/{agent_name}/prompt`

Net: chat + `agent.md` editing work for every roster agent. A planned agent has no `prompts/{name}.md` yet → `GET prompt` returns `exists: false, content: ""`; saving creates the file.

No changes needed to `list_providers` (already validates via `get_agent_profile`, which now falls back to roster → no 404).

## 3. Frontend changes

The existing pages generalize with no component rewrites:

- `/agents` list: renders whatever `/api/agents` returns → all 7 appear automatically.
- `/agents/:name` (`AgentsDetail`): for non-discovery agents it already renders **Chat with {agent}**, **System prompt (agent.md)**, **Profile** (now upserts), and **Provider API keys** — so qualifier + all planned agents get these panels once the backend roster is in. Discovery keeps its Scout-controls page (chat stays on Scout HQ).

New test only: a `Qualifier` (roster-only) detail page renders chat + prompt editor + provider keys.

## 4. Error handling

- Unknown names not in the roster → 400 on chat/prompt endpoints (unchanged behavior, now driven by `roster_names()`).
- `PATCH` on a roster agent whose name has no tools configured → `validate_tool_ids(..., agent_name=name)` already enforces the tool catalog (unchanged).

## 5. Testing

Backend (`tests/test_agent_roster.py`):
- `/api/agents` lists all 7 roster names (DB rows + roster).
- `GET /api/agents/qualifier` returns a profile (roster fallback); `GET /api/agents/categorization` likewise.
- `PATCH /api/agents/qualifier` upserts → a DB row now exists; `GET` reflects the change.
- `catalog_for_agent("qualifier")` includes `llm_chat` (after 2.2b).
- `GET/POST /api/agents/categorization/threads` and `GET /api/agents/categorization/prompt` succeed (allowlist = roster); unknown name → 400.

Frontend:
- `AgentsDetail.test.tsx`: renders chat + prompt editor for `qualifier` (mock `fetchAgent` returning roster-shaped profile, `fetchAgentThreads` → `[]`, `fetchAgentPrompt` → empty).

## 6. Deferred (next phase)

- Per-agent **LLM provider** card on each agent page: `model` + `llm_base_url` (profile) + API key (encrypted `openai` secret). New `GET/PUT /api/agents/{name}/llm`.
- Runtime wiring: `agents/lm_client.py` + `_load_agent_profile` + agent classes resolve each agent's own model/base_url/key so chat and pipelines use them.
- Per-agent provider filtering in the provider-keys panel (use the roster `providers` field).
