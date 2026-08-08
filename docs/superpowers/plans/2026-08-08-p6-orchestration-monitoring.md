# P6 — Orchestration + Monitoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the four agents actually use the RAG/graph brain they already advertise (via `knowledge/retrieval.py::build_brain_context`), add concurrent async dispatch (`crm/orchestrator.py` N-worker pool + `POST /api/agents/{name}/batch`), and surface brain/monitoring telemetry on the Dashboard (BrainHealthCard). Redis cache + `brain_query_metrics` already exist from P4.

**Architecture:** Three independently testable subsystems — (1) retrieval wiring: one helper injects scoped brain results into scout/head/discovery/qualifier prompt builds, reading each agent's new `default_domain` profile field; (2) async dispatch: a `ThreadPoolExecutor` worker pool (default 3, setting `orchestrator_workers`) with per-agent runner registry, Postgres `pipeline_runs` as the queue state, and new single+batch dispatch endpoints; (3) monitoring UI: a Dashboard `BrainHealthCard` (lamps + telemetry + recent requests) backed by new `web/src/api/brain.ts` and one new backend endpoint (`GET /api/brain/worker/status`).

**Tech Stack:** Existing — FastAPI, SQLAlchemy raw SQL, alembic, redis-py, JanusGraph/gremlinpython (P4), pgvector, Ollama embeddings, React + @tanstack/react-query + vitest.

## Global Constraints

- "No paid APIs / local LLM only." All new services are local containers.
- Follow existing test conventions: flat `tests/test_*.py`, DB-gated tests use `@pytest.mark.skipif(not os.getenv("DATABASE_URL"), ...)`, API tests use `TestClient(app)` from `api.main`, function-local imports for patchability.
- Migrations: app container runs alembic only at container start; after adding migrations run `docker exec marketing_app python -m alembic upgrade head` (or restart the app) before DB-gated tests.
- Host pytest runs on Windows Python 3.9 (`C:\Users\bacca\AppData\Local\Programs\Python\Python39`); run `python -m pytest tests/... -q --no-header` on the host. Full suite: **84 passed, 6 skipped** before P6.
- JanusGraph runs under `docker compose --profile brain`. All brain/graph functions must degrade (never raise to the caller).
- The SPA agent-detail form (`AgentsDetail.tsx`) already has a `default_seed_query` input — mirror that pattern for `default_domain`.
- Windows host / PowerShell. Use `docker compose`.
- Agent run lifecycles: `AgentRunRecorder` (crm/client.py) owns pipeline+agent-run recording; orchestrator runners bind a queue-owned `pipeline_run_id` to a recorder so one `PipelineRun` records the whole task.

---

### Task A: Schema — `default_domain` + `brain_query_metrics.query`

**Files:**
- Create: `migrations/versions/20260808_0008_agent_default_domain.py`
- Create: `migrations/versions/20260808_0009_brain_query_query.py`
- Modify: `db/models.py`, `crm/schemas.py`, `crm/service.py`, `db/brain_metrics.py`, `knowledge/rag.py`
- Modify tests: `tests/test_brain_metrics.py`, `tests/test_rag.py`, `tests/test_brain_api.py`

**Interfaces:**
- Produces: `agent_profiles.default_domain` (nullable), `brain_query_metrics.query` (nullable); `record_query(..., query: Optional[str] = None)`; `AgentProfileOut/AgentProfileUpdate.default_domain`; `update_agent_profile` accepts `default_domain`; `scoped_query` records the truncated (`[:200]`) query text on both hit and miss paths.

- [ ] **Step 1: Write migration `20260808_0008` (default_domain)**

`migrations/versions/20260808_0008_agent_default_domain.py`:

```python
"""Add agent_profiles.default_domain (P6 — brain scoping)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260808_0008"
down_revision = "20260807_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_profiles", sa.Column("default_domain", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_profiles", "default_domain")
```

- [ ] **Step 2: Write migration `20260809_0009` (query column)**

`migrations/versions/20260808_0009_brain_query_query.py`:

```python
"""Add brain_query_metrics.query (P6 — show what the agent asked for)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260808_0009"
down_revision = "20260808_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("brain_query_metrics", sa.Column("query", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("brain_query_metrics", "query")
```

- [ ] **Step 3: Model + schema + service passthroughs**

In `db/models.py` `AgentProfile` (after `default_seed_query = Column(Text)` at line 129) add:

```python
    default_domain = Column(Text)
```

In `crm/schemas.py`:
- `AgentProfileOut` (line ~170) add after `default_seed_query`:
```python
    default_domain: Optional[str] = None
```
- `AgentProfileUpdate` (line ~182) add after `default_seed_query`:
```python
    default_domain: Optional[str] = None
```

In `crm/service.py::update_agent_profile` (after the `default_seed_query` block at line 503) add:

```python
        if "default_domain" in data:
            row.default_domain = ((data["default_domain"] or "").strip() or None)
```

`get_agent_profile` needs no change — `_row_to_dict(row)` already returns all columns.

- [ ] **Step 4: `db/brain_metrics.py` — query param + column**

Change `record_query` signature to add `query: Optional[str] = None`, insert the column, and add `query` to the `recent_queries` SELECT:

```python
def record_query(
    agent_name: str,
    domain: Optional[str],
    query_hash: str,
    latency_ms: int,
    cache_hit: bool,
    vector_hits: int,
    graph_hits: int,
    query: Optional[str] = None,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO brain_query_metrics
                    (id, agent_name, domain, query_hash, latency_ms, cache_hit, vector_hits, graph_hits, query, created_at)
                VALUES (:id, :agent_name, :domain, :query_hash, :latency_ms, :cache_hit, :vector_hits, :graph_hits, :query, NOW())
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "agent_name": agent_name,
                "domain": domain,
                "query_hash": query_hash,
                "latency_ms": latency_ms,
                "cache_hit": cache_hit,
                "vector_hits": vector_hits,
                "graph_hits": graph_hits,
                "query": query,
            },
        )
```

And `recent_queries` SELECT adds `query` after `query_hash`:

```python
                SELECT id, agent_name, domain, query_hash, query, latency_ms, cache_hit, vector_hits, graph_hits, created_at
```

- [ ] **Step 5: `knowledge/rag.py` — pass truncated query on both paths**

In `scoped_query`, cache-hit `record_query(...)` call (line ~74) — add the last arg:

```python
                record_query(
                    agent_name, domain, key, cached["latency_ms"], True,
                    cached.get("vector_hits", 0), cached.get("graph_hits", 0),
                    query=query[:200],
                )
```

And the cache-miss `record_query(...)` call (line ~130) — add the last arg:

```python
        record_query(
            agent_name, domain, key, payload["latency_ms"], False,
            len(vector), len(graph_leads),
            query=query[:200],
        )
```

- [ ] **Step 6: Update P4 tests (failing → passing)**

`tests/test_brain_metrics.py::test_record_and_recent_roundtrip` — pass a query and assert it round-trips:

```python
    record_query("pytest", "tn", h, 12, False, 2, 1, query="what we offer")
    ...
    assert row["query"] == "what we offer"
```

`tests/test_rag.py` — update the `patch_layers` fixture to capture the record kwargs and add truncation assertions:

```python
@pytest.fixture
def patch_layers(monkeypatch):
    from knowledge import rag

    calls = {"vector": 0, "graph": 0, "cache_set": 0, "record": 0}
    recorded: dict = {}
    monkeypatch.setattr(rag, "cache_get", lambda key: None)
    monkeypatch.setattr(
        rag, "cache_set", lambda key, payload: calls.__setitem__("cache_set", calls["cache_set"] + 1)
    )
    monkeypatch.setattr(
        rag, "search_chunks",
        lambda agent, query, scope=None, limit=5: calls.__setitem__("vector", calls["vector"] + 1) or [
            {"source_uri": "leads/1", "content": "Tunisia agency", "similarity": 0.9}
        ],
    )
    monkeypatch.setattr(
        rag, "expand_related_leads",
        lambda terms, domain, limit=5: calls.__setitem__("graph", calls["graph"] + 1) or [
            {"pg_id": "p1", "name": "Acme", "url": "https://acme.tn", "industry": "web"}
        ],
    )
    monkeypatch.setattr(
        rag, "record_query",
        lambda *a, **kw: calls.__setitem__("record", calls["record"] + 1) or recorded.update(kw),
    )
    return rag, calls, recorded
```

Update the two tests that unpack the fixture (`test_miss_runs_vector_then_graph_and_caches`, `test_graph_down_still_returns_vector`) to `rag, calls, recorded = patch_layers`. Add two new tests:

```python
def test_miss_records_truncated_query(patch_layers):
    rag, calls, recorded = patch_layers
    rag.scoped_query("discovery", "tn", "x" * 500, limit=5)
    assert recorded.get("query") == "x" * 200


def test_cache_hit_records_truncated_query(monkeypatch):
    from knowledge import rag

    recorded: dict = {}
    monkeypatch.setattr(rag, "cache_get", lambda key: {"results": [], "cache_hit": False})
    monkeypatch.setattr(rag, "record_query", lambda *a, **kw: recorded.update(kw))
    rag.scoped_query("discovery", "tn", "web agency" + "y" * 400, limit=5)
    assert recorded.get("query") == ("web agency" + "y" * 400)[:200]
```

`tests/test_brain_api.py::test_metrics_endpoint_live_db` — pass a query and assert it appears:

```python
    record_query("pytest", "tn", "live-metrics-hash", 3, True, 0, 0, query="live metrics")
    ...
    assert any(m["query_hash"] == "live-metrics-hash" and m.get("query") == "live metrics" for m in r.json()["metrics"])
```

- [ ] **Step 7: Run the updated tests (expect fail on old column/signature, then pass)**

Run: `python -m pytest tests/test_brain_metrics.py tests/test_rag.py tests/test_brain_api.py -q --no-header`
Expected: FAIL — `record_query` missing column / signature mismatch.

- [ ] **Step 8: Apply migrations**

Run: `docker exec marketing_app python -m alembic upgrade head`
Verify columns exist:
Run: `docker exec marketing_postgres psql -U admin -d marketing_db -tAc "\d brain_query_metrics"` → shows `query text`
Run: `docker exec marketing_postgres psql -U admin -d marketing_db -tAc "\d agent_profiles"` → shows `default_domain text`

- [ ] **Step 9: Run the tests again (expect pass)**

Run: `python -m pytest tests/test_brain_metrics.py tests/test_rag.py tests/test_brain_api.py -q --no-header`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add migrations/versions/20260808_0008_agent_default_domain.py migrations/versions/20260808_0009_brain_query_query.py db/models.py crm/schemas.py crm/service.py db/brain_metrics.py knowledge/rag.py tests/test_brain_metrics.py tests/test_rag.py tests/test_brain_api.py
git commit -m "feat(P6): agent default_domain + brain_query_metrics.query column"
```

---

### Task B: Retrieval wiring — `knowledge/retrieval.py` + 4 injection sites

**Files:**
- Create: `knowledge/retrieval.py`
- Modify: `crm/scout.py`, `agents/discovery_agent.py`, `agents/head_agent.py`, `agents/qualifier_agent.py`
- Test: `tests/test_retrieval.py`

**Interfaces:**
- Produces:
  - `knowledge.retrieval.default_domain(agent_name: str) -> str` — `AgentProfile.default_domain` else `"global"`; never raises.
  - `knowledge.retrieval.build_brain_context(agent_name: str, query: str, limit: int = 5) -> str` — `scoped_query(agent, default_domain(agent), query, limit)` formatted as `## Brain context\n- [chunk|lead] <content> (<source>)`; returns `""` when no results or on any failure. Never raises.
- Consumes: `knowledge.rag.scoped_query` (function-local import), `crm.service.get_agent_profile` (function-local import).

- [ ] **Step 1: Write the failing tests**

`tests/test_retrieval.py`:

```python
"""P6 — knowledge/retrieval.py default_domain + build_brain_context."""

from __future__ import annotations

from types import SimpleNamespace

import pytest


def _patch_profile(monkeypatch, profile):
    from crm import service

    monkeypatch.setattr(service, "get_agent_profile", lambda name: profile)
    from knowledge import retrieval

    monkeypatch.setattr(retrieval, "default_domain", retrieval.default_domain)


def test_default_domain_uses_profile_field(monkeypatch):
    from crm import service
    from knowledge import retrieval

    monkeypatch.setattr(service, "get_agent_profile", lambda name: {"default_domain": "tn"})
    assert retrieval.default_domain("discovery") == "tn"


def test_default_domain_falls_back_to_global(monkeypatch):
    from crm import service
    from knowledge import retrieval

    monkeypatch.setattr(service, "get_agent_profile", lambda name: None)
    assert retrieval.default_domain("discovery") == "global"


def test_default_domain_never_raises(monkeypatch):
    from crm import service
    from knowledge import retrieval

    def boom(name):
        raise RuntimeError("db down")

    monkeypatch.setattr(service, "get_agent_profile", boom)
    assert retrieval.default_domain("discovery") == "global"


def test_build_brain_context_formats_results(monkeypatch):
    from knowledge import rag, retrieval

    monkeypatch.setattr(retrieval, "default_domain", lambda name: "tn")
    payload = {
        "results": [
            {"type": "chunk", "content": "Tunisia agency", "source": "leads/1"},
            {"type": "lead", "content": "Acme", "source": "https://acme.tn"},
        ]
    }
    monkeypatch.setattr(rag, "scoped_query", lambda a, d, q, limit=5: payload)
    ctx = retrieval.build_brain_context("discovery", "web agency")
    assert "## Brain context" in ctx
    assert "[chunk] Tunisia agency (leads/1)" in ctx
    assert "[lead] Acme (https://acme.tn)" in ctx


def test_build_brain_context_empty_when_no_results(monkeypatch):
    from knowledge import rag, retrieval

    monkeypatch.setattr(retrieval, "default_domain", lambda name: "tn")
    monkeypatch.setattr(rag, "scoped_query", lambda a, d, q, limit=5: {"results": []})
    assert retrieval.build_brain_context("discovery", "x") == ""


def test_build_brain_context_never_raises(monkeypatch):
    from knowledge import rag, retrieval

    monkeypatch.setattr(retrieval, "default_domain", lambda name: "tn")

    def boom(a, d, q, limit=5):
        raise RuntimeError("graph down")

    monkeypatch.setattr(rag, "scoped_query", boom)
    assert retrieval.build_brain_context("discovery", "x") == ""
```

Note: `build_brain_context` imports `scoped_query` function-locally (`from knowledge.rag import scoped_query`), so tests patch the **source module** `knowledge.rag.scoped_query` (resolved at each call), not a `retrieval.scoped_query` attribute (which does not exist). `default_domain` likewise imports `crm.service` function-locally, so its tests patch `crm.service.get_agent_profile`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_retrieval.py -q --no-header`
Expected: FAIL (ImportError: no module `knowledge.retrieval`).

- [ ] **Step 3: Write `knowledge/retrieval.py`**

```python
"""Agent-side brain retrieval (P6) — scoped RAG context for prompt injection."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def default_domain(agent_name: str) -> str:
    """AgentProfile.default_domain, else 'global'. Never raises."""
    try:
        from crm import service as crm_service

        profile = crm_service.get_agent_profile(agent_name) or {}
        return (profile.get("default_domain") or "").strip() or "global"
    except Exception:  # noqa: BLE001
        return "global"


def build_brain_context(agent_name: str, query: str, limit: int = 5) -> str:
    """Scoped brain results formatted for prompt injection; '' when no results.

    Reuses scoped_query (cache -> pgvector -> graph -> metrics), so agent
    retrieval automatically hits the Redis cache and records telemetry.
    Never raises: any failure here returns ''.
    """
    from knowledge.rag import scoped_query

    try:
        payload = scoped_query(agent_name, default_domain(agent_name), query, limit=limit)
    except Exception:  # noqa: BLE001
        return ""
    rows = payload.get("results") or []
    if not rows:
        return ""
    lines = ["## Brain context"]
    for r in rows[:limit]:
        kind = r.get("type", "chunk")
        content = (r.get("content") or "").strip()
        source = (r.get("source") or r.get("url") or "").strip()
        if not content:
            continue
        lines.append(f"- [{kind}] {content} ({source or 'unknown'})")
    return "\n".join(lines) if len(lines) > 1 else ""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_retrieval.py -q --no-header`
Expected: PASS (6 tests).

- [ ] **Step 5: Wire Scout (`crm/scout.py`)**

Add at module top (with the other imports):

```python
from knowledge.retrieval import build_brain_context
```

In `run_scout_turn`, replace line 131 (`messages: List[Dict[str, Any]] = [{"role": "system", "content": profile["mission_prompt"]}]`) with:

```python
    sys_content = profile["mission_prompt"]
    latest_user = (history[-1].get("content") or "") if history else user_text
    try:
        ctx = build_brain_context("scout", latest_user)
        if ctx:
            sys_content = f"{sys_content}\n\n{ctx}"
    except Exception:  # noqa: BLE001
        pass
    messages: List[Dict[str, Any]] = [{"role": "system", "content": sys_content}]
```

- [ ] **Step 6: Wire Discovery (`agents/discovery_agent.py`)**

Add at module top:

```python
from knowledge.retrieval import build_brain_context
```

In `_llm_report` (line ~296), right after the `mission` truncation block, add:

```python
        ctx = build_brain_context("discovery", seed_query)
        if ctx:
            mission = f"{mission}\n\n{ctx}"
```

- [ ] **Step 7: Wire Head (`agents/head_agent.py`)**

Add at module top:

```python
from knowledge.retrieval import build_brain_context
```

In `_plan_core` (line ~143), after `user_body` is built, append ctx:

```python
        ctx = build_brain_context("head", goal)
        if ctx:
            user_body = f"{ctx}\n\n{user_body}"
```

In `_llm_report` (line ~203), after `user_body` is built, append ctx:

```python
        ctx = build_brain_context("head", seed)
        if ctx:
            user_body = f"{ctx}\n\n{user_body}"
```

- [ ] **Step 8: Wire Qualifier (`agents/qualifier_agent.py`)**

Add at module top:

```python
from knowledge.retrieval import build_brain_context
```

In `qualify` (line ~41), after `prompt` is built, append ctx:

```python
        ctx = build_brain_context("qualifier", f"{name} {url}".strip())
        if ctx:
            prompt = f"{ctx}\n\n{prompt}"
```

- [ ] **Step 9: Run the backend suite to confirm no regressions**

Run: `python -m pytest tests/ -q --no-header`
Expected: all existing tests pass (including `tests/test_scout_engine.py`, head/discovery/qualifier tests — `build_brain_context` returns `""` in non-DB test envs so prompts are unchanged) plus the 6 new `test_retrieval.py` tests.

Note: in DB-gated live runs the agents will now emit a real `scoped_query` per turn — that is the intended behavior.

- [ ] **Step 10: Commit**

```bash
git add knowledge/retrieval.py crm/scout.py agents/discovery_agent.py agents/head_agent.py agents/qualifier_agent.py tests/test_retrieval.py
git commit -m "feat(P6): wire scoped brain retrieval into scout/head/discovery/qualifier"
```

---

### Task C: Async dispatch — `crm/orchestrator.py` + endpoints

**Files:**
- Create: `crm/orchestrator.py`
- Modify: `config/settings.py`, `api/router.py`, `api/brain_router.py`, `api/main.py`
- Modify test: `tests/test_dispatch_meta.py`
- Create: `tests/test_orchestrator.py`, `tests/test_batch_dispatch.py`

**Interfaces:**
- Produces:
  - `crm.orchestrator.enqueue_run(agent_name, seed_query, mission=None) -> Dict` (creates `PipelineRun` trigger `agent:{name}`, meta `{mission, from_agent, mode:"dispatch"}`, submits runner to pool, returns run; unknown agent → `ValueError`).
  - `crm.orchestrator.pool()` → `WorkerPool` singleton; `active_count()`, `queued_count()`, `pool().max_workers`.
  - `crm.orchestrator.reclaim_stale_runs() -> int` (marks running `agent:%` runs failed; called at app startup).
  - `POST /api/agents/{name}/batch` body `{"missions": [{"seed_query","mission"}]}` → `{"runs": [PipelineRunOut...]}` (201).
  - `POST /api/agents/{name}/dispatch` rewritten to `enqueue_run` for all agents (same response shape).
  - `GET /api/brain/worker/status` → `{"active", "max_workers", "queued"}`.
- Consumes: `crm.service.start_pipeline_run`, `crm.service.complete_pipeline_run`, `crm.service.list_pipeline_runs`, `crm.service.get_lead`, `crm.service.list_leads`; `workflows.discovery_only.run_discovery_only`; `agents.head_agent.HeadAgent`; `agents.qualifier_agent.QualifierAgent`; `crm.client.AgentRunRecorder`.

- [ ] **Step 1: Add setting**

In `config/settings.py` add (after `brain_cache_ttl_s`):

```python
    orchestrator_workers: int = 3
```

- [ ] **Step 2: Write the failing orchestrator tests**

`tests/test_orchestrator.py`:

```python
"""P6 — crm/orchestrator.py worker pool + runner registry (hermetic)."""

from __future__ import annotations

import pytest


class _FakePool:
    def __init__(self, max_workers=3):
        self.max_workers = max_workers
        self.submitted = []

    def submit(self, fn, run_id, seed, mission=None):
        self.submitted.append((fn, run_id, seed, mission))


def test_runner_registry_maps_task_agents():
    from crm import orchestrator

    assert set(orchestrator._RUNNERS) == {"discovery", "head", "qualifier"}


def test_enqueue_unknown_agent_raises(monkeypatch):
    from crm import orchestrator

    monkeypatch.setattr(orchestrator, "pool", lambda: _FakePool())
    monkeypatch.setattr(orchestrator.service, "start_pipeline_run",
                        lambda trigger, seed_query, meta=None: {"id": "r1"})
    with pytest.raises(ValueError):
        orchestrator.enqueue_run("nope", "x")


def test_enqueue_submits_runner_with_run(monkeypatch):
    from crm import orchestrator

    fake = _FakePool()
    monkeypatch.setattr(orchestrator, "pool", lambda: fake)
    monkeypatch.setattr(orchestrator.service, "start_pipeline_run",
                        lambda trigger, seed_query, meta=None: {"id": "r-1", "seed_query": seed_query})
    run = orchestrator.enqueue_run("head", "seed me", mission="m1")
    assert run["id"] == "r-1"
    assert fake.submitted[0][1] == "r-1"
    assert fake.submitted[0][2] == "seed me"
    assert fake.submitted[0][3] == "m1"


def test_run_head_marks_success(monkeypatch):
    from agents import head_agent as head_mod
    from crm import orchestrator

    completed = {}

    class _Recorder:
        pipeline_run_id = "r-9"

        def complete_pipeline(self, status="success", meta=None):
            completed["status"] = status

    class _Head:
        def plan_discovery(self, goal, recorder=None):
            return {"seed_query": "s", "tools": ["llm_chat"], "rationale": "r"}

    monkeypatch.setattr(orchestrator, "AgentRunRecorder", lambda *a, **kw: _Recorder())
    monkeypatch.setattr(head_mod, "HeadAgent", lambda: _Head())
    orchestrator._run_head("r-9", "s", None)
    assert completed["status"] == "success"


def test_run_head_marks_failed_on_error(monkeypatch):
    from agents import head_agent as head_mod
    from crm import orchestrator

    class _Recorder:
        pipeline_run_id = "r-9"

        def complete_pipeline(self, status="success", meta=None):
            pass

    class _Head:
        def plan_discovery(self, goal, recorder=None):
            raise RuntimeError("llm down")

    monkeypatch.setattr(orchestrator, "AgentRunRecorder", lambda *a, **kw: _Recorder())
    monkeypatch.setattr(head_mod, "HeadAgent", lambda: _Head())
    monkeypatch.setattr(orchestrator.service, "complete_pipeline_run",
                        lambda run_id, status, meta=None: None)
    orchestrator._run_head("r-9", "s", None)
    # no raise expected
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_orchestrator.py -q --no-header`
Expected: FAIL (ImportError: no module `crm.orchestrator`).

- [ ] **Step 4: Write `crm/orchestrator.py`**

```python
"""P6 — async agent dispatch: N-worker pool with Postgres-backed queue state.

Each dispatch creates a PipelineRun (status `running`) as the queue record; a
worker thread runs the agent's runner, then completes the run to success/failed.
The pool is process-local: on app restart `reclaim_stale_runs` marks orphaned
running runs failed.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, Optional

from config.settings import get_settings
from crm import service
from crm.client import AgentRunRecorder

_pool: Optional["WorkerPool"] = None
_lock = threading.Lock()


class WorkerPool:
    def __init__(self, max_workers: int) -> None:
        self.max_workers = max_workers
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="agent-worker")
        self._running = 0
        self._running_lock = threading.Lock()

    def submit(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        with self._running_lock:
            self._running += 1

        def _wrap(*a: Any, **kw: Any) -> Any:
            try:
                return fn(*a, **kw)
            finally:
                with self._running_lock:
                    self._running -= 1

        return self._executor.submit(_wrap, *args, **kwargs)

    def active_count(self) -> int:
        with self._running_lock:
            return self._running

    def queued_count(self) -> int:
        q = getattr(self._executor, "_work_queue", None)
        return q.qsize() if q is not None else 0


def pool() -> WorkerPool:
    global _pool
    with _lock:
        if _pool is None:
            _pool = WorkerPool(max_workers=get_settings().orchestrator_workers)
    return _pool


def active_count() -> int:
    try:
        return pool().active_count()
    except Exception:  # noqa: BLE001
        return 0


def queued_count() -> int:
    try:
        return pool().queued_count()
    except Exception:  # noqa: BLE001
        return 0


def _find_lead(seed_query: str) -> Optional[Dict[str, Any]]:
    query = (seed_query or "").strip()
    if not query:
        return None
    try:
        lead = service.get_lead(query)
        if lead:
            return lead
    except Exception:  # noqa: BLE001
        pass
    url = query.rstrip("/")
    for lead in service.list_leads(limit=10000):
        if (lead.get("url") or "").strip().rstrip("/") == url:
            return lead
    return None


def _run_discovery(run_id: str, seed_query: str, mission: Optional[str]) -> None:
    from workflows.discovery_only import run_discovery_only

    recorder = AgentRunRecorder(
        trigger="agent:discovery",
        seed_query=seed_query,
        meta={"from_agent": "discovery", "mode": "dispatch", "mission": mission or ""},
    )
    recorder.pipeline_run_id = run_id
    try:
        run_discovery_only(seed_query, recorder=recorder, trigger="agent:discovery")
    except Exception as exc:  # noqa: BLE001
        try:
            service.complete_pipeline_run(run_id, "failed", {"error": str(exc)})
        except Exception:  # noqa: BLE001
            pass


def _run_head(run_id: str, seed_query: str, mission: Optional[str]) -> None:
    from agents.head_agent import HeadAgent

    recorder = AgentRunRecorder(
        trigger="agent:head",
        seed_query=seed_query,
        meta={"from_agent": "head", "mode": "dispatch", "mission": mission or ""},
    )
    recorder.pipeline_run_id = run_id
    try:
        plan = HeadAgent().plan_discovery(seed_query or "Improve the pipeline", recorder=recorder)
        recorder.complete_pipeline(
            "success",
            meta={"mode": "dispatch", "seed_query": plan.get("seed_query"), "tools": plan.get("tools")},
        )
    except Exception as exc:  # noqa: BLE001
        try:
            service.complete_pipeline_run(run_id, "failed", {"error": str(exc)})
        except Exception:  # noqa: BLE001
            pass


def _run_qualifier(run_id: str, seed_query: str, mission: Optional[str]) -> None:
    from agents.qualifier_agent import QualifierAgent

    recorder = AgentRunRecorder(
        trigger="agent:qualifier",
        seed_query=seed_query,
        meta={"from_agent": "qualifier", "mode": "dispatch", "mission": mission or ""},
    )
    recorder.pipeline_run_id = run_id
    try:
        lead = _find_lead(seed_query)
        if lead is None:
            raise ValueError(f"qualifier dispatch needs a lead id or URL; got: {seed_query[:120]!r}")
        result = QualifierAgent().qualify(lead)
        recorder.complete_pipeline(
            "success",
            meta={
                "mode": "dispatch",
                "lead_id": str(lead.get("id")),
                "score": result.get("score"),
                "fit": result.get("fit"),
            },
        )
    except Exception as exc:  # noqa: BLE001
        try:
            service.complete_pipeline_run(run_id, "failed", {"error": str(exc)})
        except Exception:  # noqa: BLE001
            pass


_RUNNERS: Dict[str, Callable[[str, str, Optional[str]], None]] = {
    "discovery": _run_discovery,
    "head": _run_head,
    "qualifier": _run_qualifier,
}


def enqueue_run(agent_name: str, seed_query: str, mission: Optional[str] = None) -> Dict[str, Any]:
    """Enqueue a task for agent_name; returns the created PipelineRun dict."""
    if agent_name not in _RUNNERS:
        raise ValueError(f"No runner for agent: {agent_name}")
    run = service.start_pipeline_run(
        trigger=f"agent:{agent_name}",
        seed_query=seed_query,
        meta={"mission": mission or "", "from_agent": agent_name, "mode": "dispatch"},
    )
    run_id = str(run["id"])
    pool().submit(_RUNNERS[agent_name], run_id, seed_query, mission)
    return run


def reclaim_stale_runs() -> int:
    """Mark orchestrator-owned running runs failed (app restarted mid-run)."""
    runs = service.list_pipeline_runs(limit=500)
    n = 0
    for r in runs:
        if (
            r.get("status") == "running"
            and not r.get("finished_at")
            and (r.get("trigger") or "").startswith("agent:")
        ):
            service.complete_pipeline_run(str(r["id"]), "failed", {"error": "app restarted mid-run"})
            n += 1
    return n
```

- [ ] **Step 5: Run orchestrator tests (expect pass)**

Run: `python -m pytest tests/test_orchestrator.py -q --no-header`
Expected: PASS (5 tests).

- [ ] **Step 6: Rewrite `/api/agents/{agent_name}/dispatch` in `api/router.py`**

Replace the whole `api_dispatch_agent` function (lines 109-143) with:

```python
@router.post("/agents/{agent_name}/dispatch", response_model=schemas.PipelineRunOut, status_code=201)
def api_dispatch_agent(agent_name: str, body: AgentDispatchRequest):
    """Enqueue an agent task via the async worker pool (returns the run immediately)."""
    from crm import orchestrator

    seed = (body.seed_query or "").strip()
    if agent_name == "discovery" and len(seed) < 2:
        profile = service.get_agent_profile("discovery") or {}
        seed = (profile.get("default_seed_query") or "").strip()
    if agent_name == "discovery" and len(seed) < 2:
        raise HTTPException(
            status_code=400,
            detail="seed_query required (or set default_seed_query on the Discovery profile)",
        )
    try:
        run = orchestrator.enqueue_run(agent_name, seed, body.mission)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return run
```

Note: `orchestrator.enqueue_run` is looked up via `from crm import orchestrator` (module attribute at call time), so tests patch `crm.orchestrator.pool` / `crm.orchestrator.enqueue_run`.

- [ ] **Step 7: Add the batch endpoint in `api/router.py`**

Add after `AgentDispatchRequest`:

```python
class BatchMission(BaseModel):
    seed_query: Optional[str] = None
    mission: Optional[str] = None


class BatchDispatchRequest(BaseModel):
    missions: List[BatchMission] = Field(default_factory=list)
```

Add after `api_dispatch_agent`:

```python
@router.post("/agents/{agent_name}/batch", status_code=201)
def api_batch_dispatch(agent_name: str, body: BatchDispatchRequest):
    """Enqueue several tasks for one agent; returns all created runs."""
    from crm import orchestrator

    try:
        runs = [
            orchestrator.enqueue_run(agent_name, m.seed_query or "", m.mission)
            for m in body.missions
        ]
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"runs": runs}
```

Check `Field` is imported at the top of `api/router.py` (add `from pydantic import BaseModel, Field` if needed).

- [ ] **Step 8: Add `GET /api/brain/worker/status` in `api/brain_router.py`**

Append:

```python
@router.get("/worker/status")
def worker_status():
    from crm import orchestrator

    return {
        "active": orchestrator.active_count(),
        "max_workers": orchestrator.pool().max_workers,
        "queued": orchestrator.queued_count(),
    }
```

- [ ] **Step 9: Register the startup reclaim in `api/main.py`**

Append near the top-level routes:

```python
@app.on_event("startup")
def _reclaim_stale_dispatch_runs() -> None:
    try:
        from crm import orchestrator

        orchestrator.reclaim_stale_runs()
    except Exception:  # noqa: BLE001
        pass
```

(Existing tests build `TestClient(app)` without a context manager, so the startup hook never fires in tests.)

- [ ] **Step 10: Update `tests/test_dispatch_meta.py` to stay hermetic**

The head dispatch now spawns a background runner (LLM). Patch the pool so the submit is a no-op. Update `tests/test_dispatch_meta.py`:

```python
"""Dispatch (mission metadata) integration tests.

DB-gated like the rest of tests/test_crm_api.py. We assert on the persisted
PipelineRun.meta via SQL and clean up created rows. The orchestrator pool is
stubbed so no background LLM runner is spawned.
"""
from __future__ import annotations

import os
import uuid
from typing import Optional
from unittest import mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text


def _database_url() -> Optional[str]:
    return os.getenv("DATABASE_URL")


@pytest.fixture
def client():
    from api.main import app

    return TestClient(app)


class _FakePool:
    max_workers = 3

    def submit(self, *a, **kw):
        return None

    def active_count(self):
        return 0

    def queued_count(self):
        return 0


def test_dispatch_records_mission_metadata(client):
    if not _database_url():
        pytest.skip("DATABASE_URL not set")
    from crm import orchestrator

    mission = f"pytest-mission-{uuid.uuid4().hex[:8]}"
    with mock.patch.object(orchestrator, "pool", return_value=_FakePool()):
        r = client.post(
            "/api/agents/head/dispatch",
            json={"seed_query": None, "mission": mission},
        )
    assert r.status_code == 201, r.text
    run_id = r.json()["id"]
    eng = create_engine(_database_url())
    try:
        with eng.connect() as conn:
            row = conn.execute(
                text("SELECT meta FROM pipeline_runs WHERE id = :id"),
                {"id": run_id},
            ).fetchone()
        assert row is not None, "pipeline_runs row not found"
        meta = row[0] or {}
        assert meta.get("mission") == mission, meta
        assert meta.get("from_agent") == "head", meta
        assert meta.get("mode") == "dispatch", meta
    finally:
        with eng.begin() as conn:
            conn.execute(text("DELETE FROM pipeline_runs WHERE id = :id"), {"id": run_id})
        eng.dispose()


def test_dispatch_unknown_agent_returns_404(client):
    if not _database_url():
        pytest.skip("DATABASE_URL not set")
    r = client.post(
        "/api/agents/definitely-not-an-agent/dispatch",
        json={"seed_query": "x", "mission": "y"},
    )
    assert r.status_code == 404, r.text
```

- [ ] **Step 11: Write the failing batch test**

`tests/test_batch_dispatch.py`:

```python
"""P6 — POST /api/agents/{name}/batch (DB-gated, pool submit stubbed)."""

from __future__ import annotations

import os
from typing import Optional
from unittest import mock

import pytest
from fastapi.testclient import TestClient


def _database_url() -> Optional[str]:
    return os.getenv("DATABASE_URL")


@pytest.fixture
def client():
    from api.main import app

    return TestClient(app)


def _run_dict(run_id: str, seed: str) -> dict:
    return {
        "id": run_id,
        "trigger": "agent:head",
        "seed_query": seed,
        "status": "running",
        "started_at": None,
        "finished_at": None,
        "meta": {"mode": "dispatch"},
    }


def test_batch_dispatch_shape_with_mocked_enqueue(client):
    """Hermetic (no DB): route returns {runs: [...]} in order, 201."""
    from crm import orchestrator

    fake_runs = [_run_dict("r1", "s1"), _run_dict("r2", "s2")]
    with mock.patch.object(orchestrator, "enqueue_run", side_effect=fake_runs):
        r = client.post(
            "/api/agents/head/batch",
            json={"missions": [{"seed_query": "s1"}, {"seed_query": "s2"}]},
        )
    assert r.status_code == 201, r.text
    assert [x["id"] for x in r.json()["runs"]] == ["r1", "r2"]


def test_batch_dispatch_unknown_agent_404(client):
    from crm import orchestrator

    with mock.patch.object(orchestrator, "enqueue_run", side_effect=ValueError("No runner")):
        r = client.post(
            "/api/agents/nope/batch",
            json={"missions": [{"seed_query": "s1"}]},
        )
    assert r.status_code == 404, r.text


class _FakePool:
    max_workers = 3

    def submit(self, fn, run_id, seed, mission=None):
        pass

    def active_count(self):
        return 0

    def queued_count(self):
        return 0


@pytest.mark.skipif(not _database_url(), reason="DATABASE_URL not set")
def test_batch_dispatch_enqueues_runs(client):
    from sqlalchemy import create_engine, text

    from crm import orchestrator

    fake = _FakePool()
    with mock.patch.object(orchestrator, "pool", return_value=fake):
        r = client.post(
            "/api/agents/head/batch",
            json={
                "missions": [
                    {"seed_query": "s1", "mission": "m1"},
                    {"seed_query": "s2", "mission": "m2"},
                ]
            },
        )
    assert r.status_code == 201, r.text
    runs = r.json()["runs"]
    assert len(runs) == 2
    run_ids = [x["id"] for x in runs]

    eng = create_engine(_database_url())
    try:
        with eng.connect() as conn:
            rows = conn.execute(
                text("SELECT trigger, seed_query, meta FROM pipeline_runs WHERE id = ANY(:ids)"),
                {"ids": run_ids},
            ).fetchall()
        assert len(rows) == 2
        for trigger, seed, meta in rows:
            assert trigger == "agent:head"
            assert meta["from_agent"] == "head"
            assert meta["mode"] == "dispatch"
    finally:
        with eng.begin() as conn:
            conn.execute(
                text("DELETE FROM pipeline_runs WHERE id = ANY(:ids)"), {"ids": run_ids}
            )
        eng.dispose()
```

- [ ] **Step 12: Run the failing tests**

Run: `python -m pytest tests/test_dispatch_meta.py tests/test_batch_dispatch.py -q --no-header`
Expected: the hermetic `test_batch_dispatch_shape_with_mocked_enqueue` and `test_batch_dispatch_unknown_agent_404` FAIL (404 — routes not registered). The DB-gated `test_batch_dispatch_enqueues_runs` runs only when `DATABASE_URL` is set (set it from the app env: `DATABASE_URL=$(docker exec marketing_app printenv DATABASE_URL)`), otherwise it skips and is covered by the Task E live check.

- [ ] **Step 13: Apply no migrations here (none added in this task) and run the backend suite**

Run: `python -m pytest tests/ -q --no-header`
Expected: all tests pass — new orchestrator/batch tests plus the updated dispatch-meta test, no regressions (includes `test_api_router.py::test_openapi_unique_operation_ids` — new operation ids are unique).

- [ ] **Step 14: Commit**

```bash
git add config/settings.py crm/orchestrator.py api/router.py api/brain_router.py api/main.py tests/test_orchestrator.py tests/test_batch_dispatch.py tests/test_dispatch_meta.py
git commit -m "feat(P6): async dispatch worker pool + batch endpoint + worker status"
```

---

### Task D: Monitoring UI — `BrainHealthCard` on the Dashboard

**Files:**
- Create: `web/src/api/brain.ts`
- Modify: `web/src/api/types.ts`, `web/src/pages/Dashboard.tsx`
- Create: `web/src/components/BrainHealthCard.tsx`
- Create: `web/src/components/BrainHealthCard.test.tsx`
- Modify: `web/src/pages/Dashboard.test.tsx`

**Interfaces:**
- `fetchBrainStatus()` → `GET /api/brain/graph/status` (`{available, vertices, edges}`)
- `fetchBrainMetrics(limit)` → `GET /api/brain/metrics?limit=N` (`{metrics: BrainMetric[]}`)
- `fetchWorkerStatus()` → `GET /api/brain/worker/status` (`{active, max_workers, queued}`)
- `BrainHealthCard` renders lamps + telemetry strip + recent requests table; auto-refresh 8s; empty state "No brain activity yet."

- [ ] **Step 1: Add frontend types**

In `web/src/api/types.ts` append:

```ts
export interface BrainMetric {
  id: string;
  agent_name: string;
  domain: string | null;
  query: string | null;
  query_hash: string;
  latency_ms: number | null;
  cache_hit: boolean;
  vector_hits: number;
  graph_hits: number;
  created_at: string | null;
}

export interface BrainStatus {
  available: boolean;
  vertices: number;
  edges: number;
}

export interface WorkerStatus {
  active: number;
  max_workers: number;
  queued: number;
}
```

- [ ] **Step 2: Create `web/src/api/brain.ts`**

```ts
import { apiGet } from "./client";
import type { BrainMetric, BrainStatus, WorkerStatus } from "./types";

export function fetchBrainStatus(): Promise<BrainStatus> {
  return apiGet<BrainStatus>("/api/brain/graph/status");
}

export function fetchBrainMetrics(limit = 10): Promise<{ metrics: BrainMetric[] }> {
  return apiGet<{ metrics: BrainMetric[] }>(`/api/brain/metrics?limit=${limit}`);
}

export function fetchWorkerStatus(): Promise<WorkerStatus> {
  return apiGet<WorkerStatus>("/api/brain/worker/status");
}
```

- [ ] **Step 3: Create `web/src/components/BrainHealthCard.tsx`**

```tsx
import { useQuery } from "@tanstack/react-query";
import { fetchBrainMetrics, fetchBrainStatus, fetchWorkerStatus } from "../api/brain";
import type { BrainMetric } from "../api/types";
import { Lamp } from "../pages/Tools";

function hitLabel(m: BrainMetric): string {
  if (m.graph_hits > 0) return `graph×${m.graph_hits}`;
  if (m.vector_hits > 0) return `vector×${m.vector_hits}`;
  if (m.cache_hit) return "cache";
  return "—";
}

function tookClass(m: BrainMetric): string {
  if (m.latency_ms == null) return "";
  return m.latency_ms < 200 ? "text-green" : "text-amber";
}

export default function BrainHealthCard() {
  const brain = useQuery({
    queryKey: ["brain-status"],
    queryFn: fetchBrainStatus,
    refetchInterval: 8000,
    retry: false,
  });
  const metrics = useQuery({
    queryKey: ["brain-metrics"],
    queryFn: () => fetchBrainMetrics(10),
    refetchInterval: 8000,
    retry: false,
  });
  const worker = useQuery({
    queryKey: ["worker-status"],
    queryFn: fetchWorkerStatus,
    refetchInterval: 8000,
    retry: false,
  });

  const rows = metrics.data?.metrics ?? [];
  const total = rows.length;
  const cacheHits = rows.filter((r) => r.cache_hit).length;
  const cachePct = total ? Math.round((cacheHits / total) * 100) : null;
  const avgLatency = total
    ? Math.round(rows.reduce((a, r) => a + (r.latency_ms ?? 0), 0) / total)
    : null;

  return (
    <div className="panel">
      <h2>Brain health</h2>
      <p className="lamp-row">
        <span>
          <Lamp status={brain.data?.available ? "ok" : "fail"} detail="graph" /> Graph
        </span>
        <span>
          <Lamp status={metrics.isError ? "fail" : "ok"} detail="rag" /> RAG
        </span>
        <span>
          <Lamp status={metrics.isError ? "fail" : "ok"} detail="cache" /> Cache
        </span>
      </p>
      <p className="muted">
        Cache hit: {cachePct == null ? "—" : `${cachePct}%`} · Avg latency:{" "}
        {avgLatency == null ? "—" : `${avgLatency}ms`} · Workers:{" "}
        {worker.data ? `${worker.data.active}/${worker.data.max_workers}` : "—"} · Queued:{" "}
        {worker.data?.queued ?? "—"}
      </p>
      {!rows.length ? (
        <p className="muted">No brain activity yet.</p>
      ) : (
        <table className="data">
          <thead>
            <tr>
              <th>Agent</th>
              <th>Asked for</th>
              <th>Hit</th>
              <th>Started</th>
              <th>Took</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((m) => (
              <tr key={m.id}>
                <td>{m.agent_name}</td>
                <td className="muted">{m.query ?? "—"}</td>
                <td>{hitLabel(m)}</td>
                <td className="muted">
                  {m.created_at ? new Date(m.created_at).toLocaleString() : "—"}
                </td>
                <td className={tookClass(m)}>{m.latency_ms == null ? "—" : `${m.latency_ms}ms`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
```

Note: the RAG and Cache lamps both derive from `metrics` (cheapest honest signal; the design's "simplest" option). The `Lamp` component is imported from `web/src/pages/Tools.tsx` (already exported). `text-green`/`text-amber` CSS classes may not exist — add them to `web/src/styles/components.css` (or reuse an existing class; check `styles` first and add if missing):

```css
.text-green { color: var(--success); }
.text-amber { color: var(--warning); }
```

- [ ] **Step 4: Mount on the Dashboard**

In `web/src/pages/Dashboard.tsx`, import and render below the `.kpi-grid` (before the "Active Scout" panel):

```tsx
import BrainHealthCard from "../components/BrainHealthCard";
...
      </div>

      <BrainHealthCard />
```

- [ ] **Step 5: Create `web/src/components/BrainHealthCard.test.tsx`**

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import BrainHealthCard from "./BrainHealthCard";
import * as brainApi from "../api/brain";

function renderCard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <BrainHealthCard />
    </QueryClientProvider>,
  );
}

describe("BrainHealthCard", () => {
  it("renders lamps, telemetry and recent requests", async () => {
    vi.spyOn(brainApi, "fetchBrainStatus").mockResolvedValue({
      available: true,
      vertices: 128,
      edges: 198,
    });
    vi.spyOn(brainApi, "fetchBrainMetrics").mockResolvedValue({
      metrics: [
        {
          id: "m1",
          agent_name: "discovery",
          domain: "tn",
          query: "digital agencies",
          query_hash: "h1",
          latency_ms: 120,
          cache_hit: false,
          vector_hits: 1,
          graph_hits: 2,
          created_at: "2026-08-08T00:00:00",
        },
        {
          id: "m2",
          agent_name: "head",
          domain: "global",
          query: "top prospects",
          query_hash: "h2",
          latency_ms: 3,
          cache_hit: true,
          vector_hits: 0,
          graph_hits: 0,
          created_at: "2026-08-08T00:01:00",
        },
      ],
    });
    vi.spyOn(brainApi, "fetchWorkerStatus").mockResolvedValue({
      active: 1,
      max_workers: 3,
      queued: 2,
    });

    renderCard();

    expect(await screen.findByText("Brain health")).toBeInTheDocument();
    expect(await screen.findByText("digital agencies")).toBeInTheDocument();
    expect(screen.getByText("graph×2")).toBeInTheDocument();
    expect(screen.getByText("cache")).toBeInTheDocument();
    expect(screen.getByText("1/3")).toBeInTheDocument();
    expect(screen.getByText("Queued:")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("shows the empty state", async () => {
    vi.spyOn(brainApi, "fetchBrainStatus").mockResolvedValue({
      available: false,
      vertices: 0,
      edges: 0,
    });
    vi.spyOn(brainApi, "fetchBrainMetrics").mockResolvedValue({ metrics: [] });
    vi.spyOn(brainApi, "fetchWorkerStatus").mockResolvedValue({
      active: 0,
      max_workers: 3,
      queued: 0,
    });

    renderCard();

    expect(await screen.findByText("No brain activity yet.")).toBeInTheDocument();
  });
});
```

- [ ] **Step 6: Update `web/src/pages/Dashboard.test.tsx`**

Add a `vi.mock` for the brain api so the new card's queries resolve without network:

```tsx
import * as brainApi from "../api/brain";
...
vi.mock("../api/brain", () => ({
  fetchBrainStatus: vi.fn(),
  fetchBrainMetrics: vi.fn(),
  fetchWorkerStatus: vi.fn(),
}));
```

In the existing test, stub the brain api in the render before assertions:

```tsx
    vi.spyOn(brainApi, "fetchBrainStatus").mockResolvedValue({ available: false, vertices: 0, edges: 0 });
    vi.spyOn(brainApi, "fetchBrainMetrics").mockResolvedValue({ metrics: [] });
    vi.spyOn(brainApi, "fetchWorkerStatus").mockResolvedValue({ active: 0, max_workers: 3, queued: 0 });
```

- [ ] **Step 7: Run the frontend tests**

Run: `cd web && npm test -- --run` (or `npx vitest run`)
Expected: `BrainHealthCard.test.tsx` (2 tests) and `Dashboard.test.tsx` (1 test) pass; no regressions.

- [ ] **Step 8: Run the frontend build/typecheck**

Run: `cd web && npm run build`
Expected: TypeScript compiles cleanly.

- [ ] **Step 9: Commit**

```bash
git add web/src/api/brain.ts web/src/api/types.ts web/src/pages/Dashboard.tsx web/src/components/BrainHealthCard.tsx web/src/components/BrainHealthCard.test.tsx web/src/pages/Dashboard.test.tsx web/src/styles/components.css
git commit -m "feat(P6): Dashboard brain health card (lamps + telemetry + recent requests)"
```

---

### Task E: Live verification + docs

**Files:**
- Modify: `docs/superpowers/specs/2026-08-08-p6-orchestration-monitoring-design.md`

- [ ] **Step 1: Ensure infra is up**

Run: `docker compose --profile brain up -d janusgraph` and `docker compose up -d redis`
Also confirm the app container has the newest code (bind mount) and migrations applied:
Run: `docker exec marketing_app python -m alembic upgrade head`

- [ ] **Step 2: Apply migrations + restart app**

Run: `docker compose up -d --no-deps app`
Expected: app healthy (`Invoke-WebRequest -UseBasicParsing http://localhost:3000/api/agents/tools -TimeoutSec 10` → 200).

- [ ] **Step 3: Verify worker status endpoint**

Run: `Invoke-WebRequest -UseBasicParsing 'http://localhost:3000/api/brain/worker/status' -TimeoutSec 10`
Expected: 200, body `{"active":0,"max_workers":3,"queued":0}`.

- [ ] **Step 4: Verify single dispatch through the pool (head, hermetic — no LLM needed for the response)**

Run:
`Invoke-WebRequest -UseBasicParsing -Method POST -ContentType 'application/json' -Body '{"seed_query":"top agencies"}' 'http://localhost:3000/api/agents/head/dispatch' -TimeoutSec 10`
Expected: 201, JSON with `id`, `trigger:"agent:head"`, `status:"running"`, meta `{mode:"dispatch"}`. The background runner may later mark it `success`/`failed` depending on LLM reachability — check via `GET /api/pipeline-runs?limit=5`.

- [ ] **Step 5: Verify batch dispatch**

Run:
`Invoke-WebRequest -UseBasicParsing -Method POST -ContentType 'application/json' -Body '{"missions":[{"seed_query":"agencies tunisia"},{"seed_query":"web dev shop"}]}' 'http://localhost:3000/api/agents/head/batch' -TimeoutSec 10`
Expected: 201, `{"runs":[ {...}, {...} ]}` — two `PipelineRunOut` with distinct ids.

- [ ] **Step 6: Verify retrieval wiring records query text**

Run the seeded scoped query through an agent-adjacent path, or directly:
`Invoke-WebRequest -UseBasicParsing -Method POST -ContentType 'application/json' -Body '{"agent_name":"discovery","domain":"global","query":"digital marketing agencies"}' 'http://localhost:3000/api/brain/scoped_query' -TimeoutSec 60`
Then: `Invoke-WebRequest -UseBasicParsing 'http://localhost:3000/api/brain/metrics?limit=5' -TimeoutSec 10`
Expected: metric rows now include a non-null `query` equal to the asked query (truncated to 200 chars).

- [ ] **Step 7: Verify Dashboard**

Open `http://localhost:3000/` → the Brain health panel shows: Graph/RAG/Cache lamps, cache-hit %, avg latency, workers `active/max`, queued, and a recent-requests table with `Agent | Asked for | Hit | Started | Took` columns. Took colors: green <200ms, amber ≥200ms.

- [ ] **Step 8: Verify reclaim-on-restart behavior (optional, dev-only)**

Enqueue a dispatch, immediately `docker compose restart app`, then check the run:
Expected: the run is `failed` with meta `{error: "app restarted mid-run"}` (from the startup reclaim).

- [ ] **Step 9: Run the full backend + frontend suites**

Run: `python -m pytest tests/ -q --no-header` → all pass.
Run: `cd web && npm test -- --run` → all pass.
Run: `cd web && npm run build` → compiles.

- [ ] **Step 10: Update the design spec**

In `docs/superpowers/specs/2026-08-08-p6-orchestration-monitoring-design.md`, change the header status line to:

```
> **Date:** 2026-08-08  **Status:** Implemented (committed) — P6 done. **Branch:** `feat/scout-hq-backend`.
```

- [ ] **Step 11: Commit**

```bash
git add docs/superpowers/specs/2026-08-08-p6-orchestration-monitoring-design.md
git commit -m "docs(P6): mark orchestration + monitoring done, live-verified"
```

---

## Self-Review Notes

- **Spec coverage:** Spec §2 (retrieval wiring) → Task A (`default_domain` + `query` column) + Task B (`knowledge/retrieval.py` + 4 injection sites). Spec §3 (async dispatch) → Task C (pool, runners, reclaim, `/dispatch` rewrite, `/batch`). Spec §4 (monitoring UI) → Task C `GET /api/brain/worker/status` + Task D (BrainHealthCard). Spec §5 (`orchestrator_workers`) → Task C Step 1. Spec §6 tests → mapped into each task. Spec §7 risks → handled (see below).
- **Deviation from spec §3.1 "all four agents":** the runner registry covers the three task-runnable agents (`discovery`, `head`, `qualifier`) as the spec's own §3.1 bullets define; `scout` is a chat agent with no dispatchable task and dispatching it raises `ValueError` → 404, consistent with the existing unknown-agent behavior. `test_orchestrator.py` asserts the registry is exactly those three.
- **Discovery has two run paths:** Scout HQ `/agents/discovery/start` keeps `crm/runner.py::start_discovery_scout` (single-slot + cooperative cancel); orchestrator batch/single dispatch uses `run_discovery_only` with a queue-owned recorder. No double-recording: the orchestrator recorder's `pipeline_run_id` is pre-bound so `run_discovery_only` skips `start_pipeline()`.
- **`record_query` signature change** (Task A) is shipped together with the migration and P4-test updates so each commit leaves the suite green.
- **Thread pool + `--reload`:** workers die on reload; `reclaim_stale_runs` runs on FastAPI startup (Task C Step 9) and marks orphaned runs failed. Startup hook is inert in tests (`TestClient` not used as a context manager).
- **LLM reachability:** runners mark runs `failed` rather than raising; `_run_head`/`_run_qualifier`/`_run_discovery` all wrap in `try/except`.
- **`test_dispatch_meta.py` hermeticity:** patched `crm.orchestrator.pool` so no real thread/LLM runs during the DB-gated meta assertions.
- **Placeholders:** none — every step has concrete code or commands. Migration revision ids `20260808_0008`/`20260808_0009` chain from the current head `20260807_0007`.
