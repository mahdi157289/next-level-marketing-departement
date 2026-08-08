# Agent Chat + Editable agent.md (Head & Qualifier) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the operator talk to the Head and Qualifier agents via chat (same experience as Scout) and author each agent's role through an editable `agent.md` file.

**Architecture:** Generalize the existing Scout chat pipeline. Add `agent_name` to the thread/message tables and service layer, parameterize `crm/scout.py::run_scout_turn` into a shared `run_agent_turn(agent_name, ...)`, expose agent-scoped REST+SSE endpoints, and add a `GET/PUT /api/agents/{name}/prompt` API over `prompts/{name}.md`. Frontend extracts the generic `AgentChat` component and adds an `AgentPromptEditor` panel on the agent detail page.

**Tech Stack:** Existing — FastAPI, SQLAlchemy raw sessions, alembic, React + TS + @tanstack/react-query, vitest + @testing-library/react, SSE streaming (existing `takeFrames`).

## Global Constraints

- "No paid APIs / local LLM only." All new services are local containers.
- Follow existing conventions: flat `tests/test_*.py`, DB-gated tests use `@pytest.mark.skipif(not os.getenv("DATABASE_URL"), ...)`, API tests use `TestClient(app)`, function-local/`monkeypatch`-targeted patching, flat API helpers in `web/src/api/*.ts`, co-located `*.test.tsx`.
- `web/src/test/setup.ts` handles jest-dom + `afterEach(cleanup)` — do NOT add manual cleanup.
- Migrations: app container runs alembic at start; after adding migrations run `docker exec marketing_app python -m alembic upgrade head` (or restart the app) before DB-gated tests.
- Host pytest runs on Windows Python 3.9; run `python -m pytest tests/... -q --no-header` on host. Full suite before this work: **104 passed, 6 skipped**.
- `npm`/`npm test` run with `workdir = web`. Full frontend suite before this work: **35 passed / 15 files**.
- Agent allowlist for the new endpoints: `{"head", "qualifier", "discovery"}`. Scout = `discovery`.
- Model resolution: `agent_profiles.model` else `settings.agent_model_discovery` for discovery, `settings.agent_model_head` otherwise.
- The existing DB `mission_prompt` override wins over the file prompt (`knowledge/prompts.py::load_agent_prompt`). Do NOT change that.
- Windows host / PowerShell. Use `docker compose`.

---

### Task 1: Schema + service — `agent_name` on threads/messages

**Files:**
- Create: `migrations/versions/20260808_0010_agent_chat_threads.py`
- Modify: `db/models.py:213-232`, `crm/service.py:519-580`
- Test: `tests/test_agent_chat_api.py` (Task 3 adds the rest of this file; this task adds the DB-gated service test)

**Interfaces:**
- Produces:
  - `ScoutThread.agent_name`, `ScoutMessage.agent_name` columns (default `"discovery"`).
  - `service.create_scout_thread(title=None, agent_name="discovery") -> Dict`
  - `service.list_scout_threads(agent_name="discovery", limit=50) -> List[Dict]`
  - `service.add_scout_message(thread_id, role, content=None, tool_name=None, tool_args=None, tool_result=None, agent_name="discovery") -> Dict`
  - `service.list_scout_messages(thread_id, limit=200) -> List[Dict]` (unchanged signature)

- [ ] **Step 1: Write the migration**

`migrations/versions/20260808_0010_agent_chat_threads.py`:

```python
"""Add agent_name to scout_threads / scout_messages (agent chat generalization)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260808_0010"
down_revision = "20260808_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scout_threads",
        sa.Column("agent_name", sa.String(32), nullable=False, server_default="discovery"),
    )
    op.add_column(
        "scout_messages",
        sa.Column("agent_name", sa.String(32), nullable=False, server_default="discovery"),
    )
    op.create_index("ix_scout_threads_agent_name", "scout_threads", ["agent_name"])
    op.create_index("ix_scout_messages_agent_name", "scout_messages", ["agent_name"])


def downgrade() -> None:
    op.drop_index("ix_scout_messages_agent_name", table_name="scout_messages")
    op.drop_index("ix_scout_threads_agent_name", table_name="scout_threads")
    op.drop_column("scout_messages", "agent_name")
    op.drop_column("scout_threads", "agent_name")
```

- [ ] **Step 2: Add columns to the models**

In `db/models.py`, `ScoutThread` (after `title = Column(Text)` at line 217) add:

```python
    agent_name = Column(String(32), nullable=False, default="discovery")
```

In `ScoutMessage` (after `thread_id = Column(UUID(as_uuid=True), nullable=False)` at line 226) add:

```python
    agent_name = Column(String(32), nullable=False, default="discovery")
```

- [ ] **Step 3: Thread the agent_name through the service layer**

In `crm/service.py`, replace `create_scout_thread`, `list_scout_threads`, and `add_scout_message` (lines 519-566) with:

```python
def create_scout_thread(
    title: Optional[str] = None, agent_name: str = "discovery"
) -> Dict[str, Any]:
    session = _session()
    try:
        thread = ScoutThread(
            id=uuid.uuid4(),
            title=title or "New scout thread",
            agent_name=agent_name,
        )
        session.add(thread)
        session.commit()
        session.refresh(thread)
        return _row_to_dict(thread)
    finally:
        session.close()


def list_scout_threads(agent_name: str = "discovery", limit: int = 50) -> List[Dict[str, Any]]:
    session = _session()
    try:
        rows = session.scalars(
            select(ScoutThread)
            .where(ScoutThread.agent_name == agent_name)
            .order_by(ScoutThread.created_at.desc())
            .limit(limit)
        ).all()
        return [_row_to_dict(r) for r in rows]
    finally:
        session.close()


def add_scout_message(
    thread_id: str,
    role: str,
    content: Optional[str] = None,
    tool_name: Optional[str] = None,
    tool_args: Optional[Dict[str, Any]] = None,
    tool_result: Optional[Any] = None,
    agent_name: str = "discovery",
) -> Dict[str, Any]:
    session = _session()
    try:
        msg = ScoutMessage(
            id=uuid.uuid4(),
            thread_id=uuid.UUID(thread_id),
            role=role,
            content=content,
            tool_name=tool_name,
            tool_args=tool_args,
            tool_result=tool_result,
            agent_name=agent_name,
        )
        session.add(msg)
        session.commit()
        session.refresh(msg)
        return _row_to_dict(msg)
    finally:
        session.close()
```

`list_scout_messages` stays unchanged (threads are already isolated by their UUID).

- [ ] **Step 4: Apply the migration**

Run: `docker exec marketing_app python -m alembic upgrade head`
Verify columns:
Run: `docker exec marketing_postgres psql -U admin -d marketing_db -tAc "\d scout_threads"` → shows `agent_name character varying(32)`.

- [ ] **Step 5: Add the DB-gated service test**

Append to `tests/test_agent_chat_api.py` (create the file with just this test for now; Task 3 adds more):

```python
"""Agent-scoped chat + prompt API tests."""
from __future__ import annotations

import os
import uuid
from typing import Optional

import pytest
from sqlalchemy import create_engine, text


def _database_url() -> Optional[str]:
    return os.getenv("DATABASE_URL")


@pytest.mark.skipif(not _database_url(), reason="DATABASE_URL not set")
def test_threads_scoped_by_agent():
    from crm import service

    tag = uuid.uuid4().hex[:8]
    head_thread = service.create_scout_thread(f"head-{tag}", agent_name="head")
    discovery_thread = service.create_scout_thread(f"disc-{tag}", agent_name="discovery")
    try:
        heads = service.list_scout_threads(agent_name="head", limit=50)
        discs = service.list_scout_threads(agent_name="discovery", limit=50)
        assert any(t["id"] == head_thread["id"] for t in heads)
        assert not any(t["id"] == head_thread["id"] for t in discs)
        assert any(t["id"] == discovery_thread["id"] for t in discs)
    finally:
        eng = create_engine(_database_url())
        with eng.begin() as conn:
            conn.execute(
                text("DELETE FROM scout_messages WHERE thread_id IN (SELECT id FROM scout_threads WHERE id = ANY(:ids::uuid[]))"),
                {"ids": [str(head_thread["id"]), str(discovery_thread["id"])]},
            )
        with eng.begin() as conn:
            conn.execute(
                text("DELETE FROM scout_threads WHERE id = ANY(:ids::uuid[])"),
                {"ids": [str(head_thread["id"]), str(discovery_thread["id"])]},
            )
        eng.dispose()
```

- [ ] **Step 6: Run the DB-gated test**

Run: `python -m pytest tests/test_agent_chat_api.py -q --no-header`
Expected: PASS (or SKIP if `DATABASE_URL` unset — run with the app env: `DATABASE_URL=$(docker exec marketing_app printenv DATABASE_URL)`).

- [ ] **Step 7: Commit**

```bash
git add migrations/versions/20260808_0010_agent_chat_threads.py db/models.py crm/service.py tests/test_agent_chat_api.py
git commit -m "feat(agent-chat): agent_name column on scout threads/messages"
```

---

### Task 2: Chat engine — `run_agent_turn(agent_name, ...)`

**Files:**
- Modify: `crm/scout.py:61-206`
- Test: `tests/test_agent_chat.py` (new)

**Interfaces:**
- Consumes: `knowledge.prompts.load_agent_prompt`, `knowledge.retrieval.build_brain_context` (already imported), `crm.service.add_scout_message(..., agent_name=...)` (Task 1), `config.settings.get_settings`.
- Produces:
  - `crm.scout._load_agent_profile(agent_name) -> Dict` with keys `{model, mission_prompt, enabled_tools}`.
  - `crm.scout.run_agent_turn(agent_name, thread_id, user_text, *, max_tool_iterations=5, profile=None) -> Dict` — same return shape as today: `{thread_id, assistant, tool_calls, message_ids}`.
  - `crm.scout.run_scout_turn(...)` — thin wrapper delegating to `run_agent_turn("discovery", ...)`, same signature and behavior.

- [ ] **Step 1: Write the failing engine tests**

`tests/test_agent_chat.py`:

```python
"""Agent chat engine — pure logic, mocked LLM + tools + service."""
from __future__ import annotations

import pytest


class _FakeProfile:
    def __init__(self, **kw):
        self.model = kw.get("model", "head-model")
        self.mission_prompt = kw.get("mission_prompt", "You are the Head Agent.")
        self.enabled_tools = kw.get("enabled_tools", ["llm_chat"])

    def get(self, key, default=None):
        return getattr(self, key, default)


def test_run_agent_turn_uses_agent_profile(monkeypatch):
    from crm import scout

    recorded = []
    monkeypatch.setattr(
        scout.service, "get_agent_profile",
        lambda name: _FakeProfile() if name == "head" else None,
    )

    def fake_add(*a, **kw):
        role = kw.get("role") if len(a) < 2 else a[1]
        recorded.append({"role": role, "agent_name": kw.get("agent_name")})
        return {"id": f"m{len(recorded)}"}

    monkeypatch.setattr(scout.service, "add_scout_message", fake_add)
    monkeypatch.setattr(scout.service, "list_scout_messages", lambda tid, limit=200: [])
    monkeypatch.setattr(
        scout.lm_client,
        "chat_completion_tools",
        lambda model, messages, tools, **kw: {"content": "Plan ready.", "tool_calls": []},
    )
    monkeypatch.setattr(scout.lm_client, "chat_completion", lambda *a, **kw: "Plan ready.")

    out = scout.run_agent_turn("head", "thread-1", "plan this")

    assert out["assistant"] == "Plan ready."
    assert recorded[0] == {"role": "user", "agent_name": "head"}
    assert recorded[-1]["role"] == "assistant"
    assert recorded[-1]["agent_name"] == "head"


def test_run_agent_turn_advertises_no_tools_for_llm_only(monkeypatch):
    from crm import scout

    seen_tools = {}

    def fake_tools(model, messages, tools, **kw):
        seen_tools["tools"] = tools
        return {"content": "ok", "tool_calls": []}

    monkeypatch.setattr(scout.service, "get_agent_profile", lambda name: _FakeProfile(enabled_tools=["llm_chat"]))
    monkeypatch.setattr(scout.service, "add_scout_message", lambda *a, **kw: {"id": "m"})
    monkeypatch.setattr(scout.service, "list_scout_messages", lambda tid, limit=200: [])
    monkeypatch.setattr(scout.lm_client, "chat_completion_tools", fake_tools)

    scout.run_agent_turn("head", "thread-1", "hi")

    assert seen_tools["tools"] == []


def test_run_scout_turn_still_delegates_to_discovery(monkeypatch):
    from crm import scout

    def fake_tools(model, messages, tools, **kw):
        return {"content": "Scout answer.", "tool_calls": []}

    monkeypatch.setattr(scout.service, "get_agent_profile", lambda name: _FakeProfile())
    monkeypatch.setattr(scout.service, "add_scout_message", lambda *a, **kw: {"id": "m"})
    monkeypatch.setattr(scout.service, "list_scout_messages", lambda tid, limit=200: [])
    monkeypatch.setattr(scout.lm_client, "chat_completion_tools", fake_tools)
    monkeypatch.setattr(scout.lm_client, "chat_completion", lambda *a, **kw: "Scout answer.")

    out = scout.run_scout_turn("thread-1", "hello")

    assert out["assistant"] == "Scout answer."
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_agent_chat.py -q --no-header`
Expected: FAIL with `AttributeError: module 'crm.scout' has no attribute 'run_agent_turn'`.

- [ ] **Step 3: Add `_load_agent_profile`**

In `crm/scout.py`, add `from knowledge.prompts import load_agent_prompt` to the imports, then replace `_load_scout_profile` (lines 61-72) with:

```python
def _load_agent_profile(agent_name: str) -> Dict[str, Any]:
    s = get_settings()
    try:
        profile = service.get_agent_profile(agent_name) or {}
    except Exception:
        profile = {}
    if agent_name == "discovery":
        model = profile.get("model") or s.agent_model_discovery
        tools = list(profile.get("enabled_tools") or [])
    else:
        model = profile.get("model") or s.agent_model_head
        tools = list(profile.get("enabled_tools") or ["llm_chat"])
    mission_prompt = load_agent_prompt(agent_name, profile.get("mission_prompt"))
    return {
        "model": model,
        "mission_prompt": mission_prompt or "You are the Agent.",
        "enabled_tools": tools,
    }


def _load_scout_profile() -> Dict[str, Any]:
    return _load_agent_profile("discovery")
```

- [ ] **Step 4: Rename the engine to `run_agent_turn`**

Rename `run_scout_turn` (line 114) to `run_agent_turn(agent_name, thread_id, user_text, *, max_tool_iterations=_MAX_TOOL_ITERATIONS, profile=None)` and change its body:
- `if profile is None: profile = _load_agent_profile(agent_name)`
- `service.add_scout_message(thread_id, "user", content=user_text, agent_name=agent_name)`
- `ctx = build_brain_context(agent_name, latest_user)`
- The three `service.add_scout_message(...)` calls (user, tool, assistant) each add `agent_name=agent_name`.
- Everything else (tool loop, fallback tools, return dict) stays identical.

Then add a thin wrapper after it:

```python
def run_scout_turn(
    thread_id: str,
    user_text: str,
    *,
    max_tool_iterations: int = _MAX_TOOL_ITERATIONS,
    profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return run_agent_turn(
        "discovery",
        thread_id,
        user_text,
        max_tool_iterations=max_tool_iterations,
        profile=profile,
    )
```

- [ ] **Step 5: Run the new tests**

Run: `python -m pytest tests/test_agent_chat.py -q --no-header`
Expected: PASS (3 tests).

- [ ] **Step 6: Run the existing scout engine tests (regression)**

Run: `python -m pytest tests/test_scout_engine.py -q --no-header`
Expected: PASS (all existing tests — `_FakeProfile.get` and `add_scout_message` lambdas accept the extra `agent_name` kwarg).

- [ ] **Step 7: Commit**

```bash
git add crm/scout.py tests/test_agent_chat.py
git commit -m "feat(agent-chat): generalize run_scout_turn into run_agent_turn"
```

---

### Task 3: Chat API — agent-scoped threads + SSE

**Files:**
- Modify: `api/router.py:54-91`
- Test: `tests/test_agent_chat_api.py` (extend)

**Interfaces:**
- Consumes: `crm.scout.run_agent_turn` (Task 2), `crm.service.list_scout_threads/create_scout_thread/list_scout_messages` (Task 1).
- Produces:
  - `GET /api/agents/{name}/threads?limit=` → `List[ScoutThreadOut]`
  - `POST /api/agents/{name}/threads` `{title?}` → `ScoutThreadOut` (201)
  - `GET /api/agents/{name}/threads/{thread_id}/messages` → `List[ScoutMessageOut]`
  - `POST /api/agents/{name}/threads/{thread_id}/messages` `{content}` → SSE stream (`start`/`delta`/`done`/`error` frames)
  - Unknown agent name → 400; bad thread UUID on GET messages → 422.

- [ ] **Step 1: Write the failing API tests**

Append to `tests/test_agent_chat_api.py`:

```python
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from api.main import app

    return TestClient(app)


def test_unknown_agent_threads_400(client):
    r = client.get("/api/agents/nope/threads")
    assert r.status_code == 400, r.text


def test_list_threads_scoped_by_agent(client, monkeypatch):
    from crm import service

    monkeypatch.setattr(service, "list_scout_threads", lambda agent_name, limit=50: [])
    r = client.get("/api/agents/head/threads?limit=10")
    assert r.status_code == 200, r.text
    assert r.json() == []


def test_create_thread_posts_agent_name(client, monkeypatch):
    from crm import service

    calls = {}
    monkeypatch.setattr(
        service,
        "create_scout_thread",
        lambda title=None, agent_name="discovery": calls.update(title=title, agent_name=agent_name)
        or {"id": "00000000-0000-0000-0000-000000000001", "title": title, "created_at": None, "updated_at": None},
    )
    r = client.post("/api/agents/qualifier/threads", json={"title": "q1"})
    assert r.status_code == 201, r.text
    assert calls["agent_name"] == "qualifier"
    assert calls["title"] == "q1"


def test_unknown_agent_messages_400(client):
    r = client.get("/api/agents/nope/threads/00000000-0000-0000-0000-000000000001/messages")
    assert r.status_code == 400, r.text


def test_agent_sse_stream_frames(client, monkeypatch):
    from crm import scout

    monkeypatch.setattr(
        scout,
        "run_agent_turn",
        lambda agent_name, thread_id, content, **kw: {
            "thread_id": "00000000-0000-0000-0000-000000000001",
            "assistant": "hello there",
            "tool_calls": 0,
            "message_ids": [],
        },
    )
    r = client.post(
        "/api/agents/head/threads/00000000-0000-0000-0000-000000000001/messages",
        json={"content": "hi"},
    )
    assert r.status_code == 200, r.text
    body = r.text
    assert "event: start" in body
    assert "event: delta" in body
    assert "hello there" in body
    assert "event: done" in body
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_agent_chat_api.py -q --no-header`
Expected: FAIL (404 — routes not registered).

- [ ] **Step 3: Add the agent-chat routes**

In `api/router.py`, add `_AGENT_CHAT_ALLOWED` near the other constants:

```python
_AGENT_CHAT_ALLOWED = {"head", "qualifier", "discovery"}
```

Rename `_scout_chat_events` (line 59) to `_agent_chat_events(agent_name, thread_id, content, profile=None)` and change the `run_kwargs`/call to:

```python
    from crm import scout

    async def gen():
        try:
            yield "event: start\ndata: {}\n\n"
            run_kwargs = {}
            if profile is not None:
                run_kwargs["profile"] = profile
            result = await asyncio.to_thread(
                scout.run_agent_turn, agent_name, thread_id, content, **run_kwargs
            )
            for i, chunk in enumerate(_chunk_text(result["assistant"], 80)):
                payload = {"delta": chunk, "index": i}
                yield f"event: delta\ndata: {json.dumps(payload)}\n\n"
            payload = {
                "thread_id": result["thread_id"],
                "assistant": result["assistant"],
                "tool_calls": result["tool_calls"],
            }
            yield f"event: done\ndata: {json.dumps(payload)}\n\n"
        except Exception as exc:
            yield f"event: error\ndata: {json.dumps({'detail': str(exc)})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
```

Update `api_scout_chat` to delegate (keeps the scout route working):

```python
@router.post("/scout/threads/{thread_id}/messages")
def api_scout_chat(thread_id: str, body: ScoutMessageCreate):
    return _agent_chat_events("discovery", thread_id, body.content)
```

Append the new agent-scoped endpoints after the existing scout thread routes (after line 162):

```python
@router.get("/agents/{agent_name}/threads", response_model=List[schemas.ScoutThreadOut])
def api_list_agent_threads(agent_name: str, limit: int = 50):
    if agent_name not in _AGENT_CHAT_ALLOWED:
        raise HTTPException(status_code=400, detail=f"Unknown agent: {agent_name}")
    return service.list_scout_threads(agent_name=agent_name, limit=limit)


@router.post("/agents/{agent_name}/threads", response_model=schemas.ScoutThreadOut, status_code=201)
def api_create_agent_thread(agent_name: str, body: ScoutThreadCreate):
    if agent_name not in _AGENT_CHAT_ALLOWED:
        raise HTTPException(status_code=400, detail=f"Unknown agent: {agent_name}")
    return service.create_scout_thread(body.title, agent_name=agent_name)


@router.get(
    "/agents/{agent_name}/threads/{thread_id}/messages",
    response_model=List[schemas.ScoutMessageOut],
)
def api_list_agent_messages(agent_name: str, thread_id: str, limit: int = 200):
    if agent_name not in _AGENT_CHAT_ALLOWED:
        raise HTTPException(status_code=400, detail=f"Unknown agent: {agent_name}")
    try:
        return service.list_scout_messages(thread_id, limit=limit)
    except ValueError:
        raise HTTPException(status_code=422, detail="thread_id must be a UUID")


@router.post("/agents/{agent_name}/threads/{thread_id}/messages")
def api_agent_chat(agent_name: str, thread_id: str, body: ScoutMessageCreate):
    if agent_name not in _AGENT_CHAT_ALLOWED:
        raise HTTPException(status_code=400, detail=f"Unknown agent: {agent_name}")
    return _agent_chat_events(agent_name, thread_id, body.content)
```

- [ ] **Step 4: Run the API tests**

Run: `python -m pytest tests/test_agent_chat_api.py -q --no-header`
Expected: PASS (5 hermetic tests + the DB-gated service test from Task 1, which skips without `DATABASE_URL`).

- [ ] **Step 5: Run the full backend suite**

Run: `python -m pytest tests/ -q --no-header`
Expected: all pass (includes `test_api_router.py::test_openapi_unique_operation_ids` — new operation ids are unique).

- [ ] **Step 6: Commit**

```bash
git add api/router.py tests/test_agent_chat_api.py
git commit -m "feat(agent-chat): agent-scoped thread + SSE chat endpoints"
```

---

### Task 4: Prompt editor API + qualifier prompt fallback

**Files:**
- Create: `prompts/qualifier.md`
- Modify: `knowledge/prompts.py`, `api/router.py`
- Test: `tests/test_agent_prompt_api.py` (new)

**Interfaces:**
- Consumes: `knowledge.prompts.prompt_dir()`, `load_agent_prompt`, `file_prompt` (existing).
- Produces:
  - `knowledge.prompts.write_file_prompt(agent_name, content) -> None`
  - `GET /api/agents/{name}/prompt` → `{agent_name, exists, content, resolved_prompt}`
  - `PUT /api/agents/{name}/prompt` `{content}` → same shape
  - Unknown agent → 400; missing file GET → 200 with `exists: false, content: ""`.

- [ ] **Step 1: Write the failing prompt API tests**

`tests/test_agent_prompt_api.py`:

```python
"""GET/PUT agent system prompt (prompts/{name}.md) API tests."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from api.main import app

    return TestClient(app)


@pytest.fixture
def tmp_prompt_dir(monkeypatch, tmp_path):
    from knowledge import prompts

    monkeypatch.setattr(prompts, "_PROMPT_DIR", tmp_path)
    return tmp_path


def test_get_missing_prompt_returns_exists_false(client, tmp_prompt_dir):
    r = client.get("/api/agents/head/prompt")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["agent_name"] == "head"
    assert data["exists"] is False
    assert data["content"] == ""


def test_put_writes_and_get_roundtrips(client, tmp_prompt_dir):
    content = "# System Prompt — Head\n\nBe decisive."
    r = client.put("/api/agents/head/prompt", json={"content": content})
    assert r.status_code == 200, r.text
    assert r.json()["exists"] is True
    assert r.json()["content"] == content

    r2 = client.get("/api/agents/head/prompt")
    assert r2.json()["content"] == content


def test_unknown_agent_prompt_400(client, tmp_prompt_dir):
    assert client.get("/api/agents/nope/prompt").status_code == 400
    assert client.put("/api/agents/nope/prompt", json={"content": "x"}).status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_agent_prompt_api.py -q --no-header`
Expected: FAIL (404 — routes not registered).

- [ ] **Step 3: Add the qualifier prompt + fallback**

Create `prompts/qualifier.md`:

```markdown
# System Prompt — Qualifier Agent

You are the Qualifier Agent for Next Level Tech Company. Given a lead (name, URL, notes), evaluate it against the company profile and scoring criteria.

## Scoring criteria
- **Development** — web/app/crm/admin
- **Data** — analytics/dashboards
- **Marketing** — human or AI marketing
- **Automation** — workflows / AI agents
- **Migration** — stack or provider migration
- Prefer Tunisia-based or MENA region. Skip directories, news sites, non-business pages.

## Output format
Respond with JSON only (no markdown fences): `{"score": <0-50>, "fit": "<perfect|good|partial|poor>", "service_category": "<development|data|marketing|automation|migration|none>", "reasoning": "<1 sentence why>"}`.

## Persona
Rigorous, specific, honest. Never inflate a score.
```

In `knowledge/prompts.py`, add a qualifier default and wire the fallback:

```python
_DEFAULT_QUALIFIER_PROMPT = (
    "You are the Qualifier Agent for Next Level Tech Company. "
    "Given a lead (name, URL, notes), evaluate it and respond with JSON only: "
    '{"score": <0-50>, "fit": "<perfect|good|partial|poor>", '
    '"service_category": "<development|data|marketing|automation|migration|none>", '
    '"reasoning": "<1 sentence why>"}'
)
```

Update `_fallback` (line 51):

```python
def _fallback(agent_name: str) -> str:
    if agent_name == "head":
        return _DEFAULT_HEAD_PROMPT
    if agent_name == "qualifier":
        return _DEFAULT_QUALIFIER_PROMPT
    return _DEFAULT_DISCOVERY_PROMPT
```

- [ ] **Step 4: Add `write_file_prompt`**

In `knowledge/prompts.py`, after `file_prompt` (line 62) add:

```python
def write_file_prompt(agent_name: str, content: str) -> None:
    """Write the file-backed system prompt for an agent (creates/replaces agent.md)."""
    path = _PROMPT_DIR / f"{agent_name}.md"
    _PROMPT_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(content or "", encoding="utf-8")
```

- [ ] **Step 5: Add the prompt routes**

In `api/router.py`, add `PromptUpdate` next to the other request models:

```python
class PromptUpdate(BaseModel):
    content: str
```

Append the routes:

```python
@router.get("/agents/{agent_name}/prompt")
def api_get_agent_prompt(agent_name: str):
    if agent_name not in _AGENT_CHAT_ALLOWED:
        raise HTTPException(status_code=400, detail=f"Unknown agent: {agent_name}")
    from knowledge import prompts

    content = prompts.file_prompt(agent_name)
    return {
        "agent_name": agent_name,
        "exists": bool(content),
        "content": content,
        "resolved_prompt": prompts.load_agent_prompt(agent_name, None),
    }


@router.put("/agents/{agent_name}/prompt")
def api_put_agent_prompt(agent_name: str, body: PromptUpdate):
    if agent_name not in _AGENT_CHAT_ALLOWED:
        raise HTTPException(status_code=400, detail=f"Unknown agent: {agent_name}")
    from knowledge import prompts

    prompts.write_file_prompt(agent_name, body.content)
    content = prompts.file_prompt(agent_name)
    return {
        "agent_name": agent_name,
        "exists": bool(content),
        "content": content,
        "resolved_prompt": prompts.load_agent_prompt(agent_name, None),
    }
```

- [ ] **Step 6: Run the prompt tests**

Run: `python -m pytest tests/test_agent_prompt_api.py -q --no-header`
Expected: PASS (3 tests).

- [ ] **Step 7: Run the full backend suite**

Run: `python -m pytest tests/ -q --no-header`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add prompts/qualifier.md knowledge/prompts.py api/router.py tests/test_agent_prompt_api.py
git commit -m "feat(agent-chat): GET/PUT agent system prompt + qualifier agent.md"
```

---

### Task 5: Frontend API + types + hook

**Files:**
- Create: `web/src/api/agent-chat.ts`
- Modify: `web/src/api/types.ts`, `web/src/api/scout.ts`, `web/src/hooks/useScoutChat.ts`
- Test: `web/src/api/agent-chat.test.ts` (new)

**Interfaces:**
- Consumes: `apiGet`/`apiSend` from `client.ts`, `takeFrames` from `sse.ts`.
- Produces:
  - `web/src/api/agent-chat.ts`:
    - `fetchAgentThreads(agentName, limit=50): Promise<ScoutThread[]>`
    - `createAgentThread(agentName, title?): Promise<ScoutThread>`
    - `fetchAgentMessages(agentName, threadId): Promise<ScoutMessage[]>`
    - `streamAgentTurn(agentName, threadId, content, handlers)` (same handler shape as `streamScoutTurn`)
    - `fetchAgentPrompt(agentName): Promise<AgentPrompt>`
    - `saveAgentPrompt(agentName, content): Promise<AgentPrompt>`
  - `web/src/api/types.ts`: `AgentPrompt { agent_name; exists; content; resolved_prompt }`
  - `web/src/hooks/useAgentChat.ts`: `useAgentChat(agentName, threadId, onTurnDone?, onTurnError?)` — same shape as `useScoutChat`.
  - `web/src/hooks/useScoutChat.ts`: becomes a thin wrapper delegating to `useAgentChat("discovery", ...)` (keeps ScoutHQ + existing tests working).

- [ ] **Step 1: Add the frontend type**

In `web/src/api/types.ts`, append:

```ts
export interface AgentPrompt {
  agent_name: string;
  exists: boolean;
  content: string;
  resolved_prompt: string;
}
```

- [ ] **Step 2: Create `web/src/api/agent-chat.ts`**

```ts
import { apiGet, apiSend } from "./client";
import { takeFrames } from "./sse";
import type { AgentPrompt, ScoutMessage, ScoutThread } from "./types";

export function fetchAgentThreads(agentName: string, limit = 50): Promise<ScoutThread[]> {
  return apiGet<ScoutThread[]>(`/api/agents/${agentName}/threads?limit=${limit}`);
}

export function createAgentThread(agentName: string, title?: string): Promise<ScoutThread> {
  return apiSend<ScoutThread>(`/api/agents/${agentName}/threads`, "POST", { title });
}

export function fetchAgentMessages(agentName: string, threadId: string): Promise<ScoutMessage[]> {
  return apiGet<ScoutMessage[]>(`/api/agents/${agentName}/threads/${threadId}/messages`);
}

export interface AgentTurnHandlers {
  onStart?: () => void;
  onDelta?: (delta: string, index: number) => void;
  onDone?: (payload: { thread_id: string; assistant: string; tool_calls: number }) => void;
  onError?: (detail: string) => void;
}

export async function streamAgentTurn(
  agentName: string,
  threadId: string,
  content: string,
  handlers: AgentTurnHandlers,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`/api/agents/${agentName}/threads/${threadId}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    });
  } catch (err) {
    handlers.onError?.(err instanceof Error ? err.message : "Network error");
    return;
  }
  if (!res.ok) {
    const text = await res.text();
    handlers.onError?.(text || `HTTP ${res.status}`);
    return;
  }
  const reader = res.body?.getReader();
  if (!reader) {
    handlers.onError?.("No response body");
    return;
  }
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    let value: Uint8Array | undefined;
    let done: boolean;
    try {
      ({ done, value } = await reader.read());
    } catch (err) {
      handlers.onError?.(err instanceof Error ? err.message : "Stream error");
      return;
    }
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const { frames, rest } = takeFrames(buffer);
    buffer = rest;
    for (const frame of frames) {
      if (frame.event === "start") {
        handlers.onStart?.();
      } else if (frame.event === "delta") {
        try {
          const data = JSON.parse(frame.data) as { delta: string; index: number };
          handlers.onDelta?.(data.delta, data.index);
        } catch {
          // ignore malformed delta
        }
      } else if (frame.event === "done") {
        try {
          handlers.onDone?.(JSON.parse(frame.data) as { thread_id: string; assistant: string; tool_calls: number });
        } catch {
          // ignore
        }
      } else if (frame.event === "error") {
        try {
          const data = JSON.parse(frame.data) as { detail?: string };
          handlers.onError?.(data.detail ?? frame.data);
        } catch {
          handlers.onError?.(frame.data);
        }
      }
    }
  }
}

export function fetchAgentPrompt(agentName: string): Promise<AgentPrompt> {
  return apiGet<AgentPrompt>(`/api/agents/${agentName}/prompt`);
}

export function saveAgentPrompt(agentName: string, content: string): Promise<AgentPrompt> {
  return apiSend<AgentPrompt>(`/api/agents/${agentName}/prompt`, "PUT", { content });
}
```

- [ ] **Step 3: Create `web/src/hooks/useAgentChat.ts`**

```ts
import { useCallback, useState } from "react";
import { streamAgentTurn } from "../api/agent-chat";

export function useAgentChat(
  agentName: string,
  threadId: string | null,
  onTurnDone?: () => void,
  onTurnError?: () => void,
) {
  const [streaming, setStreaming] = useState(false);
  const [assistantText, setAssistantText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [toolCalls, setToolCalls] = useState(0);

  const send = useCallback(
    async (content: string) => {
      if (!threadId) return;
      setStreaming(true);
      setError(null);
      setAssistantText("");
      setToolCalls(0);
      try {
        await streamAgentTurn(agentName, threadId, content, {
          onStart: () => setStreaming(true),
          onDelta: (delta) => setAssistantText((prev) => prev + delta),
          onDone: (payload) => {
            setToolCalls(payload.tool_calls);
            onTurnDone?.();
          },
          onError: (detail) => {
            setError(detail);
            onTurnError?.();
          },
        });
      } finally {
        setStreaming(false);
      }
    },
    [agentName, threadId, onTurnDone, onTurnError],
  );

  return { streaming, assistantText, error, toolCalls, send };
}
```

- [ ] **Step 4: Make `useScoutChat` delegate**

Rewrite `web/src/hooks/useScoutChat.ts`:

```ts
import { useAgentChat } from "./useAgentChat";

export function useScoutChat(threadId: string | null, onTurnDone?: () => void, onTurnError?: () => void) {
  return useAgentChat("discovery", threadId, onTurnDone, onTurnError);
}
```

- [ ] **Step 5: Write `web/src/api/agent-chat.test.ts`**

```ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchAgentPrompt, fetchAgentThreads, saveAgentPrompt, streamAgentTurn } from "./agent-chat";

afterEach(() => {
  vi.unstubAllGlobals();
});

function jsonResponse(body: unknown) {
  return { ok: true, status: 200, json: async () => body };
}

describe("agent-chat api", () => {
  it("fetchAgentThreads hits the agent-scoped URL", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([]));
    vi.stubGlobal("fetch", fetchMock);
    await fetchAgentThreads("head");
    expect(fetchMock).toHaveBeenCalledWith("/api/agents/head/threads?limit=50", expect.anything());
  });

  it("fetchAgentPrompt GETs the prompt file", async () => {
    const prompt = { agent_name: "head", exists: true, content: "# x", resolved_prompt: "# x" };
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(prompt));
    vi.stubGlobal("fetch", fetchMock);
    await fetchAgentPrompt("head");
    expect(fetchMock).toHaveBeenCalledWith("/api/agents/head/prompt", expect.anything());
  });

  it("saveAgentPrompt PUTs the content", async () => {
    const prompt = { agent_name: "head", exists: true, content: "x", resolved_prompt: "x" };
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(prompt));
    vi.stubGlobal("fetch", fetchMock);
    const out = await saveAgentPrompt("head", "x");
    expect(out.content).toBe("x");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/agents/head/prompt",
      expect.objectContaining({ method: "PUT", body: JSON.stringify({ content: "x" }) }),
    );
  });
});
```

- [ ] **Step 6: Run the new tests**

Run: `npm test -- --run src/api/agent-chat.test.ts` (workdir `web`)
Expected: PASS (3 tests).

- [ ] **Step 7: Run the existing scout/chat tests (regression)**

Run: `npm test -- --run src/hooks/useScoutChat.test.ts src/api/scout.test.ts` (workdir `web`)
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add web/src/api/agent-chat.ts web/src/api/agent-chat.test.ts web/src/api/types.ts web/src/hooks/useAgentChat.ts web/src/hooks/useScoutChat.ts
git commit -m "feat(agent-chat): frontend agent chat + prompt API helpers"
```

---

### Task 6: Generic `AgentChat` component + ScoutHQ wiring

**Files:**
- Create: `web/src/components/AgentChat.tsx`, `web/src/components/AgentChat.test.tsx`
- Modify: `web/src/components/ScoutChat.tsx`, `web/src/pages/ScoutHQ.tsx`

**Interfaces:**
- Consumes: `web/src/api/agent-chat.ts` (Task 5), `useAgentChat` hook, `ToolActivityCard`, `StatusBadge`.
- Produces:
  - `<AgentChat agentName="head" label="Head" />` — thread list + messages + streaming input, exactly like ScoutChat.
  - `ScoutChat` becomes a wrapper: `<AgentChat agentName="discovery" label="Scout" />`.

- [ ] **Step 1: Write the failing component test**

`web/src/components/AgentChat.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import * as agentChatApi from "../api/agent-chat";
import { AgentChat } from "./AgentChat";

vi.mock("../api/agent-chat", () => ({
  fetchAgentThreads: vi.fn(),
  createAgentThread: vi.fn(),
  fetchAgentMessages: vi.fn(),
  streamAgentTurn: vi.fn(),
}));

function renderChat() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AgentChat agentName="head" label="Head" />
    </QueryClientProvider>,
  );
}

describe("AgentChat", () => {
  it("lists threads for the agent", async () => {
    vi.mocked(agentChatApi.fetchAgentThreads).mockResolvedValue([
      { id: "t1", title: "planning", created_at: null, updated_at: null },
    ]);
    renderChat();
    expect(await screen.findByText("planning")).toBeInTheDocument();
  });

  it("sends a message via streamAgentTurn", async () => {
    vi.mocked(agentChatApi.fetchAgentThreads).mockResolvedValue([
      { id: "t1", title: "planning", created_at: null, updated_at: null },
    ]);
    vi.mocked(agentChatApi.fetchAgentMessages).mockResolvedValue([]);
    vi.mocked(agentChatApi.streamAgentTurn).mockImplementation(async (_name, _tid, _c, handlers) => {
      handlers.onStart?.();
      handlers.onDelta?.("hello", 0);
      handlers.onDone?.({ thread_id: "t1", assistant: "hello", tool_calls: 0 });
    });
    renderChat();

    const pill = await screen.findByText("planning");
    fireEvent.click(pill);

    const input = screen.getByPlaceholderText("Message the Head…");
    fireEvent.change(input, { target: { value: "plan next quarter" } });
    fireEvent.click(screen.getByText("Send"));

    await waitFor(() =>
      expect(agentChatApi.streamAgentTurn).toHaveBeenCalledWith(
        "head",
        "t1",
        "plan next quarter",
        expect.anything(),
      ),
    );
    expect(await screen.findByText("hello")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npm test -- --run src/components/AgentChat.test.tsx` (workdir `web`)
Expected: FAIL (no such module `../components/AgentChat`).

- [ ] **Step 3: Create `web/src/components/AgentChat.tsx`**

Copy the current `ScoutChat.tsx` body, parameterized:

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import {
  createAgentThread,
  fetchAgentMessages,
  fetchAgentThreads,
} from "../api/agent-chat";
import { useAgentChat } from "../hooks/useAgentChat";
import { ToolActivityCard } from "./ToolActivityCard";

export function AgentChat({ agentName, label }: { agentName: string; label: string }) {
  const qc = useQueryClient();
  const [threadId, setThreadId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  const { data: threads } = useQuery({
    queryKey: ["agent-threads", agentName],
    queryFn: () => fetchAgentThreads(agentName),
  });
  const { data: messages } = useQuery({
    queryKey: ["agent-messages", agentName, threadId],
    queryFn: () => (threadId ? fetchAgentMessages(agentName, threadId) : Promise.resolve([])),
    enabled: Boolean(threadId),
  });

  const create = useMutation({
    mutationFn: () => createAgentThread(agentName, "New chat"),
    onSuccess: (t) => {
      qc.invalidateQueries({ queryKey: ["agent-threads", agentName] });
      setThreadId(t.id);
    },
  });

  const invalidateMessages = () => {
    qc.invalidateQueries({ queryKey: ["agent-messages", agentName, threadId] });
  };

  const { streaming, assistantText, error, toolCalls, send } = useAgentChat(
    agentName,
    threadId,
    invalidateMessages,
    invalidateMessages,
  );

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, assistantText]);

  return (
    <div className="scout-chat">
      <div className="scout-chat-threads">
        <button className="btn" type="button" onClick={() => create.mutate()} disabled={create.isPending}>
          + New thread
        </button>
        {threads?.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`thread-pill ${t.id === threadId ? "active" : ""}`}
            onClick={() => setThreadId(t.id)}
          >
            {t.title ?? "Untitled"}
          </button>
        ))}
      </div>

      <div className="scout-chat-messages">
        {!threadId ? (
          <p className="muted">Select or create a thread to start chatting with the {label}.</p>
        ) : (
          <>
            {messages?.map((m) => {
              if (m.role === "tool") {
                return <ToolActivityCard key={m.id} message={m} />;
              }
              return (
                <div key={m.id} className={`chat-bubble ${m.role}`}>
                  {m.content ?? ""}
                </div>
              );
            })}
            {streaming && assistantText ? <div className="chat-bubble assistant">{assistantText}</div> : null}
            {streaming ? <div className="muted">{label} is thinking{toolCalls > 0 ? ` · ${toolCalls} tool call(s)` : ""}…</div> : null}
            {error ? <div className="flash err">{error}</div> : null}
          </>
        )}
        <div ref={bottomRef} />
      </div>

      <form
        className="scout-chat-input"
        onSubmit={(e) => {
          e.preventDefault();
          const text = draft.trim();
          if (!text || !threadId) return;
          setDraft("");
          void send(text);
        }}
      >
        <input
          type="text"
          placeholder={threadId ? `Message the ${label}…` : "Create a thread first"}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          disabled={!threadId || streaming}
        />
        <button className="btn" type="submit" disabled={!threadId || streaming || !draft.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
```

- [ ] **Step 4: Make ScoutChat a wrapper**

Rewrite `web/src/components/ScoutChat.tsx`:

```tsx
import { AgentChat } from "./AgentChat";

export function ScoutChat() {
  return <AgentChat agentName="discovery" label="Scout" />;
}
```

- [ ] **Step 5: Run the new test + scout regression**

Run: `npm test -- --run src/components/AgentChat.test.tsx` (workdir `web`)
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add web/src/components/AgentChat.tsx web/src/components/AgentChat.test.tsx web/src/components/ScoutChat.tsx
git commit -m "feat(agent-chat): generic AgentChat component; ScoutChat delegates"
```

---

### Task 7: `AgentPromptEditor` + Agent detail page wiring

**Files:**
- Create: `web/src/components/AgentPromptEditor.tsx`, `web/src/components/AgentPromptEditor.test.tsx`
- Modify: `web/src/pages/AgentsDetail.tsx`, `web/src/pages/AgentsDetail.test.tsx` (new)

**Interfaces:**
- Consumes: `fetchAgentPrompt`/`saveAgentPrompt` from `web/src/api/agent-chat.ts` (Task 5).
- Produces:
  - `<AgentPromptEditor agentName="head" />` — loads prompt, textarea, Save, flash, precedence hint.
  - `AgentsDetail` mounts `<AgentChat>` + `<AgentPromptEditor>` for `head` and `qualifier`.

- [ ] **Step 1: Write the failing editor test**

`web/src/components/AgentPromptEditor.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import * as agentChatApi from "../api/agent-chat";
import { AgentPromptEditor } from "./AgentPromptEditor";

vi.mock("../api/agent-chat", () => ({
  fetchAgentPrompt: vi.fn(),
  saveAgentPrompt: vi.fn(),
}));

function renderEditor() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AgentPromptEditor agentName="head" />
    </QueryClientProvider>,
  );
}

describe("AgentPromptEditor", () => {
  it("loads and shows the prompt", async () => {
    vi.mocked(agentChatApi.fetchAgentPrompt).mockResolvedValue({
      agent_name: "head",
      exists: true,
      content: "# Head\n\nBe decisive.",
      resolved_prompt: "# Head\n\nBe decisive.",
    });
    renderEditor();
    expect(await screen.findByDisplayValue("# Head\n\nBe decisive.")).toBeInTheDocument();
  });

  it("saves edits and flashes", async () => {
    vi.mocked(agentChatApi.fetchAgentPrompt).mockResolvedValue({
      agent_name: "head",
      exists: true,
      content: "old",
      resolved_prompt: "old",
    });
    vi.mocked(agentChatApi.saveAgentPrompt).mockResolvedValue({
      agent_name: "head",
      exists: true,
      content: "new",
      resolved_prompt: "new",
    });
    renderEditor();
    const ta = await screen.findByDisplayValue("old");
    fireEvent.change(ta, { target: { value: "new" } });
    fireEvent.click(screen.getByText("Save prompt"));
    await waitFor(() =>
      expect(agentChatApi.saveAgentPrompt).toHaveBeenCalledWith("head", "new"),
    );
    expect(await screen.findByText("Prompt saved.")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npm test -- --run src/components/AgentPromptEditor.test.tsx` (workdir `web`)
Expected: FAIL (no such module `../components/AgentPromptEditor`).

- [ ] **Step 3: Create `web/src/components/AgentPromptEditor.tsx`**

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { fetchAgentPrompt, saveAgentPrompt } from "../api/agent-chat";

export function AgentPromptEditor({ agentName }: { agentName: string }) {
  const qc = useQueryClient();
  const [draft, setDraft] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const [flashErr, setFlashErr] = useState(false);

  const { data: prompt } = useQuery({
    queryKey: ["agent-prompt", agentName],
    queryFn: () => fetchAgentPrompt(agentName),
  });

  const save = useMutation({
    mutationFn: () => saveAgentPrompt(agentName, draft ?? ""),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agent-prompt", agentName] });
      setFlash("Prompt saved.");
      setFlashErr(false);
    },
    onError: (e: Error) => {
      setFlash(e.message);
      setFlashErr(true);
    },
  });

  if (!prompt) return <p className="muted">Loading prompt…</p>;

  return (
    <div className="panel">
      <h3>System prompt (agent.md)</h3>
      {flash ? <div className={`flash ${flashErr ? "err" : ""}`}>{flash}</div> : null}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <div className="form-row">
          <textarea
            rows={12}
            value={draft ?? prompt.content}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="# System Prompt — Agent"
          />
        </div>
        <button className="btn" type="submit" disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Save prompt"}
        </button>
      </form>
      <p className="muted" style={{ marginTop: 8 }}>
        This edits <code>prompts/{agentName}.md</code> in the repo. If a DB profile
        override exists, it takes precedence; edit the Mission prompt above to clear it.
      </p>
    </div>
  );
}
```

- [ ] **Step 4: Write `web/src/pages/AgentsDetail.test.tsx`**

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import * as agentsApi from "../api/agents";
import * as agentChatApi from "../api/agent-chat";
import AgentsDetail from "./AgentsDetail";

vi.mock("../api/agents", () => ({
  fetchAgent: vi.fn(),
  fetchProviders: vi.fn(),
  updateAgent: vi.fn(),
  deleteProviderKey: vi.fn(),
  upsertProviderKey: vi.fn(),
  startScout: vi.fn(),
  finishScout: vi.fn(),
}));

vi.mock("../api/agent-chat", () => ({
  fetchAgentThreads: vi.fn(),
  createAgentThread: vi.fn(),
  fetchAgentMessages: vi.fn(),
  fetchAgentPrompt: vi.fn(),
  saveAgentPrompt: vi.fn(),
}));

function renderDetail(name: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }} initialEntries={[`/agents/${name}`]}>
        <Routes>
          <Route path="/agents/:name" element={<AgentsDetail />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AgentsDetail", () => {
  it("renders chat + prompt editor for head", async () => {
    vi.mocked(agentsApi.fetchAgent).mockResolvedValue({
      agent_name: "head",
      display_name: "Head",
      mission_prompt: "m",
      enabled_tools: ["llm_chat"],
      model: null,
      default_seed_query: null,
      updated_at: null,
      available_tools: [],
    });
    vi.mocked(agentsApi.fetchProviders).mockResolvedValue([]);
    vi.mocked(agentChatApi.fetchAgentThreads).mockResolvedValue([]);
    vi.mocked(agentChatApi.fetchAgentPrompt).mockResolvedValue({
      agent_name: "head",
      exists: true,
      content: "# Head",
      resolved_prompt: "# Head",
    });

    renderDetail("head");

    expect(await screen.findByText("Head")).toBeInTheDocument();
    expect(await screen.findByText("System prompt (agent.md)")).toBeInTheDocument();
    expect(screen.getByText("Message the Head…").closest("input")).toBeInTheDocument();
  });
});
```

Note: `fetchAgentPrompt` resolves to `content: "# Head"` so the editor textarea's `placeholder`/value don't conflict with `getByText("Head")` (the `<h2>` display name). If the assertion becomes ambiguous, assert on the editor panel heading only.

- [ ] **Step 5: Wire `AgentsDetail.tsx`**

Add imports at the top of `web/src/pages/AgentsDetail.tsx`:

```tsx
import { AgentChat } from "../components/AgentChat";
import { AgentPromptEditor } from "../components/AgentPromptEditor";
```

After the `isDiscovery` Scout-controls block (after line 123) and before the `Profile` panel, add:

```tsx
      {!isDiscovery ? (
        <>
          <div className="panel">
            <h3>Chat with {agent.display_name}</h3>
            <AgentChat agentName={name} label={agent.display_name} />
          </div>
          <AgentPromptEditor agentName={name} />
        </>
      ) : null}
```

- [ ] **Step 6: Run the frontend tests**

Run: `npm test -- --run src/components/AgentPromptEditor.test.tsx src/pages/AgentsDetail.test.tsx` (workdir `web`)
Expected: PASS (2 editor tests + 1 page test).

- [ ] **Step 7: Commit**

```bash
git add web/src/components/AgentPromptEditor.tsx web/src/components/AgentPromptEditor.test.tsx web/src/pages/AgentsDetail.tsx web/src/pages/AgentsDetail.test.tsx
git commit -m "feat(agent-chat): AgentPromptEditor + chat panels on agent detail page"
```

---

### Task 8: Verify + ship

- [ ] **Step 1: Full frontend test + build**

Run: `npm test -- --run` then `npm run build` (workdir `web`)
Expected: all tests pass; TypeScript compiles cleanly.

- [ ] **Step 2: Full backend suite**

Run: `python -m pytest tests/ -q --no-header`
Expected: all pass (existing 104 passed/6 skipped + new tests).

- [ ] **Step 3: Rebuild web image + deploy**

Run: `docker compose build web && docker compose up -d web`

- [ ] **Step 4: Live verify**

- `docker compose exec web grep -o "Head HQ" /usr/share/nginx/html/assets/*.js` still present (bundle not broken).
- `curl -s http://localhost:8000/api/agents/head/prompt` → `{agent_name: "head", exists: true, ...}` (head.md exists).
- `curl -s http://localhost:8000/api/agents/qualifier/prompt` → `exists: true` (qualifier.md created in Task 4).
- `curl -s -X POST http://localhost:8000/api/agents/head/threads -H "Content-Type: application/json" -d '{"title":"verify"}'` → 201 thread.
- Post a chat message to that thread and confirm the SSE body streams `start`/`delta`/`done`.
- Open the UI at `http://localhost:3000/agents/head`: chat panel + "System prompt (agent.md)" editor render; send a message; edit the prompt and confirm it persists.

- [ ] **Step 5: Commit any follow-up fixes**

If verification surfaces issues, fix + rerun Task 8 steps, then commit.

- [ ] **Step 6: Update the spec status**

In `docs/superpowers/specs/2026-08-08-agent-chat-design.md`, change the status line to `Implemented (committed)`.
```bash
git add docs/superpowers/specs/2026-08-08-agent-chat-design.md
git commit -m "docs(agent-chat): mark design spec implemented"
```
