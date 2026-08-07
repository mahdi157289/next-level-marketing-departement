# Scout HQ Backend — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the backend for Scout HQ — persisted chat threads/messages, mission-board pipeline-run listing, KPI stats, and a tool-capable Scout chat engine — all exposed under a unified `/api` prefix.

**Architecture:** Follows the existing layered pattern: `db/models.py` (SQLAlchemy) → `crm/service.py` (pure logic, `_session()` + `_row_to_dict`) → `crm/schemas.py` (Pydantic) → routers. New `crm/scout.py` holds the chat engine (pure logic, no FastAPI). A new `api/router.py` mounts at `/api` and includes the existing `crm_router`, plus new endpoints. The chat engine uses the Scout's own model/mission/tools from `agent_profiles`, with a hybrid native-tools → JSON-decision fallback.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Pydantic v2, `sse-starlette` (or raw `StreamingResponse`), existing `lm_client`, existing `tools.registry.resolve_callable`.

## Global Constraints

- Follow the exact existing patterns: `_session()` + `_row_to_dict()` in `crm/service.py`; Pydantic DTOs in `crm/schemas.py` with `model_config = {"from_attributes": True}`.
- No FastAPI imports in `crm/*` logic modules (mirror `crm/service.py` docstring "no FastAPI imports").
- Chat turns MUST NOT touch `crm/runner.py`'s single active-slot global — chat is conversational, per-turn, independent.
- Tool calls capped at **5 iterations** per user message.
- All new tables created via one Alembic migration `0004_scout_chat` with `down_revision = "20260714_0003"`.
- Python is 3.9 on host, 3.11 in Docker — avoid `str | None` union syntax in new files (use `Optional[str]`); tests run via Docker or against the real DB like `tests/test_crm_api.py`.
- DB tests use `DATABASE_URL` (Postgres) — same pattern as `tests/test_crm_api.py` (cleanup created rows).

---

### Task 1: Scout chat tables (models + migration)

**Files:**
- Modify: `db/models.py` (append two models)
- Create: `migrations/versions/20260805_0004_scout_chat.py`
- Test: `tests/test_scout_chat.py`

**Interfaces:**
- Consumes: existing `db/session.py` `SessionLocal`, existing `crm/service.py` `_session()` pattern.
- Produces: `ScoutThread` and `ScoutMessage` SQLAlchemy models with columns:
  - ScoutThread: `id` UUID PK, `title` TEXT, `created_at` TIMESTAMP, `updated_at` TIMESTAMP
  - ScoutMessage: `id` UUID PK, `thread_id` UUID FK, `role` VARCHAR(16), `content` TEXT nullable, `tool_name` VARCHAR(64) nullable, `tool_args` JSON nullable, `tool_result` JSON nullable, `created_at` TIMESTAMP

- [ ] **Step 1: Write the failing test**

```python
"""DB round-trip for scout chat tables — requires DATABASE_URL (like test_crm_api.py)."""
from __future__ import annotations

import os
import uuid
from typing import Optional

import pytest
from sqlalchemy import create_engine, text


def _database_url() -> Optional[str]:
    return os.getenv("DATABASE_URL")


@pytest.mark.skipif(not _database_url(), reason="DATABASE_URL not set")
def test_scout_tables_exist_and_roundtrip():
    eng = create_engine(_database_url())
    thread_id = uuid.uuid4()
    msg_id = uuid.uuid4()
    try:
        with eng.begin() as conn:
            conn.execute(
                text("INSERT INTO scout_threads (id, title, created_at, updated_at) "
                     "VALUES (:id, :title, NOW(), NOW())"),
                {"id": thread_id, "title": "plan-test"},
            )
            conn.execute(
                text("INSERT INTO scout_messages (id, thread_id, role, content, tool_name, "
                     "tool_args, tool_result, created_at) "
                     "VALUES (:id, :thread_id, :role, :content, :tool_name, :tool_args, :tool_result, NOW())"),
                {
                    "id": msg_id,
                    "thread_id": thread_id,
                    "role": "assistant",
                    "content": "hello",
                    "tool_name": None,
                    "tool_args": None,
                    "tool_result": None,
                },
            )
        with eng.connect() as conn:
            row = conn.execute(
                text("SELECT role, content FROM scout_messages WHERE id = :id"),
                {"id": msg_id},
            ).fetchone()
            assert row is not None
            assert row[0] == "assistant"
            assert row[1] == "hello"
    finally:
        with eng.begin() as conn:
            conn.execute(text("DELETE FROM scout_messages WHERE id = :id"), {"id": msg_id})
            conn.execute(text("DELETE FROM scout_threads WHERE id = :id"), {"id": thread_id})
        eng.dispose()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scout_chat.py -v`
Expected: FAIL — `sqlalchemy.exc.ProgrammingError: relation "scout_threads" does not exist` (tables not created yet)

- [ ] **Step 3: Add the two models to `db/models.py`**

Append after the `LeadEvent` class (end of file):

```python
class ScoutThread(Base):
    __tablename__ = "scout_threads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(Text)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)


class ScoutMessage(Base):
    __tablename__ = "scout_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id = Column(UUID(as_uuid=True), nullable=False)
    role = Column(String(16), nullable=False)
    content = Column(Text)
    tool_name = Column(String(64))
    tool_args = Column(JSON)
    tool_result = Column(JSON)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
```

- [ ] **Step 4: Create the migration**

Create `migrations/versions/20260805_0004_scout_chat.py`:

```python
"""scout chat tables

Revision ID: 20260805_0004
Revises: 20260714_0003
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260805_0004"
down_revision: Union[str, None] = "20260714_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scout_threads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(), nullable=True),
    )
    op.create_table(
        "scout_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("tool_name", sa.String(length=64), nullable=True),
        sa.Column("tool_args", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("tool_result", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=True),
    )
    op.create_index("ix_scout_messages_thread_id", "scout_messages", ["thread_id"])


def downgrade() -> None:
    op.drop_index("ix_scout_messages_thread_id", table_name="scout_messages")
    op.drop_table("scout_messages")
    op.drop_table("scout_threads")
```

- [ ] **Step 5: Run the migration**

Run: `alembic upgrade head`
Expected: `Running upgrade 20260714_0003 -> 20260805_0004`

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_scout_chat.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add db/models.py migrations/versions/20260805_0004_scout_chat.py tests/test_scout_chat.py
git commit -m "feat: scout chat tables (threads + messages) with migration"
```

---

### Task 2: Scout thread/message service functions

**Files:**
- Modify: `crm/service.py`
- Test: `tests/test_scout_service.py`

**Interfaces:**
- Consumes: `ScoutThread`, `ScoutMessage` models from Task 1; `_session()`, `_row_to_dict()`, `uuid`, `select` already in `crm/service.py`.
- Produces:
  - `create_scout_thread(title: Optional[str]) -> Dict[str, Any]`
  - `list_scout_threads(limit: int = 50) -> List[Dict[str, Any]]` (ordered by `created_at desc`)
  - `add_scout_message(thread_id: str, role: str, content: Optional[str] = None, tool_name: Optional[str] = None, tool_args: Optional[Dict[str, Any]] = None, tool_result: Optional[Any] = None) -> Dict[str, Any]`
  - `list_scout_messages(thread_id: str, limit: int = 200) -> List[Dict[str, Any]]` (ordered by `created_at asc`)

- [ ] **Step 1: Write the failing test**

```python
"""Service-layer tests for scout chat — requires DATABASE_URL."""
from __future__ import annotations

import os
import uuid
from typing import Optional

import pytest

from crm import service


def _database_url() -> Optional[str]:
    return os.getenv("DATABASE_URL")


@pytest.mark.skipif(not _database_url(), reason="DATABASE_URL not set")
def test_scout_thread_and_message_crud():
    thread = service.create_scout_thread("test thread")
    tid = str(thread["id"])
    try:
        assert thread["title"] == "test thread"

        m1 = service.add_scout_message(tid, "user", content="find leads")
        m2 = service.add_scout_message(tid, "assistant", content="done", tool_name="web_search")
        assert m1["role"] == "user"
        assert m2["tool_name"] == "web_search"

        msgs = service.list_scout_messages(tid)
        assert [m["role"] for m in msgs] == ["user", "assistant"]

        threads = service.list_scout_threads(limit=50)
        assert any(str(t["id"]) == tid for t in threads)
    finally:
        eng = __import__("sqlalchemy").create_engine(_database_url())
        with eng.begin() as conn:
            conn.execute(__import__("sqlalchemy").text("DELETE FROM scout_messages WHERE thread_id = :id"), {"id": uuid.UUID(tid)})
            conn.execute(__import__("sqlalchemy").text("DELETE FROM scout_threads WHERE id = :id"), {"id": uuid.UUID(tid)})
        eng.dispose()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scout_service.py -v`
Expected: FAIL — `ImportError: cannot import name 'create_scout_thread' from 'crm.service'`

- [ ] **Step 3: Add the four service functions**

Add to `crm/service.py`, after the `# --- Agent profiles ---` section (before `tools_catalog`), matching the existing `_session()`/`_row_to_dict()` style:

```python
# --- Scout chat ---


def create_scout_thread(title: Optional[str] = None) -> Dict[str, Any]:
    session = _session()
    try:
        thread = ScoutThread(id=uuid.uuid4(), title=title or "New scout thread")
        session.add(thread)
        session.commit()
        session.refresh(thread)
        return _row_to_dict(thread)
    finally:
        session.close()


def list_scout_threads(limit: int = 50) -> List[Dict[str, Any]]:
    session = _session()
    try:
        rows = session.scalars(
            select(ScoutThread).order_by(ScoutThread.created_at.desc()).limit(limit)
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
        )
        session.add(msg)
        session.commit()
        session.refresh(msg)
        return _row_to_dict(msg)
    finally:
        session.close()


def list_scout_messages(thread_id: str, limit: int = 200) -> List[Dict[str, Any]]:
    session = _session()
    try:
        rows = session.scalars(
            select(ScoutMessage)
            .where(ScoutMessage.thread_id == uuid.UUID(thread_id))
            .order_by(ScoutMessage.created_at.asc())
            .limit(limit)
        ).all()
        return [_row_to_dict(r) for r in rows]
    finally:
        session.close()
```

Update the import at the top of `crm/service.py`:

```python
from db.models import (
    AgentProfile,
    AgentRun,
    Lead,
    LeadEvent,
    LeadStatus,
    PipelineRun,
    RunStatus,
    ScoutMessage,
    ScoutThread,
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_scout_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add crm/service.py tests/test_scout_service.py
git commit -m "feat: scout thread/message service functions"
```

---

### Task 3: `list_pipeline_runs` service + schemas

**Files:**
- Modify: `crm/service.py`, `crm/schemas.py`
- Test: `tests/test_pipeline_runs_list.py`

**Interfaces:**
- Consumes: `PipelineRun`, `AgentRun` models.
- Produces:
  - `list_pipeline_runs(limit: int = 50) -> List[Dict[str, Any]]` — each row is the pipeline-run dict plus an extra `"agent_run_count"` key.
  - `PipelineRunListOut` Pydantic model = `PipelineRunOut` fields + `agent_run_count: int`.

- [ ] **Step 1: Write the failing test**

```python
"""Pipeline-run listing with agent-run counts — requires DATABASE_URL."""
from __future__ import annotations

import os
import uuid
from typing import Optional

import pytest

from crm import service


def _database_url() -> Optional[str]:
    return os.getenv("DATABASE_URL")


@pytest.mark.skipif(not _database_url(), reason="DATABASE_URL not set")
def test_list_pipeline_runs_has_counts():
    run = service.start_pipeline_run("pytest", "list test", {"mode": "discovery_only"})
    rid = str(run["id"])
    try:
        service.start_agent_run(rid, "discovery", model="m", input_summary="s")
        rows = service.list_pipeline_runs(limit=50)
        assert any(str(r["id"]) == rid and r.get("agent_run_count", 0) >= 1 for r in rows), rows
    finally:
        eng = __import__("sqlalchemy").create_engine(_database_url())
        with eng.begin() as conn:
            conn.execute(__import__("sqlalchemy").text("DELETE FROM agent_runs WHERE pipeline_run_id = :id"), {"id": uuid.UUID(rid)})
            conn.execute(__import__("sqlalchemy").text("DELETE FROM pipeline_runs WHERE id = :id"), {"id": uuid.UUID(rid)})
        eng.dispose()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pipeline_runs_list.py -v`
Expected: FAIL — `AttributeError: module 'crm.service' has no attribute 'list_pipeline_runs'`

- [ ] **Step 3: Add the service function**

Add to `crm/service.py` in the `# --- Pipeline runs ---` section, after `latest_head_assignment`:

```python
def list_pipeline_runs(limit: int = 50) -> List[Dict[str, Any]]:
    session = _session()
    try:
        rows = session.scalars(
            select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(limit)
        ).all()
        out: List[Dict[str, Any]] = []
        for r in rows:
            d = _row_to_dict(r)
            n = session.scalar(
                select(func.count())
                .select_from(AgentRun)
                .where(AgentRun.pipeline_run_id == r.id)
            )
            d["agent_run_count"] = int(n or 0)
            out.append(d)
        return out
    finally:
        session.close()
```

Update the `from sqlalchemy import select, text` import to include `func`:

```python
from sqlalchemy import func, select, text
```

- [ ] **Step 4: Add the DTO to `crm/schemas.py`**

Add after `PipelineRunOut`:

```python
class PipelineRunListOut(PipelineRunOut):
    agent_run_count: int = 0
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_pipeline_runs_list.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add crm/service.py crm/schemas.py tests/test_pipeline_runs_list.py
git commit -m "feat: list_pipeline_runs with agent-run counts"
```

---

### Task 4: `/api` router (unified prefix)

**Files:**
- Create: `api/router.py`
- Modify: `api/main.py`
- Test: `tests/test_api_router.py`

**Interfaces:**
- Consumes: `crm.router.router` (all existing `/crm/*` endpoints), new `list_pipeline_runs`, `list_scout_threads`, `create_scout_thread`, `list_scout_messages`.
- Produces: a FastAPI `APIRouter` mounted at `/api` exposing:
  - `/api/leads`, `/api/agent-runs`, `/api/agents`, `/api/pipeline-runs/{id}` (inherited from `crm_router`)
  - `GET /api/pipeline-runs` → `list[PipelineRunListOut]`
  - `GET /api/scout/threads` → `list[ScoutThreadOut]`
  - `POST /api/scout/threads` → `ScoutThreadOut` (body `{title?: str}`)
  - `GET /api/scout/threads/{thread_id}/messages` → `list[ScoutMessageOut]`

- [ ] **Step 1: Write the failing test**

```python
"""Unified /api prefix — reuses the crm router + new scout/pipeline endpoints."""
from __future__ import annotations

import os
import uuid
from typing import Optional

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text


def _database_url() -> Optional[str]:
    return os.getenv("DATABASE_URL")


@pytest.fixture
def client():
    from api.main import app

    return TestClient(app)


def test_api_health_and_crm_prefix(client):
    r = client.get("/api/crm/health")
    assert r.status_code == 200, r.text


def test_api_leads_via_crm_router(client):
    r = client.get("/api/crm/leads?limit=5")
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)


def test_api_pipeline_runs_list(client):
    r = client.get("/api/pipeline-runs?limit=5")
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)


@pytest.mark.skipif(not _database_url(), reason="DATABASE_URL not set")
def test_api_scout_thread_crud(client):
    r = client.post("/api/scout/threads", json={"title": "api test"})
    assert r.status_code == 201, r.text
    thread_id = r.json()["id"]

    r = client.get("/api/scout/threads")
    assert any(t["id"] == thread_id for t in r.json())

    r = client.get(f"/api/scout/threads/{thread_id}/messages")
    assert r.status_code == 200, r.text
    assert r.json() == []

    eng = create_engine(_database_url())
    with eng.begin() as conn:
        conn.execute(text("DELETE FROM scout_messages WHERE thread_id = :id"), {"id": uuid.UUID(thread_id)})
        conn.execute(text("DELETE FROM scout_threads WHERE id = :id"), {"id": uuid.UUID(thread_id)})
    eng.dispose()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_router.py -v`
Expected: FAIL — the new endpoints 404 (`/api/scout/threads`, `/api/pipeline-runs`)

- [ ] **Step 3: Create `api/router.py`**

```python
"""Unified /api router for the SPA — includes the CRM REST router + new endpoints."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from crm import schemas, service
from crm.router import router as crm_router

router = APIRouter()
router.include_router(crm_router)  # exposes /api/crm/*


class ScoutThreadCreate(BaseModel):
    title: Optional[str] = None


@router.get("/pipeline-runs", response_model=List[schemas.PipelineRunListOut])
def api_list_pipeline_runs(limit: int = 50):
    return service.list_pipeline_runs(limit=limit)


@router.get("/scout/threads", response_model=List[schemas.ScoutThreadOut])
def api_list_threads(limit: int = 50):
    return service.list_scout_threads(limit=limit)


@router.post("/scout/threads", response_model=schemas.ScoutThreadOut, status_code=201)
def api_create_thread(body: ScoutThreadCreate):
    return service.create_scout_thread(body.title)


@router.get(
    "/scout/threads/{thread_id}/messages",
    response_model=List[schemas.ScoutMessageOut],
)
def api_list_messages(thread_id: str, limit: int = 200):
    try:
        return service.list_scout_messages(thread_id, limit=limit)
    except ValueError:
        raise HTTPException(status_code=422, detail="thread_id must be a UUID")
```

- [ ] **Step 4: Add the DTOs to `crm/schemas.py`**

Add after `PipelineRunListOut`:

```python
class ScoutThreadOut(BaseModel):
    id: UUID
    title: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ScoutMessageOut(BaseModel):
    id: UUID
    thread_id: UUID
    role: str
    content: Optional[str] = None
    tool_name: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None
    tool_result: Optional[Any] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
```

- [ ] **Step 5: Mount the router in `api/main.py`**

Modify `api/main.py` imports and app:

```python
from api.router import router as api_router

app = FastAPI(title="AI Marketing Department API", version="0.1.0")
app.include_router(crm_router, prefix="/crm")
app.include_router(crm_ui_router, prefix="/crm")
app.include_router(api_router, prefix="/api")
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_api_router.py -v`
Expected: PASS (4 passed)

- [ ] **Step 7: Commit**

```bash
git add api/router.py api/main.py crm/schemas.py tests/test_api_router.py
git commit -m "feat: unified /api router with pipeline-runs list and scout thread endpoints"
```

---

### Task 5: Tool-capable completion in `lm_client`

**Files:**
- Modify: `agents/lm_client.py`
- Test: `tests/test_lm_client_tools.py`

**Interfaces:**
- Consumes: `OpenAI` client already in `agents/lm_client.py`, `_get_client()`.
- Produces:
  - `chat_completion_tools(model: str, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], *, temperature: float = 0.35, max_tokens: int = 1024) -> Dict[str, Any]`
  - Returns `{"content": str, "tool_calls": List[Dict[str, Any]]}` where each tool call is `{"id": str, "name": str, "arguments": Dict[str, Any]}`.

- [ ] **Step 1: Write the failing test**

```python
"""chat_completion_tools returns content + parsed tool calls (mocked client)."""
from __future__ import annotations

import pytest


class _FakeMsg:
    content = None
    tool_calls = None
    model_extra = None


class _FakeChoice:
    def __init__(self):
        self.message = _FakeMsg()


class _FakeResp:
    def __init__(self):
        self.choices = [_FakeChoice()]


def test_returns_empty_tool_calls_when_none(monkeypatch):
    from agents import lm_client

    resp = _FakeResp()
    resp.choices[0].message.content = "ok"

    class _FakeClient:
        def chat(self):
            class _FakeCompletions:
                def create(self, **kwargs):
                    return resp
            return _FakeCompletions()

    monkeypatch.setattr(lm_client, "_get_client", lambda: _FakeClient())
    out = lm_client.chat_completion_tools("m", [{"role": "user", "content": "hi"}], tools=[])
    assert out["content"] == "ok"
    assert out["tool_calls"] == []


def test_parses_tool_calls(monkeypatch):
    from agents import lm_client

    resp = _FakeResp()
    msg = resp.choices[0].message
    msg.content = "let me search"
    msg.tool_calls = [
        type("TC", (), {
            "id": "call_1",
            "function": type("F", (), {"name": "web_search", "arguments": '{"query": "x", "max_results": 3}'}),
        })()
    ]

    class _FakeClient:
        def chat(self):
            class _FakeCompletions:
                def create(self, **kwargs):
                    return resp
            return _FakeCompletions()

    monkeypatch.setattr(lm_client, "_get_client", lambda: _FakeClient())
    out = lm_client.chat_completion_tools("m", [{"role": "user", "content": "find"}], tools=[{"type": "function", "function": {"name": "web_search"}}])
    assert out["content"] == "let me search"
    assert out["tool_calls"][0]["name"] == "web_search"
    assert out["tool_calls"][0]["arguments"]["query"] == "x"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_lm_client_tools.py -v`
Expected: FAIL — `AttributeError: module 'agents.lm_client' has no attribute 'chat_completion_tools'`

- [ ] **Step 3: Add `chat_completion_tools` to `agents/lm_client.py`**

Add after `chat_completion`:

```python
def chat_completion_tools(
    model: str,
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    *,
    temperature: float = 0.35,
    max_tokens: int = 1024,
) -> Dict[str, Any]:
    """Chat completion with OpenAI function-calling; returns content + parsed tool calls."""
    client = _get_client()
    kwargs: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tools:
        kwargs["tools"] = tools
    r = client.chat.completions.create(**kwargs)
    msg = r.choices[0].message
    content = _extract_message_text(msg)
    tool_calls: List[Dict[str, Any]] = []
    for tc in getattr(msg, "tool_calls", None) or []:
        fn = getattr(tc, "function", None)
        if fn is None:
            continue
        args_raw = getattr(fn, "arguments", None) or "{}"
        try:
            import json

            args = json.loads(args_raw)
        except Exception:
            args = {}
        tool_calls.append(
            {"id": getattr(tc, "id", None), "name": getattr(fn, "name", ""), "arguments": args}
        )
    return {"content": content, "tool_calls": tool_calls}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_lm_client_tools.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add agents/lm_client.py tests/test_lm_client_tools.py
git commit -m "feat: tool-capable chat completion in lm_client"
```

---

### Task 6: Scout chat engine (`crm/scout.py`)

**Files:**
- Create: `crm/scout.py`
- Test: `tests/test_scout_engine.py`

**Interfaces:**
- Consumes: `service.get_agent_profile("discovery")`, `service.add_scout_message`, `service.list_scout_messages`, `lm_client.chat_completion_tools`, `lm_client.chat_completion`, `tools.registry.resolve_callable`, `config.settings.get_settings`.
- Produces:
  - `run_scout_turn(thread_id: str, user_text: str, *, max_tool_iterations: int = 5) -> Dict[str, Any]` — executes one user message: persists user message, runs the model+tool loop, persists tool + assistant messages. Returns `{"thread_id": str, "assistant": str, "tool_calls": int, "message_ids": List[str]}`.
  - `_TOOLS_SCHEMA` module constant — the OpenAI `tools=` schema for `web_search` and `google_maps_search`.

- [ ] **Step 1: Write the failing test**

```python
"""Scout chat engine — pure logic, mocked LLM + tools + service."""
from __future__ import annotations

import pytest


class _FakeProfile:
    def __init__(self):
        self.model = "scout-model"
        self.mission_prompt = "You are the Scout."
        self.enabled_tools = ["web_search", "google_maps_search", "llm_chat"]


def _patch_service(monkeypatch, msgs=None, created_ids=None):
    from crm import scout

    msgs = msgs or []
    created_ids = created_ids or []

    class _FakeMessages:
        def __init__(self, items):
            self._items = items

        def __len__(self):
            return len(self._items)

        def __getitem__(self, i):
            return self._items[i]

        def __iter__(self):
            return iter(self._items)

    monkeypatch.setattr(scout.service, "get_agent_profile", lambda name: _FakeProfile())
    monkeypatch.setattr(scout.service, "add_scout_message", lambda *a, **kw: {"id": f"m{len(created_ids)}"})
    return _FakeMessages(msgs)


def test_plain_answer_no_tools(monkeypatch):
    from crm import scout
    from crm import service

    monkeypatch.setattr(scout.service, "list_scout_messages", lambda tid, limit=200: [])
    monkeypatch.setattr(
        scout.lm_client,
        "chat_completion_tools",
        lambda model, messages, tools, **kw: {"content": "I checked.", "tool_calls": []},
    )
    monkeypatch.setattr(scout.lm_client, "chat_completion", lambda *a, **kw: "I checked.")

    out = scout.run_scout_turn("thread-1", "hello")
    assert out["assistant"] == "I checked."
    assert out["tool_calls"] == 0


def test_tool_call_roundtrip(monkeypatch):
    from crm import scout

    profile = _FakeProfile()
    profile.enabled_tools = ["web_search", "google_maps_search", "llm_chat"]
    monkeypatch.setattr(scout.service, "get_agent_profile", lambda name: profile)
    monkeypatch.setattr(scout.service, "add_scout_message", lambda *a, **kw: {"id": "x"})
    monkeypatch.setattr(scout.service, "list_scout_messages", lambda tid, limit=200: [])

    # First call requests a tool; second call produces the final answer.
    calls = {"n": 0}

    def fake_tools(model, messages, tools, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "content": "",
                "tool_calls": [
                    {"id": "c1", "name": "web_search", "arguments": {"query": "plumber Tunis", "max_results": 2}}
                ],
            }
        return {"content": "Found leads.", "tool_calls": []}

    monkeypatch.setattr(scout.lm_client, "chat_completion_tools", fake_tools)

    monkeypatch.setattr(
        scout.registry,
        "resolve_callable",
        lambda tid: (lambda **kw: [{"title": "A", "url": "http://a.tn"}]) if tid == "web_search" else None,
    )

    out = scout.run_scout_turn("thread-1", "find me a plumber")
    assert out["tool_calls"] == 1
    assert out["assistant"] == "Found leads."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scout_engine.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'crm.scout'`

- [ ] **Step 3: Create `crm/scout.py`**

```python
"""Scout chat engine — conversational, tool-capable, persisted.

Pure logic (no FastAPI). Loads the Scout's own model + mission + enabled
tools from agent_profiles.discovery. Hybrid tool invocation: native OpenAI
function-calling first, JSON-decision fallback if the model rejects `tools`.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from agents import lm_client
from config.settings import get_settings
from crm import service
from tools import registry

_MAX_TOOL_ITERATIONS = 5

_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for real businesses and leads.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "max_results": {"type": "integer", "description": "Max results", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "google_maps_search",
            "description": "Find local businesses on Google Maps with contact info.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Business type / keyword"},
                    "region": {"type": "string", "description": "City, country", "default": "Tunisia"},
                    "max_results": {"type": "integer", "description": "Max results", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
]

_FALLBACK_DECISION_PROMPT = (
    "You are the Scout. Decide if you need tools. Respond with JSON only (no fences): "
    '{"tool_calls": [{"name": "web_search", "arguments": {"query": "..."}}]} '
    "or {\"tool_calls\": []} if you can answer directly."
)


def _load_scout_profile() -> Dict[str, Any]:
    s = get_settings()
    try:
        profile = service.get_agent_profile("discovery") or {}
    except Exception:
        profile = {}
    return {
        "model": profile.get("model") or s.agent_model_discovery,
        "mission_prompt": profile.get("mission_prompt") or "You are the Scout.",
        "enabled_tools": list(profile.get("enabled_tools") or []),
    }


def _tool_callable(name: str) -> Optional[Callable[..., Any]]:
    return registry.resolve_callable(name)


def _run_native_tools(messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One native function-calling round; returns tool-call dicts."""
    resp = lm_client.chat_completion_tools(
        _load_scout_profile()["model"],
        messages,
        tools=tools,
        temperature=0.2,
        max_tokens=1024,
    )
    return resp.get("tool_calls") or []


def _run_fallback_tools(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """JSON-decision fallback when the model rejects native tools."""
    user_body = _FALLBACK_DECISION_PROMPT + "\n\nLast message:\n" + (messages[-1].get("content") or "")
    try:
        text = lm_client.chat_completion(
            _load_scout_profile()["model"],
            [{"role": "user", "content": user_body}],
            temperature=0.2,
            max_tokens=256,
        )
        import json

        data = json.loads(text.strip().strip("`") or "{}")
        calls = data.get("tool_calls") or []
        return [{"id": f"fb{i}", "name": c.get("name"), "arguments": c.get("arguments") or {}} for i, c in enumerate(calls)]
    except Exception:
        return []


def _execute_tool(call: Dict[str, Any]) -> Dict[str, Any]:
    name = call.get("name") or ""
    fn = _tool_callable(name)
    args = call.get("arguments") or {}
    if fn is None:
        return {"tool_name": name, "args": args, "result": None, "error": f"tool {name} not available"}
    try:
        result = fn(**args)
        return {"tool_name": name, "args": args, "result": result, "error": None}
    except Exception as exc:
        return {"tool_name": name, "args": args, "result": None, "error": str(exc)}


def run_scout_turn(
    thread_id: str,
    user_text: str,
    *,
    max_tool_iterations: int = _MAX_TOOL_ITERATIONS,
) -> Dict[str, Any]:
    profile = _load_scout_profile()
    service.add_scout_message(thread_id, "user", content=user_text)

    history = service.list_scout_messages(thread_id, limit=200)
    messages: List[Dict[str, Any]] = [{"role": "system", "content": profile["mission_prompt"]}]
    for m in history:
        if m.get("role") == "tool":
            content = m.get("tool_name") or "tool"
            messages.append({"role": "user", "content": f"[{content} result] {m.get('tool_result')}"})
        else:
            messages.append({"role": m["role"], "content": m.get("content") or ""})

    assistant_text = ""
    tool_calls_made = 0
    message_ids: List[str] = []

    for _ in range(max_tool_iterations):
        tool_calls: List[Dict[str, Any]] = []
        try:
            resp = lm_client.chat_completion_tools(
                profile["model"],
                messages,
                tools=_TOOLS_SCHEMA,
                temperature=0.2,
                max_tokens=1024,
            )
            tool_calls = resp.get("tool_calls") or []
            assistant_text = resp.get("content") or ""
        except Exception:
            tool_calls = _run_fallback_tools(messages)
            assistant_text = ""

        if not tool_calls:
            break

        tool_calls_made += 1
        for call in tool_calls:
            outcome = _execute_tool(call)
            msg = service.add_scout_message(
                thread_id,
                "tool",
                content=f"[{outcome['tool_name']}]",
                tool_name=outcome["tool_name"],
                tool_args=outcome["args"],
                tool_result={"result": outcome["result"], "error": outcome["error"]},
            )
            message_ids.append(str(msg["id"]))
            messages.append(
                {
                    "role": "user",
                    "content": f"[{outcome['tool_name']} result] {outcome['result']}",
                }
            )

    if not assistant_text:
        assistant_text = lm_client.chat_completion(
            profile["model"],
            messages,
            temperature=0.25,
            max_tokens=1024,
        )

    msg = service.add_scout_message(thread_id, "assistant", content=assistant_text)
    message_ids.append(str(msg["id"]))

    return {
        "thread_id": thread_id,
        "assistant": assistant_text,
        "tool_calls": tool_calls_made,
        "message_ids": message_ids,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_scout_engine.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add crm/scout.py tests/test_scout_engine.py
git commit -m "feat: scout chat engine with hybrid tool invocation"
```

---

### Task 7: `GET /api/stats` (KPI aggregates)

**Files:**
- Modify: `crm/service.py`, `api/router.py`, `crm/schemas.py`
- Test: `tests/test_stats.py`

**Interfaces:**
- Consumes: `Lead`, `AgentRun`, `PipelineRun` models.
- Produces:
  - `compute_stats() -> Dict[str, Any]` with keys:
    - `leads_total: int`, `leads_by_status: Dict[str, int]`, `leads_avg_score: float`
    - `runs_today: int`, `run_success_rate: float` (percent 0-100), `recent_runs: List[Dict]` (top 5)
    - `scout_active: bool`, `scout_last_seed: Optional[str]`
  - `GET /api/stats` endpoint returning that dict.

- [ ] **Step 1: Write the failing test**

```python
"""GET /api/stats — KPI aggregates. Real DB for lead counts; runner mocked."""
from __future__ import annotations

import os
from typing import Optional

import pytest
from fastapi.testclient import TestClient


def _database_url() -> Optional[str]:
    return os.getenv("DATABASE_URL")


@pytest.fixture
def client():
    from api.main import app

    return TestClient(app)


@pytest.mark.skipif(not _database_url(), reason="DATABASE_URL not set")
def test_stats_shape(client):
    r = client.get("/api/stats")
    assert r.status_code == 200, r.text
    body = r.json()
    for key in ("leads_total", "leads_by_status", "leads_avg_score", "runs_today", "run_success_rate", "recent_runs", "scout_active", "scout_last_seed"):
        assert key in body, f"missing {key}"
    assert isinstance(body["leads_by_status"], dict)
    assert isinstance(body["recent_runs"], list)
    assert 0.0 <= body["run_success_rate"] <= 100.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_stats.py -v`
Expected: FAIL — 404 for `/api/stats`

- [ ] **Step 3: Add `compute_stats` to `crm/service.py`**

Add after `list_pipeline_runs`:

```python
from datetime import datetime


def compute_stats() -> Dict[str, Any]:
    session = _session()
    try:
        today = datetime.utcnow().date()
        start_today = datetime(today.year, today.month, today.day)
        leads_total = session.scalar(select(func.count()).select_from(Lead)) or 0
        leads_by_status: Dict[str, int] = {}
        for st in LeadStatus:
            leads_by_status[st.value] = 0
        for (status, cnt) in session.execute(
            select(Lead.status, func.count()).group_by(Lead.status)
        ):
            leads_by_status[_enum_val(status)] = int(cnt)
        avg_score = session.scalar(select(func.avg(Lead.lead_score))) or 0.0
        runs_today = (
            session.scalar(
                select(func.count()).select_from(PipelineRun).where(PipelineRun.started_at >= start_today)
            )
            or 0
        )
        total_runs = session.scalar(select(func.count()).select_from(PipelineRun)) or 0
        success_runs = (
            session.scalar(
                select(func.count())
                .select_from(PipelineRun)
                .where(PipelineRun.status == RunStatus.success)
            )
            or 0
        )
        run_success_rate = round((success_runs / total_runs * 100.0) if total_runs else 0.0, 1)
        recent_rows = session.scalars(
            select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(5)
        ).all()
        recent_runs = [
            {
                "id": str(r.id),
                "trigger": r.trigger,
                "seed_query": r.seed_query,
                "status": _enum_val(r.status),
                "started_at": _iso_str(r.started_at),
            }
            for r in recent_rows
        ]
        active, seed = _scout_status()
        return {
            "leads_total": int(leads_total),
            "leads_by_status": leads_by_status,
            "leads_avg_score": round(float(avg_score or 0.0), 1),
            "runs_today": int(runs_today),
            "run_success_rate": run_success_rate,
            "recent_runs": recent_runs,
            "scout_active": active,
            "scout_last_seed": seed,
        }
    finally:
        session.close()


def _iso_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%dT%H:%M:%SZ")
    return str(v)


def _scout_status() -> tuple:
    try:
        from crm import runner

        active = runner.get_active()
        if active:
            return True, active.get("seed_query")
    except Exception:
        pass
    return False, None
```

- [ ] **Step 4: Add the stats endpoint to `api/router.py`**

```python
@router.get("/stats")
def api_stats():
    return service.compute_stats()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_stats.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add crm/service.py api/router.py tests/test_stats.py
git commit -m "feat: /api/stats KPI aggregates"
```

---

### Task 8: `GET /api/scout/status` + SSE chat endpoint

**Files:**
- Modify: `api/router.py`, `crm/schemas.py`
- Test: `tests/test_scout_api.py`

**Interfaces:**
- Consumes: `service.compute_stats` (`scout_active`, `scout_last_seed`), `crm.scout.run_scout_turn`.
- Produces:
  - `GET /api/scout/status` → `{"scout_active": bool, "scout_last_seed": Optional[str], "latest_missions": List[Dict]}` (latest_missions = top 5 from `list_pipeline_runs`).
  - `POST /api/scout/threads/{thread_id}/messages` → `text/event-stream` with SSE events:
    - `event: tool` data: `{"tool_name": "...", "status": "start"|"done", "error": null|str}`
    - `event: delta` data: JSON chunk of assistant text (no-op for now — engine returns full text)
    - `event: done` data: `{"thread_id": "...", "assistant": "...", "tool_calls": int}`
    - `event: error` data: `{"detail": "..."}`

- [ ] **Step 1: Write the failing test**

```python
"""Scout status + SSE chat endpoint (engine mocked)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from api.main import app

    return TestClient(app)


def test_scout_status_shape(client):
    r = client.get("/api/scout/status")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "scout_active" in body
    assert "scout_last_seed" in body
    assert "latest_missions" in body
    assert isinstance(body["latest_missions"], list)


def test_scout_chat_sse(client, monkeypatch):
    from api import router as api_router
    import crm.scout as scout_mod

    def fake_run(thread_id, user_text, **kw):
        return {"thread_id": thread_id, "assistant": "done", "tool_calls": 0, "message_ids": ["m1"]}

    monkeypatch.setattr(scout_mod, "run_scout_turn", fake_run)
    r = client.post("/api/scout/threads/00000000-0000-0000-0000-000000000001/messages", json={"content": "hello"})
    assert r.status_code == 200, r.text
    assert "text/event-stream" in r.headers["content-type"]
    assert "event: done" in r.text
    assert "done" in r.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scout_api.py -v`
Expected: FAIL — 404 for `/api/scout/status` and the messages POST

- [ ] **Step 3: Add the schema + endpoints to `api/router.py`**

Add a request DTO (top of file, after `ScoutThreadCreate`):

```python
class ScoutMessageCreate(BaseModel):
    content: str
```

Add the endpoints:

```python
from fastapi.responses import StreamingResponse


@router.get("/scout/status")
def api_scout_status():
    stats = service.compute_stats()
    missions = service.list_pipeline_runs(limit=5)
    return {
        "scout_active": stats["scout_active"],
        "scout_last_seed": stats["scout_last_seed"],
        "latest_missions": missions,
    }


@router.post("/scout/threads/{thread_id}/messages")
def api_scout_chat(thread_id: str, body: ScoutMessageCreate):
    from crm import scout

    import asyncio

    async def gen():
        try:
            yield "event: start\ndata: {}\n\n"
            result = await asyncio.to_thread(
                scout.run_scout_turn, thread_id, body.content
            )
            import json

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
            import json

            yield f"event: error\ndata: {json.dumps({'detail': str(exc)})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


def _chunk_text(text: str, size: int) -> List[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_scout_api.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add api/router.py tests/test_scout_api.py
git commit -m "feat: scout status + SSE chat endpoint"
```

---

### Task 9: Full backend suite verification + docs

**Files:**
- Test: run the whole suite.
- Modify: `docs/ops/START_DEPARTMENT.md` (add new API endpoints to docs).

**Interfaces:**
- Consumes: everything from Tasks 1-8.

- [ ] **Step 1: Run the full backend test suite**

Run: `pytest tests/test_google_maps_tool.py tests/test_scout_chat.py tests/test_scout_service.py tests/test_pipeline_runs_list.py tests/test_api_router.py tests/test_lm_client_tools.py tests/test_scout_engine.py tests/test_stats.py tests/test_scout_api.py -v`
Expected: ALL PASS

- [ ] **Step 2: Run the pre-existing suite for regressions**

Run: `pytest tests/test_crm_api.py tests/test_tools.py tests/test_db.py -v`
Expected: PASS (or the same known local-3.9 failures that already exist — verify none are NEW)

- [ ] **Step 3: Update ops docs**

In `docs/ops/START_DEPARTMENT.md`, add to the "Open CRM" section:

```
| API | http://localhost:8000/api/docs |
```

And a new section:

```
## Scout HQ API (new)

| Endpoint | Purpose |
|----------|---------|
| GET /api/pipeline-runs | Mission board list with agent-run counts |
| GET /api/stats | Dashboard KPI aggregates |
| GET /api/scout/status | Active scout + latest missions (topbar badge) |
| GET/POST /api/scout/threads | List / create chat threads |
| GET /api/scout/threads/{id}/messages | Chat history |
| POST /api/scout/threads/{id}/messages | Send a message (SSE stream) |
```

- [ ] **Step 4: Commit**

```bash
git add docs/ops/START_DEPARTMENT.md
git commit -m "docs: Scout HQ backend API endpoints"
```

---

## Self-Review Notes

- **Spec coverage:** Data model (Task 1), service layer (Task 2), pipeline-runs list (Task 3), unified `/api` prefix (Task 4), tool-capable `lm_client` (Task 5), chat engine with hybrid tool invocation + 5-iteration cap (Task 6), `/api/stats` (Task 7), scout status + SSE (Task 8), verification + docs (Task 9). The **frontend React SPA** (spec Sections 5, 7) and **legacy remount/deletion** (Section 8, phase 5) are intentionally OUT of this plan — they are a separate plan to be written after this backend plan lands.
- **Consistency check:** `run_scout_turn` signature, `_TOOLS_SCHEMA`, service function names, and DTO names are used identically across Tasks 2-8. `api_list_messages` wraps thread_id parsing with a 422 fallback because FastAPI path params are strings.
- **Fallback path tested?** Task 6 tests the native path and the tool round-trip. The JSON-decision fallback is exercised only when native tools raise; a mocked raise → fallback test is included implicitly via `_run_fallback_tools` unit logic but not asserted — acceptable for phase 1, noted for the frontend plan's live test.
