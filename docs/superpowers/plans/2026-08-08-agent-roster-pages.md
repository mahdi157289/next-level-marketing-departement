# Agent Roster Pages (all agents) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every roster agent (including planned ones) a working page — chat, system-prompt editing, profile upsert, and provider keys — by replacing the hardcoded 3-agent allowlist and profile lookups with a static roster.

**Architecture:** Introduce a single source of truth (`crm/agents_registry.py`) holding all 7 agents. `crm/service.py` falls back to roster defaults for profile reads and upserts a real row on first edit; `tools/registry.py` advertises `llm_chat` to every agent so their default tool passes validation; `api/router.py` derives its chat/prompt allowlist from the roster. The React pages generalize with zero component changes.

**Tech Stack:** FastAPI, SQLAlchemy + Postgres, pytest, React + TS + @tanstack/react-query, Vitest + Testing-Library.

## Global Constraints

- Backend tests need a live Postgres: run with `$env:DATABASE_URL = "postgresql://admin:secret@localhost:5433/marketing_db"` in PowerShell first.
- DB-backed tests must use `@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")`.
- Run pytest from the repo root: `python -m pytest tests/<file>.py -v`. The app does not need to be restarted (backend is bind-mounted).
- Frontend: run tests and build with `workdir` = `web` (`npm test`, `npm run build`).
- No inline `#` comments; docstrings follow the existing codebase convention.
- Commit messages use the repo style: `feat:`, `test:`, `docs:`.
- Roster names (exact): `discovery`, `head`, `qualifier`, `categorization`, `analysis`, `outreach`, `content`.
- `/api/agents`-prefixed routes come from `crm/router.py` (included into the `/api` router) AND `api/router.py`; `PATCH /api/agents/{name}` and `/api/agents/{name}/providers` need no changes — they call `service.update_agent_profile` / `get_agent_profile`, which this plan makes roster-aware.

---

### Task 1: Agent roster registry (`crm/agents_registry.py`)

**Files:**
- Create: `crm/agents_registry.py`
- Test: `tests/test_agent_roster.py`

**Interfaces:**
- Consumes: `tools/registry._KNOWN_IDS` (test only, to validate tool ids).
- Produces:
  - `AGENT_ROSTER: List[Dict[str, object]]` — 7 entries with keys `name`, `display_name`, `description`, `default_tools: List[str]`, `providers: List[str]`.
  - `roster_names() -> Set[str]`
  - `roster_entry(name: str) -> Optional[Dict[str, object]]`

- [ ] **Step 1: Write the failing test**

Create `tests/test_agent_roster.py`:

```python
"""Roster: every agent gets a dedicated page."""

from __future__ import annotations

import os
from typing import Optional

import pytest
from fastapi.testclient import TestClient

from crm.agents_registry import AGENT_ROSTER, roster_entry, roster_names


def test_roster_has_all_seven_agents():
    assert roster_names() == {
        "discovery", "head", "qualifier", "categorization",
        "analysis", "outreach", "content",
    }


def test_roster_entries_are_well_formed():
    from tools.registry import _KNOWN_IDS

    assert len(AGENT_ROSTER) == 7
    seen = set()
    for entry in AGENT_ROSTER:
        assert entry["name"] not in seen
        seen.add(entry["name"])
        assert entry["display_name"]
        assert entry["description"]
        assert entry["default_tools"], "default_tools must be non-empty"
        assert set(entry["default_tools"]) <= _KNOWN_IDS
        assert entry["providers"]


def test_roster_entry_unknown_returns_none():
    assert roster_entry("nonexistent") is None


def _database_url() -> Optional[str]:
    return os.getenv("DATABASE_URL")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_agent_roster.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'crm.agents_registry'`

- [ ] **Step 3: Write minimal implementation**

Create `crm/agents_registry.py`:

```python
"""Static roster of every agent in the department.

The roster is the source of truth for which agent names exist. A name here maps
to an ``agent_profiles`` row when one exists; otherwise the roster entry's
defaults are used as a profile-shaped fallback (see ``crm.service``).
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set

AGENT_ROSTER: List[Dict[str, object]] = [
    {
        "name": "discovery", "display_name": "Discovery (Scout)",
        "description": "Searches the web/maps/ad library and writes leads.",
        "default_tools": [
            "web_search", "google_maps_search", "meta_ads_search",
            "crm_write_leads", "llm_chat", "scrape",
        ],
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


def roster_names() -> Set[str]:
    """All roster agent names — the single source of truth for allowlists."""
    return {entry["name"] for entry in AGENT_ROSTER}


def roster_entry(name: str) -> Optional[Dict[str, object]]:
    """Return the roster entry for ``name`` or ``None`` if not on the roster."""
    for entry in AGENT_ROSTER:
        if entry["name"] == name:
            return entry
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_agent_roster.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add crm/agents_registry.py tests/test_agent_roster.py
git commit -m "feat: static agent roster registry"
```

---

### Task 2: Advertise `llm_chat` to every roster agent (`tools/registry.py`)

**Files:**
- Modify: `tools/registry.py:31-35` (the `llm_chat` entry)
- Test: `tests/test_agent_roster.py` (append)

**Interfaces:**
- Consumes: `roster_names()` from Task 1 (test only).
- Produces: `catalog_for_agent(name)` and `validate_tool_ids(ids, agent_name=name)` accept `llm_chat` for all 7 roster agents.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_agent_roster.py`:

```python
def test_llm_chat_available_to_all_roster_agents():
    from tools.registry import catalog_for_agent, validate_tool_ids

    for name in roster_names():
        ids = {t["id"] for t in catalog_for_agent(name)}
        assert "llm_chat" in ids, name
        assert validate_tool_ids(["llm_chat"], agent_name=name) == ["llm_chat"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_agent_roster.py::test_llm_chat_available_to_all_roster_agents -v`
Expected: FAIL with `AssertionError: 'llm_chat' not in ids` (for `qualifier` first)

- [ ] **Step 3: Write minimal implementation**

In `tools/registry.py`, change the `llm_chat` entry (lines 31-35) to advertise every roster agent:

```python
    {
        "id": "llm_chat",
        "label": "LiteLLM / LM Studio chat",
        "agents": [
            "discovery", "head", "qualifier", "categorization",
            "analysis", "outreach", "content",
        ],
    },
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_agent_roster.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add tools/registry.py tests/test_agent_roster.py
git commit -m "feat: llm_chat tool available to every roster agent"
```

---

### Task 3: Roster-aware profiles + upsert (`crm/service.py`)

**Files:**
- Modify: `crm/service.py:461-513` (`list_agent_profiles`, `get_agent_profile`, `update_agent_profile`)
- Test: `tests/test_agent_roster.py` (append)

**Interfaces:**
- Consumes: `AGENT_ROSTER`, `roster_entry` from Task 1.
- Produces:
  - `list_agent_profiles()` returns DB rows then roster-only entries.
  - `get_agent_profile(name)` returns a roster-shaped dict for roster agents without a DB row; `None` only for names off-roster.
  - `update_agent_profile(name, data)` upserts (creates a row with roster defaults when none exists).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_agent_roster.py`:

```python
@pytest.fixture
def client():
    from api.main import app

    return TestClient(app)


@pytest.mark.skipif(not _database_url(), reason="DATABASE_URL not set")
def test_agent_profiles_list_includes_roster(client):
    from crm import service

    names = {p["agent_name"] for p in service.list_agent_profiles()}
    assert roster_names() <= names


@pytest.mark.skipif(not _database_url(), reason="DATABASE_URL not set")
def test_get_agent_profile_falls_back_to_roster():
    from crm import service

    p = service.get_agent_profile("categorization")
    assert p is not None
    assert p["display_name"] == "Categorization"
    assert p["enabled_tools"] == ["llm_chat"]
    assert p["mission_prompt"] is None


@pytest.mark.skipif(not _database_url(), reason="DATABASE_URL not set")
def test_get_agent_profile_unknown_returns_none():
    from crm import service

    assert service.get_agent_profile("nonexistent") is None


@pytest.mark.skipif(not _database_url(), reason="DATABASE_URL not set")
def test_patch_qualifier_upserts_row(client):
    from crm import service

    r = client.patch(
        "/api/agents/qualifier",
        json={"display_name": "Qualifier 2.0", "mission_prompt": "Score leads"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["agent_name"] == "qualifier"
    assert body["display_name"] == "Qualifier 2.0"
    assert body["mission_prompt"] == "Score leads"
    row = service.get_agent_profile("qualifier")
    assert row is not None
    assert row["display_name"] == "Qualifier 2.0"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_agent_roster.py -v`
Expected: 4 DB tests FAIL (3x `TypeError: 'NoneType' object is not subscriptable` / assertion, 1x `assert 404 == 200`)

- [ ] **Step 3: Write minimal implementation**

In `crm/service.py`, add the roster import after line 28:

```python
from crm.agents_registry import AGENT_ROSTER, roster_entry
```

Add a roster-shaping helper above `list_agent_profiles` (after line 458):

```python
def _profile_from_roster(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "agent_name": entry["name"],
        "display_name": entry["display_name"],
        "mission_prompt": None,
        "enabled_tools": list(entry["default_tools"]),
        "model": None,
        "default_seed_query": None,
        "default_domain": None,
        "updated_at": None,
        "available_tools": catalog_for_agent(entry["name"]),
    }
```

Replace `list_agent_profiles` (lines 461-472) with:

```python
def list_agent_profiles() -> List[Dict[str, Any]]:
    session = _session()
    try:
        rows = session.scalars(select(AgentProfile).order_by(AgentProfile.agent_name)).all()
        seen = set()
        out = []
        for r in rows:
            seen.add(r.agent_name)
            d = _row_to_dict(r)
            d["available_tools"] = catalog_for_agent(r.agent_name)
            out.append(d)
        for entry in AGENT_ROSTER:
            if entry["name"] not in seen:
                out.append(_profile_from_roster(entry))
        return out
    finally:
        session.close()
```

Replace `get_agent_profile` (lines 475-485) with:

```python
def get_agent_profile(agent_name: str) -> Optional[Dict[str, Any]]:
    session = _session()
    try:
        row = session.get(AgentProfile, agent_name)
        if row:
            d = _row_to_dict(row)
            d["available_tools"] = catalog_for_agent(agent_name)
            return d
    finally:
        session.close()
    entry = roster_entry(agent_name)
    if not entry:
        return None
    return _profile_from_roster(entry)
```

Replace `update_agent_profile` (lines 488-513) with:

```python
def update_agent_profile(agent_name: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    session = _session()
    try:
        row = session.get(AgentProfile, agent_name)
        if not row:
            entry = roster_entry(agent_name)
            if not entry:
                return None
            row = AgentProfile(
                agent_name=agent_name,
                display_name=entry["display_name"],
                mission_prompt="",
                enabled_tools=list(entry["default_tools"]),
            )
            session.add(row)
        if "display_name" in data and data["display_name"] is not None:
            row.display_name = data["display_name"]
        if "mission_prompt" in data and data["mission_prompt"] is not None:
            row.mission_prompt = data["mission_prompt"]
        if "enabled_tools" in data and data["enabled_tools"] is not None:
            row.enabled_tools = validate_tool_ids(data["enabled_tools"], agent_name=agent_name)
        if "model" in data:
            row.model = data["model"]
        if "default_seed_query" in data:
            row.default_seed_query = data["default_seed_query"]
        if "default_domain" in data:
            row.default_domain = ((data["default_domain"] or "").strip() or None)
        row.updated_at = datetime.utcnow()
        session.commit()
        session.refresh(row)
        d = _row_to_dict(row)
        d["available_tools"] = catalog_for_agent(agent_name)
        return d
    finally:
        session.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_agent_roster.py -v`
Expected: 8 passed (4 unit + 4 DB)

- [ ] **Step 5: Run the existing agent-control suite for regressions**

Run: `python -m pytest tests/test_agent_control.py -v`
Expected: all pass (GET/PATCH `/crm/agents` still works)

- [ ] **Step 6: Commit**

```bash
git add crm/service.py tests/test_agent_roster.py
git commit -m "feat: roster-aware agent profiles with upsert"
```

---

### Task 4: Allowlist from the roster (`api/router.py`)

**Files:**
- Modify: `api/router.py:12` (import), `api/router.py:47` (constant), and the six `agent_name not in _AGENT_CHAT_ALLOWED` checks at lines 174, 181, 191, 201, 208, 223
- Test: `tests/test_agent_roster.py` (append)

**Interfaces:**
- Consumes: `roster_names()` from Task 1.
- Produces: `GET/POST /api/agents/{name}/threads`, thread messages (SSE chat), and `GET/PUT /api/agents/{name}/prompt` accept every roster name; off-roster names still 400.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_agent_roster.py`:

```python
@pytest.mark.skipif(not _database_url(), reason="DATABASE_URL not set")
def test_roster_chat_and_prompt_endpoints(client):
    r = client.post("/api/agents/categorization/threads", json={"title": "t"})
    assert r.status_code == 201, r.text
    thread_id = r.json()["id"]

    r = client.get(f"/api/agents/categorization/threads/{thread_id}/messages")
    assert r.status_code == 200, r.text

    r = client.get("/api/agents/categorization/prompt")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["agent_name"] == "categorization"
    assert body["exists"] is False

    r = client.get("/api/agents/nonexistent/prompt")
    assert r.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_agent_roster.py -v`
Expected: the new test FAILs with `assert 400 == 201` (categorization not in the hardcoded allowlist)

- [ ] **Step 3: Write minimal implementation**

In `api/router.py`, add the import after line 12:

```python
from crm.agents_registry import roster_names
```

Replace the constant at line 47:

```python
_AGENT_CHAT_ALLOWED = {"head", "qualifier", "discovery"}
```

with nothing (delete the line). Then replace each of the six checks:

```python
    if agent_name not in _AGENT_CHAT_ALLOWED:
        raise HTTPException(status_code=400, detail=f"Unknown agent: {agent_name}")
```

with:

```python
    if agent_name not in roster_names():
        raise HTTPException(status_code=400, detail=f"Unknown agent: {agent_name}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_agent_roster.py -v`
Expected: 9 passed (4 unit + 5 DB)

- [ ] **Step 5: Run the chat + prompt suites for regressions**

Run: `python -m pytest tests/test_agent_chat_api.py tests/test_agent_prompt_api.py tests/test_provider_keys.py -v`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add api/router.py tests/test_agent_roster.py
git commit -m "feat: derive agent chat/prompt allowlist from the roster"
```

---

### Task 5: Qualifier (roster-only) detail page test (`web/src/pages/AgentsDetail.test.tsx`)

**Files:**
- Modify: `web/src/pages/AgentsDetail.test.tsx` (append a test)
- Test: the file itself

**Interfaces:**
- Consumes: the generalized `AgentsDetail` page (no component changes) + Task 3/4 backend behavior.
- Produces: evidence that a roster-only agent renders chat + prompt editor + provider keys.

- [ ] **Step 1: Write the failing (new) test**

Append inside the `describe("AgentsDetail", ...)` block in `web/src/pages/AgentsDetail.test.tsx`:

```tsx
  it("renders chat + prompt editor + provider keys for qualifier (roster-only)", async () => {
    vi.mocked(agentsApi.fetchAgent).mockResolvedValue({
      agent_name: "qualifier",
      display_name: "Qualifier",
      mission_prompt: null,
      enabled_tools: ["llm_chat"],
      model: null,
      default_seed_query: null,
      updated_at: null,
      available_tools: [
        {
          id: "llm_chat",
          label: "LiteLLM / LM Studio chat",
          agents: ["discovery", "head", "qualifier"],
        },
      ],
    });
    vi.mocked(agentsApi.fetchProviders).mockResolvedValue([]);
    vi.mocked(agentChatApi.fetchAgentThreads).mockResolvedValue([
      { id: "t1", title: "scoring", created_at: null, updated_at: null },
    ]);
    vi.mocked(agentChatApi.fetchAgentMessages).mockResolvedValue([]);
    vi.mocked(agentChatApi.fetchAgentPrompt).mockResolvedValue({
      agent_name: "qualifier",
      exists: false,
      content: "",
      resolved_prompt: "",
    });

    renderDetail("qualifier");

    expect(await screen.findByText("Qualifier")).toBeInTheDocument();
    expect(await screen.findByText("System prompt (agent.md)")).toBeInTheDocument();
    expect(
      screen.getByText("Provider API keys (hashed fingerprint shown)"),
    ).toBeInTheDocument();

    fireEvent.click(await screen.findByText("scoring"));
    expect(screen.getByPlaceholderText("Message the Qualifier…")).toBeInTheDocument();
  });
```

- [ ] **Step 2: Run test to verify it passes**

Run (in `web`): `npm test -- AgentsDetail`
Expected: all AgentsDetail tests pass

- [ ] **Step 3: Run the full frontend suite + build**

Run (in `web`): `npm test` then `npm run build`
Expected: all tests pass; build completes clean

- [ ] **Step 4: Commit**

```bash
git add web/src/pages/AgentsDetail.test.tsx
git commit -m "test: roster-only agent detail page renders"
```

---

### Task 6: Verify + mark the spec implemented

**Files:**
- Modify: `docs/superpowers/specs/2026-08-08-agent-roster-pages-design.md:3` (status line)

- [ ] **Step 1: Run the full backend suite**

Run: `python -m pytest -q`
Expected: all pass (existing 116 passed / 6 skipped baseline plus the new tests)

- [ ] **Step 2: Live smoke check**

With the app running (bind-mounted backend picks up changes automatically):

1. `curl http://localhost:8000/api/agents` — all 7 names present.
2. `curl http://localhost:8000/api/agents/qualifier` — returns a profile (not 404).
3. `curl http://localhost:8000/api/agents/categorization/prompt` — `"exists": false`.
4. Open `http://localhost:3000/agents/qualifier` in the browser — chat + prompt editor + profile + provider keys render.

- [ ] **Step 3: Mark the spec implemented**

In `docs/superpowers/specs/2026-08-08-agent-roster-pages-design.md`, change line 3:

```markdown
> **Date:** 2026-08-08  **Status:** Design approved.
```

to:

```markdown
> **Date:** 2026-08-08  **Status:** Implemented (committed).
```

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-08-08-agent-roster-pages-design.md
git commit -m "docs: mark agent roster pages spec implemented"
```
