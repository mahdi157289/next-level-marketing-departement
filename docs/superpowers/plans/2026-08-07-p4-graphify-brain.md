# P4 — Graphify (JanusGraph) Brain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a JanusGraph graph brain (company/services/leads/runs + traversal queries) and an orchestrated `scoped_query` = Redis cache → pgvector → graph-expand → cache, with `brain_query_metrics` telemetry, all exposed via a `/api/brain/*` REST surface — degrading gracefully when JanusGraph/Redis are off.

**Architecture:** JanusGraph (BerkeleyDB backend, `janusgraph/janusgraph:1.1.0`) runs under the compose `brain` profile and exposes Gremlin Server on 8182. A new `knowledge/graph.py` module ingests Postgres data (company, 5 services, leads, runs) as vertices/edges and runs traversal queries via `gremlinpython`. `knowledge/rag.py::scoped_query` layers Redis cache → pgvector search → graph expansion, records telemetry to a new `brain_query_metrics` table, and returns structured results. The graph/cache are optional: any unreachable dependency degrades to the layer below.

**Tech Stack:** JanusGraph 1.1.0 (BerkeleyDB + Lucene, default image config), gremlinpython 3.7.x, redis-py, SQLAlchemy raw SQL (existing pattern), FastAPI, pgvector (existing `db/embeddings.py`), Ollama embeddings (existing).

## Global Constraints

- "No paid APIs / local LLM only." All new services are local containers.
- App image is `python:3.11-slim`; new pip deps go in `requirements.txt` and require an app image rebuild.
- JanusGraph is **off by default**: `docker compose up -d` must NOT start it. It lives under `profiles: ["brain"]`. The app must keep working without it (every graph function degrades, never raises to the caller).
- Follow existing test conventions: flat `tests/test_*.py`, DB-gated tests use `@pytest.mark.skipif(not os.getenv("DATABASE_URL"), ...)`, API tests use `TestClient(app)` from `api.main`.
- Migrations are applied only on app container start (via `scripts/docker_entrypoint.py`); a new migration must be applied with `docker compose up -d --no-deps app`.
- Windows host / PowerShell. Use `docker compose` (not `docker-compose`). Redis is already in compose (`redis:7-alpine` on 6379).
- Raw-SQL + `SessionLocal`/`engine` is the established data-access pattern (see `db/embeddings.py`, `db/session.py`). Do not introduce a new ORM layer.

---

### Task 1: JanusGraph + Redis deps, compose service, settings

**Files:**
- Modify: `requirements.txt`
- Modify: `docker-compose.yml`
- Modify: `config/settings.py`
- Test: (verify via commands)

**Interfaces:**
- Produces: settings fields `janusgraph_base_url` and `redis_url` (used by every later task); compose service `janusgraph` reachable at `ws://janusgraph:8182/gremlin` inside the app network and `ws://127.0.0.1:8182/gremlin` on the host.

- [ ] **Step 1: Add pip dependencies**

Append to `requirements.txt`:

```
# Graphify (P4) — JanusGraph Gremlin client + Redis cache
gremlinpython>=3.7.0,<3.8
redis>=5.0.0
```

- [ ] **Step 2: Add the JanusGraph compose service**

In `docker-compose.yml`, add a `janusgraph` service (before `app`) and a `janusgraph_data` volume. The default image config is already BerkeleyDB + Lucene (data at `/var/lib/janusgraph/data`):

```yaml
  janusgraph:
    image: janusgraph/janusgraph:1.1.0
    container_name: marketing_janusgraph
    profiles: ["brain"]
    ports:
      - "8182:8182"
    volumes:
      - janusgraph_data:/var/lib/janusgraph
```

Add to the `volumes:` block at the bottom:

```yaml
  janusgraph_data:
```

- [ ] **Step 3: Add app env overrides for JanusGraph + Redis**

In `docker-compose.yml` under `app:` → `environment:`, add:

```yaml
      JANUSGRAPH_BASE_URL: ws://janusgraph:8182/gremlin
      REDIS_URL: redis://redis:6379/2
```

- [ ] **Step 4: Add settings fields**

In `config/settings.py`, add to `class Settings`:

```python
    janusgraph_base_url: str = "ws://localhost:8182/gremlin"
    redis_url: str = "redis://localhost:6379/2"
    brain_cache_ttl_s: int = 3600
```

- [ ] **Step 5: Rebuild the app image with the new deps**

Run:
`docker compose build app`

Expected: build succeeds; `pip install` includes gremlinpython + redis.

- [ ] **Step 6: Start JanusGraph (brain profile) and verify Gremlin Server**

Run:
`docker compose --profile brain up -d janusgraph`

Expected: container `marketing_janusgraph` starts. Wait for Gremlin Server (first start can take 20-60s). Verify the WebSocket port answers:

`docker exec marketing_janusgraph sh -c "echo 'x' | nc -w 3 127.0.0.1 8182 || echo NC_UNSUPPORTED"`

(If `nc` is absent, use the verification in Task 3's live check instead — the authoritative check is connecting via gremlinpython.) Confirm the compose file is valid with the profile gate:

Run: `docker compose config --services`
Expected: lists `postgres redis litellm app web janusgraph`.

Run: `docker compose config --services` (should be unchanged from before if profile were off — the profile ensures default `up` skips it):
Confirm janusgraph is NOT in `docker compose ps` after a plain `docker compose up -d` (do not run this now — just confirm `profiles: ["brain"]` is present in the file).

- [ ] **Step 7: Restart app (rebuild applied) and smoke check**

Run: `docker compose up -d --no-deps app`
Then verify app healthy: `Invoke-WebRequest -UseBasicParsing http://localhost:3000/api/agents/tools -TimeoutSec 10` → StatusCode 200.

- [ ] **Step 8: Commit**

```bash
git add requirements.txt docker-compose.yml config/settings.py
git commit -m "feat(P4): janusgraph (brain profile) + redis deps + settings"
```

---

### Task 2: `brain_query_metrics` table + `db/brain_metrics.py`

**Files:**
- Create: `migrations/versions/20260807_0007_brain_query_metrics.py`
- Create: `db/brain_metrics.py`
- Test: `tests/test_brain_metrics.py`

**Interfaces:**
- Produces: `db.brain_metrics.record_query(agent_name: str, domain: Optional[str], query_hash: str, latency_ms: int, cache_hit: bool, vector_hits: int, graph_hits: int) -> None` and `db.brain_metrics.recent_queries(limit: int = 20) -> List[Dict[str, Any]]` (dict keys: `id, agent_name, domain, query_hash, latency_ms, cache_hit, vector_hits, graph_hits, created_at`).

- [ ] **Step 1: Write the migration**

`migrations/versions/20260807_0007_brain_query_metrics.py`:

```python
"""Add brain_query_metrics table (P4 — RAG query telemetry)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260807_0007"
down_revision = "20260807_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "brain_query_metrics",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("agent_name", sa.String(), nullable=False),
        sa.Column("domain", sa.String(), nullable=True),
        sa.Column("query_hash", sa.String(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("cache_hit", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("vector_hits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("graph_hits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_brain_query_metrics_agent_created", "brain_query_metrics", ["agent_name", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_brain_query_metrics_agent_created", table_name="brain_query_metrics")
    op.drop_table("brain_query_metrics")
```

Check the existing `migrations/versions/20260807_0006_agent_chunks_vector.py` to confirm `revision`/`down_revision` id format matches (it must be `"20260807_0007"` and `down_revision="20260807_0006"`).

- [ ] **Step 2: Write `db/brain_metrics.py`**

```python
"""brain_query_metrics — record + read RAG brain query telemetry (P4)."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from db.session import engine


def record_query(
    agent_name: str,
    domain: Optional[str],
    query_hash: str,
    latency_ms: int,
    cache_hit: bool,
    vector_hits: int,
    graph_hits: int,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO brain_query_metrics
                    (id, agent_name, domain, query_hash, latency_ms, cache_hit, vector_hits, graph_hits, created_at)
                VALUES (:id, :agent_name, :domain, :query_hash, :latency_ms, :cache_hit, :vector_hits, :graph_hits, NOW())
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
            },
        )


def recent_queries(limit: int = 20) -> List[Dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, agent_name, domain, query_hash, latency_ms, cache_hit, vector_hits, graph_hits, created_at
                FROM brain_query_metrics
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        ).mappings().all()
    return [dict(r) for r in rows]
```

- [ ] **Step 3: Write the failing test**

`tests/test_brain_metrics.py`:

```python
"""P4 — brain_query_metrics telemetry (real Postgres, DB-gated)."""

from __future__ import annotations

import os
import uuid
from typing import Optional

import pytest


def _database_url() -> Optional[str]:
    return os.getenv("DATABASE_URL")


@pytest.mark.skipif(not _database_url(), reason="DATABASE_URL not set")
def test_record_and_recent_roundtrip():
    from db.brain_metrics import recent_queries, record_query

    h = "testhash-" + uuid.uuid4().hex[:8]
    record_query("pytest", "tn", h, 12, False, 2, 1)
    rows = recent_queries(limit=5)
    assert any(r["query_hash"] == h for r in rows)
    row = next(r for r in rows if r["query_hash"] == h)
    assert row["cache_hit"] is False
    assert row["vector_hits"] == 2
    assert row["graph_hits"] == 1
    assert row["created_at"] is not None
```

- [ ] **Step 4: Run test to verify it fails**

Run: `python -m pytest tests/test_brain_metrics.py -q --no-header`
Expected: FAIL (ImportError: `db.brain_metrics` module not found — or table missing).

- [ ] **Step 5: Apply the migration (restart app so the entrypoint runs alembic)**

Run: `docker compose up -d --no-deps app`
Then confirm the table exists:

Run: `docker exec marketing_postgres psql -U admin -d marketing_db -tAc "select count(*) from brain_query_metrics;"`
Expected: `0` (table exists, empty).

- [ ] **Step 6: Run test to verify it passes**

Run: `python -m pytest tests/test_brain_metrics.py -q --no-header`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add migrations/versions/20260807_0007_brain_query_metrics.py db/brain_metrics.py tests/test_brain_metrics.py
git commit -m "feat(P4): brain_query_metrics table + record/recent helpers"
```

---

### Task 3: `knowledge/graph.py` — JanusGraph client, ingest, traversal

**Files:**
- Create: `knowledge/graph.py`
- Test: `tests/test_graph.py`

**Interfaces:**
- Consumes: `config.settings.get_settings()` (fields `janusgraph_base_url`).
- Produces:
  - `class knowledge.graph.GraphUnavailable(RuntimeError)`
  - `graph_available() -> bool`
  - `reset_connection() -> None` (tests only)
  - `ingest_all_from_db() -> Dict[str, Any]` (returns `{"company": 1, "services": 5, "leads": N, "runs": M}`; raises `GraphUnavailable` if unreachable)
  - `expand_related_leads(terms: List[str], domain: str, limit: int = 5) -> List[Dict[str, Any]]` (returns `[]` on unreachable — never raises)
  - `graph_stats() -> Dict[str, Any]` (returns `{"available": bool, "vertices": n, "edges": n}`, `available: False` when unreachable)
  - Internal `_get_g()` → gremlinpython `GraphTraversalSource` or raises `GraphUnavailable`; `_expand_traversal(g, terms, domain, limit)` builds the traversal (pure, used by tests).

- [ ] **Step 1: Write the failing tests**

`tests/test_graph.py`:

```python
"""P4 — knowledge/graph.py (unit tests, no live JanusGraph required)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest


def _unreachable_settings(monkeypatch):
    from knowledge import graph

    graph.reset_connection()
    monkeypatch.setattr(
        graph, "get_settings", lambda: SimpleNamespace(janusgraph_base_url="ws://127.0.0.1:1/gremlin")
    )


def test_graph_available_false_when_unreachable(monkeypatch):
    from knowledge import graph

    _unreachable_settings(monkeypatch)
    assert graph.graph_available() is False


def test_expand_related_leads_falls_back_to_empty(monkeypatch):
    from knowledge import graph

    _unreachable_settings(monkeypatch)
    assert graph.expand_related_leads(["web"], "tn", limit=5) == []


def test_graph_stats_reports_unavailable(monkeypatch):
    from knowledge import graph

    _unreachable_settings(monkeypatch)
    stats = graph.graph_stats()
    assert stats["available"] is False


def test_ingest_all_from_db_raises_when_unreachable(monkeypatch):
    from knowledge import graph

    _unreachable_settings(monkeypatch)
    with pytest.raises(graph.GraphUnavailable):
        graph.ingest_all_from_db()


def test_expand_traversal_builds_without_server():
    # Building a traversal must not require a connection.
    from gremlin_python.process.anonymous_traversal import traversal

    from knowledge import graph

    g = traversal()
    tr = graph._expand_traversal(g, ["web"], "tn", 5)
    assert tr is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_graph.py -q --no-header`
Expected: FAIL (ImportError: no module `knowledge.graph`).

- [ ] **Step 3: Write `knowledge/graph.py`**

```python
"""Graphify (JanusGraph) graph brain — company/services/leads/runs + traversal.

Degrades gracefully: when JanusGraph is not running (compose profile `brain`
is off) every query function returns empty results / `False` instead of
raising, so the pgvector brain and the app keep working.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from gremlin_python.driver.driver_remote_connection import DriverRemoteConnection
from gremlin_python.process.anonymous_traversal import traversal
from gremlin_python.process.graph_traversal import __
from gremlin_python.process.traversal import P

from config.settings import get_settings

COMPANY_NAME = "Next Level Tech Company"
SERVICES = ["development", "data", "marketing", "automation", "migration"]
_SERVICE_KEYWORDS = {
    "development": ("dev", "development", "software", "web", "app", "code"),
    "data": ("data", "analytics", "ai", "ml", "scraping"),
    "marketing": ("market", "seo", "ad", "agency", "lead", "social"),
    "automation": ("automation", "workflow", "automate", "chatbot"),
    "migration": ("migration", "migrate", "migrating", "move"),
}


class GraphUnavailable(RuntimeError):
    """Raised when JanusGraph / Gremlin Server cannot be reached."""


_conn: Optional[DriverRemoteConnection] = None


def reset_connection() -> None:
    """Tests only — force a fresh driver connection on next use."""
    global _conn
    _conn = None


def _get_g():
    global _conn
    base = get_settings().janusgraph_base_url
    try:
        if _conn is None:
            _conn = DriverRemoteConnection(base, "g")
        return traversal().withRemote(_conn)
    except Exception as e:  # noqa: BLE001
        raise GraphUnavailable(f"janusgraph unreachable at {base}: {e}") from e


def graph_available() -> bool:
    try:
        return bool(_get_g().V().limit(1).count().next() >= 0)
    except Exception:  # noqa: BLE001
        return False


def _upsert(g, label: str, name: str) -> str:
    v = (
        g.V().hasLabel(label).has("name", name)
        .fold().coalesce(__.unfold(), __.addV(label).property("name", name))
        .next()
    )
    return str(v.id)


def _upsert_lead(g, pg_id: str, url: Optional[str], name: Optional[str], industry: Optional[str]) -> str:
    v = (
        g.V().hasLabel("lead").has("pg_id", pg_id)
        .fold().coalesce(__.unfold(), __.addV("lead").property("pg_id", pg_id))
        .next()
    )
    for key, val in (("url", url), ("name", name), ("industry", industry)):
        if val is not None:
            g.V(v.id).property(key, str(val)).iterate()
    return str(v.id)


def _upsert_run(g, run_id: str, status: Optional[str]) -> str:
    v = (
        g.V().hasLabel("run").has("run_id", run_id)
        .fold().coalesce(__.unfold(), __.addV("run").property("run_id", run_id))
        .next()
    )
    if status is not None:
        g.V(v.id).property("status", str(status)).iterate()
    return str(v.id)


def _edge(g, out_id: str, label: str, in_id: str) -> None:
    g.V(out_id).addE(label).to(__.V(in_id)).iterate()


def ingest_all_from_db() -> Dict[str, Any]:
    """Clear and rebuild the graph from Postgres (idempotent rebuild)."""
    from crm import service as crm_service

    g = _get_g()
    g.V().drop().iterate()

    company = _upsert(g, "company", COMPANY_NAME)
    services: Dict[str, str] = {}
    for s in SERVICES:
        services[s] = _upsert(g, "service", s)
        _edge(g, company, "offers", services[s])

    lead_count = 0
    for lead in crm_service.list_leads(limit=10000):
        pg_id = str(lead.get("id") or "")
        if not pg_id:
            continue
        lid = _upsert_lead(
            g, pg_id, url=lead.get("url"), name=lead.get("name"), industry=lead.get("industry")
        )
        domain_name = (lead.get("country") or "global").strip() or "global"
        did = _upsert(g, "domain", domain_name)
        _edge(g, lid, "belongs_to", did)
        hay = " ".join(
            str(lead.get(k) or "") for k in ("name", "industry", "business_type", "country")
        ).lower()
        for svc, keywords in _SERVICE_KEYWORDS.items():
            if any(kw in hay for kw in keywords):
                _edge(g, lid, "related_to", services[svc])
        lead_count += 1

    run_count = 0
    for run in crm_service.list_pipeline_runs(limit=5000):
        rid = _upsert_run(g, str(run.get("id") or ""), status=run.get("status"))
        _edge(g, rid, "for_company", company)
        run_count += 1

    return {"company": 1, "services": len(services), "leads": lead_count, "runs": run_count}


def _first(d: Dict[str, Any], key: str) -> str:
    v = d.get(key)
    if isinstance(v, list) and v:
        return str(v[0])
    return str(v or "")


def _expand_traversal(g, terms: List[str], domain: str, limit: int):
    return (
        g.V().hasLabel("lead")
        .where(__.in_("belongs_to").has("name", domain))
        .where(__.out("related_to").has("name", P.within(*terms)))
        .dedup()
        .limit(limit)
        .valueMap("pg_id", "name", "url", "industry")
    )


def expand_related_leads(terms: List[str], domain: str, limit: int = 5) -> List[Dict[str, Any]]:
    try:
        g = _get_g()
        rows = _expand_traversal(g, terms, domain, limit).toList()
    except Exception:  # noqa: BLE001
        return []
    out = []
    for m in rows:
        out.append(
            {
                "pg_id": _first(m, "pg_id"),
                "name": _first(m, "name"),
                "url": _first(m, "url"),
                "industry": _first(m, "industry"),
            }
        )
    return out


def graph_stats() -> Dict[str, Any]:
    try:
        g = _get_g()
        return {"available": True, "vertices": int(g.V().count().next()), "edges": int(g.E().count().next())}
    except Exception:  # noqa: BLE001
        return {"available": False, "vertices": 0, "edges": 0}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_graph.py -q --no-header`
Expected: PASS (5 tests).

- [ ] **Step 5: Live check against the running JanusGraph (from inside the app container)**

Run:
`docker exec marketing_app python -c "from knowledge.graph import graph_available, graph_stats, ingest_all_from_db; print('available:', graph_available()); print(graph_stats()); print(ingest_all_from_db())"`

Expected: `available: True`, a `graph_stats()` with `available: True`, and an ingest dict like `{'company': 1, 'services': 5, 'leads': N, 'runs': M}`. If this errors, check the JanusGraph container is still up (`docker ps --filter name=marketing_janusgraph`) and the app env has `JANUSGRAPH_BASE_URL` set.

- [ ] **Step 6: Commit**

```bash
git add knowledge/graph.py tests/test_graph.py
git commit -m "feat(P4): janusgraph graph module — ingest + traversal, graceful degradation"
```

---

### Task 4: `knowledge/rag.py` — orchestrated `scoped_query`

**Files:**
- Create: `knowledge/rag.py`
- Test: `tests/test_rag.py`

**Interfaces:**
- Consumes: `db.embeddings.search_chunks(agent_name, query, scope=None, limit=5) -> List[Dict]`; `knowledge.graph.expand_related_leads(terms, domain, limit) -> List[Dict]`; `db.brain_metrics.record_query(...)`; settings `redis_url`, `brain_cache_ttl_s`.
- Produces: `knowledge.rag.scoped_query(agent_name: str, domain: str, query: str, limit: int = 5, use_cache: bool = True) -> Dict[str, Any]` with keys `query, domain, agent_name, cache_hit, vector_hits, graph_hits, results, checked_at, latency_ms`. Each result item is `{"type": "chunk"|"lead", "source": ..., "content": ..., "url": ...?, "similarity": ...?}`. Never raises: on any cache/vector/graph/metrics failure it degrades and still returns.

- [ ] **Step 1: Write the failing tests**

`tests/test_rag.py`:

```python
"""P4 — knowledge/rag.py scoped_query orchestration (monkeypatched layers)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest


@pytest.fixture
def patch_layers(monkeypatch):
    from knowledge import rag

    calls = {"vector": 0, "graph": 0, "cache_set": 0, "record": 0}
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
        lambda *a, **kw: calls.__setitem__("record", calls["record"] + 1),
    )
    return rag, calls


def test_cache_hit_short_circuits_vector_and_graph(monkeypatch):
    from knowledge import rag

    monkeypatch.setattr(rag, "cache_get", lambda key: {"results": [], "cache_hit": False})
    monkeypatch.setattr(rag, "search_chunks", lambda *a, **kw: pytest.fail("vector called on cache hit"))
    monkeypatch.setattr(rag, "expand_related_leads", lambda *a, **kw: pytest.fail("graph called on cache hit"))
    monkeypatch.setattr(rag, "record_query", lambda *a, **kw: None)
    out = rag.scoped_query("discovery", "tn", "web agency", limit=5)
    assert out["cache_hit"] is True


def test_miss_runs_vector_then_graph_and_caches(patch_layers):
    rag, calls = patch_layers
    out = rag.scoped_query("discovery", "tn", "web agency tunisia", limit=5)
    assert calls["vector"] == 1
    assert calls["graph"] == 1
    assert calls["cache_set"] == 1
    assert calls["record"] == 1
    assert out["cache_hit"] is False
    assert out["vector_hits"] == 1
    assert out["graph_hits"] == 1
    types = {r["type"] for r in out["results"]}
    assert types == {"chunk", "lead"}


def test_graph_down_still_returns_vector(patch_layers, monkeypatch):
    rag, calls = patch_layers
    monkeypatch.setattr(rag, "expand_related_leads", lambda *a, **kw: [])
    out = rag.scoped_query("discovery", "tn", "web agency", limit=5)
    assert out["graph_hits"] == 0
    assert any(r["type"] == "chunk" for r in out["results"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_rag.py -q --no-header`
Expected: FAIL (ImportError: no module `knowledge.rag`).

- [ ] **Step 3: Write `knowledge/rag.py`**

```python
"""Orchestrated RAG brain: Redis cache -> pgvector -> graph-expand -> cache.

`scoped_query` is the single entry point P6 will wire into agents. It never
raises: cache, vector, graph and metrics layers each degrade independently.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from db.brain_metrics import record_query
from db.embeddings import search_chunks
from knowledge import graph as graphmod
from config.settings import get_settings

_redis = None


def _cache_client():
    global _redis
    if _redis is None:
        import redis

        _redis = redis.Redis.from_url(
            get_settings().redis_url, decode_responses=True, socket_connect_timeout=2
        )
    return _redis


def _cache_key(agent_name: str, domain: str, query: str) -> str:
    h = hashlib.sha256(f"{agent_name}:{domain}:{query}".encode("utf-8")).hexdigest()
    return f"brain:{agent_name}:{domain}:{h}"


def cache_get(key: str) -> Optional[Dict[str, Any]]:
    try:
        val = _cache_client().get(key)
        return json.loads(val) if val else None
    except Exception:  # noqa: BLE001
        return None


def cache_set(key: str, payload: Dict[str, Any]) -> None:
    try:
        _cache_client().set(key, json.dumps(payload), ex=get_settings().brain_cache_ttl_s)
    except Exception:  # noqa: BLE001
        pass


def expand_related_leads(terms: List[str], domain: str, limit: int = 5) -> List[Dict[str, Any]]:
    return graphmod.expand_related_leads(terms, domain, limit=limit)


def scoped_query(
    agent_name: str,
    domain: str,
    query: str,
    limit: int = 5,
    use_cache: bool = True,
) -> Dict[str, Any]:
    t0 = time.monotonic()
    key = _cache_key(agent_name, domain, query)

    if use_cache:
        cached = cache_get(key)
        if cached is not None:
            cached["cache_hit"] = True
            cached["latency_ms"] = int((time.monotonic() - t0) * 1000)
            try:
                record_query(
                    agent_name, domain, key, cached["latency_ms"], True,
                    cached.get("vector_hits", 0), cached.get("graph_hits", 0),
                )
            except Exception:  # noqa: BLE001
                pass
            return cached

    vector: List[Dict[str, Any]] = []
    try:
        vector = search_chunks(agent_name, query, scope=domain, limit=limit)
    except Exception:  # noqa: BLE001
        vector = []

    graph_leads: List[Dict[str, Any]] = []
    try:
        terms = [t for t in query.lower().split() if len(t) > 2]
        graph_leads = graphmod.expand_related_leads(terms, domain, limit=limit)
    except Exception:  # noqa: BLE001
        graph_leads = []

    results: List[Dict[str, Any]] = [
        {
            "type": "chunk",
            "source": c.get("source_uri"),
            "content": c.get("content"),
            "similarity": c.get("similarity"),
        }
        for c in vector
    ]
    results += [
        {
            "type": "lead",
            "source": l.get("url"),
            "content": l.get("name"),
            "url": l.get("url"),
        }
        for l in graph_leads
    ]

    payload: Dict[str, Any] = {
        "query": query,
        "domain": domain,
        "agent_name": agent_name,
        "cache_hit": False,
        "vector_hits": len(vector),
        "graph_hits": len(graph_leads),
        "results": results,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    payload["latency_ms"] = int((time.monotonic() - t0) * 1000)

    if use_cache:
        cache_set(key, payload)

    try:
        record_query(
            agent_name, domain, key, payload["latency_ms"], False,
            len(vector), len(graph_leads),
        )
    except Exception:  # noqa: BLE001
        pass

    return payload
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_rag.py -q --no-header`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add knowledge/rag.py tests/test_rag.py
git commit -m "feat(P4): scoped_query orchestration — cache -> pgvector -> graph -> metrics"
```

---

### Task 5: `/api/brain/*` REST surface

**Files:**
- Modify: `crm/schemas.py`
- Create: `api/brain_router.py`
- Modify: `api/router.py`
- Test: `tests/test_brain_api.py`

**Interfaces:**
- Consumes: `knowledge.rag.scoped_query`, `knowledge.graph.ingest_all_from_db`, `knowledge.graph.graph_stats`, `db.brain_metrics.recent_queries`.
- Produces: `POST /api/brain/scoped_query` body `{agent_name, domain, query, limit?}` → scoped_query payload (200); `POST /api/brain/graph/ingest` → `{"company":1,"services":5,"leads":N,"runs":M}` (200) or `503 {"detail": "janusgraph unreachable..."}`; `GET /api/brain/graph/status` → `{"available": bool, "vertices": n, "edges": n}` (200); `GET /api/brain/metrics?limit=20` → `{"metrics": [...]}` (200).

- [ ] **Step 1: Add the request schema**

In `crm/schemas.py`, add near the other request models:

```python
class BrainQueryRequest(BaseModel):
    agent_name: str
    domain: str
    query: str
    limit: int = 5
```

(Check the file's existing imports — `BaseModel` is already imported.)

- [ ] **Step 2: Write the failing tests**

`tests/test_brain_api.py`:

```python
"""P4 — /api/brain/* endpoints (mocked brain layers for shape; live DB test gated)."""

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


def test_scoped_query_endpoint_shape(client):
    payload = {"query": "web agency", "domain": "tn", "agent_name": "discovery", "cache_hit": False,
               "vector_hits": 0, "graph_hits": 0, "results": [], "checked_at": "x", "latency_ms": 1}
    with mock.patch("knowledge.rag.scoped_query", return_value=payload) as m:
        r = client.post("/api/brain/scoped_query", json={"agent_name": "discovery", "domain": "tn", "query": "web agency"})
    assert r.status_code == 200
    assert r.json()["query"] == "web agency"
    m.assert_called_once()


def test_graph_status_endpoint_shape(client):
    with mock.patch("knowledge.graph.graph_stats", return_value={"available": False, "vertices": 0, "edges": 0}):
        r = client.get("/api/brain/graph/status")
    assert r.status_code == 200
    assert r.json()["available"] is False


def test_graph_ingest_503_when_unavailable(client):
    from knowledge.graph import GraphUnavailable

    with mock.patch("knowledge.graph.ingest_all_from_db", side_effect=GraphUnavailable("down")):
        r = client.post("/api/brain/graph/ingest")
    assert r.status_code == 503


def test_metrics_endpoint_shape(client):
    with mock.patch("db.brain_metrics.recent_queries", return_value=[]):
        r = client.get("/api/brain/metrics")
    assert r.status_code == 200
    assert r.json() == {"metrics": []}


@pytest.mark.skipif(not _database_url(), reason="DATABASE_URL not set")
def test_metrics_endpoint_live_db(client):
    from db.brain_metrics import record_query

    record_query("pytest", "tn", "live-metrics-hash", 3, True, 0, 0)
    r = client.get("/api/brain/metrics", params={"limit": 5})
    assert r.status_code == 200
    assert any(m["query_hash"] == "live-metrics-hash" for m in r.json()["metrics"])
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_brain_api.py -q --no-header`
Expected: FAIL (404/connection errors — routes not registered).

- [ ] **Step 4: Write `api/brain_router.py`**

```python
"""REST API for the graph/RAG brain (P4)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from crm import schemas

router = APIRouter(tags=["brain"])


@router.post("/scoped_query")
def scoped_query(body: schemas.BrainQueryRequest):
    from knowledge.rag import scoped_query as _scoped_query

    return _scoped_query(body.agent_name, body.domain, body.query, limit=body.limit)


@router.post("/graph/ingest")
def graph_ingest():
    from knowledge.graph import GraphUnavailable, ingest_all_from_db

    try:
        return ingest_all_from_db()
    except GraphUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


@router.get("/graph/status")
def graph_status():
    from knowledge.graph import graph_stats

    return graph_stats()


@router.get("/metrics")
def brain_metrics(limit: int = 20):
    from db.brain_metrics import recent_queries

    return {"metrics": recent_queries(limit=limit)}
```

- [ ] **Step 5: Mount the router**

In `api/router.py`, add the import next to the existing crm import (line 13) and include it after the crm include (line 16):

```python
from crm.router import router as crm_router
from api.brain_router import router as brain_router

router = APIRouter()
router.include_router(crm_router)  # exposes /api/* inherited CRM routes
router.include_router(brain_router)  # exposes /api/brain/*
```

Note: `api/brain_router.py` imports `crm.schemas` only at module level and imports `knowledge.*`/`db.brain_metrics` **inside** each route function, so the tests can patch `knowledge.rag.scoped_query`, `knowledge.graph.*`, and `db.brain_metrics.recent_queries` (function-local imports resolve the module attribute at call time).

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_brain_api.py -q --no-header`
Expected: PASS (5 tests).

- [ ] **Step 7: Commit**

```bash
git add crm/schemas.py api/brain_router.py api/router.py tests/test_brain_api.py
git commit -m "feat(P4): /api/brain REST surface — scoped_query, graph ingest/status, metrics"
```

---

### Task 6: Live end-to-end verification + docs

**Files:**
- Modify: `docs/superpowers/specs/2026-08-07-agent-platform-brain.md`

- [ ] **Step 1: Ensure JanusGraph, Ollama and Redis are up**

Run: `docker compose --profile brain --profile ollama up -d janusgraph ollama`
And: `docker compose up -d redis`
Expected: `marketing_janusgraph`, `marketing_ollama` (if the compose project uses the `ollama` profile image; if the running stack uses a separate `nextlevel-ollama` container for embeddings, start that instead), `marketing_redis` all running.

- [ ] **Step 2: Ingest the graph through the API**

Run:
`$b = Invoke-WebRequest -UseBasicParsing -Method POST 'http://localhost:3000/api/brain/graph/ingest' -TimeoutSec 60; $b.StatusCode; $b.Content`

Expected: 200 and a JSON body like `{"company": 1, "services": 5, "leads": N, "runs": M}`.

- [ ] **Step 3: Run a live scoped_query**

First seed a chunk (uses Ollama embeddings), then query:
```
Invoke-WebRequest -UseBasicParsing -Method POST -ContentType 'application/json' -Body '{"agent_name":"discovery","content":"Tunisia digital marketing agencies","scope":"tn"}' 'http://localhost:3000/api/agents/discovery/chunks' -TimeoutSec 60
```
Then:
```
Invoke-WebRequest -UseBasicParsing -Method POST -ContentType 'application/json' -Body '{"agent_name":"discovery","domain":"tn","query":"digital marketing agencies tunisia"}' 'http://localhost:3000/api/brain/scoped_query' -TimeoutSec 60
```
Expected: 200; `vector_hits >= 1` (chunk match) and, if any lead in the graph is linked to the `marketing` service in domain `tn`, `graph_hits >= 1`. Confirm the response has a `latency_ms` and `checked_at`.

- [ ] **Step 4: Verify the Redis cache + metrics**

Re-run the exact same scoped_query body twice:
- First run: `cache_hit: false`.
- Second run: `cache_hit: true` (served from Redis).

Then read the telemetry:
`Invoke-WebRequest -UseBasicParsing 'http://localhost:3000/api/brain/metrics?limit=5' -TimeoutSec 10`
Expected: at least one metric row with `cache_hit: true` and one with `cache_hit: false`, non-null `vector_hits`/`graph_hits`.

- [ ] **Step 5: Verify graceful degradation when JanusGraph is off**

Stop JanusGraph: `docker compose --profile brain stop janusgraph`

Then re-run the scoped_query with a different query (to bypass cache):
Expected: still 200, `graph_hits: 0`, `vector_hits >= 1` — the pgvector brain works without the graph.
Also: `Invoke-WebRequest -UseBasicParsing 'http://localhost:3000/api/brain/graph/status' -TimeoutSec 10` → `{"available": false, "vertices": 0, "edges": 0}`.

Restart JanusGraph so the stack is left in a good state:
`docker compose --profile brain up -d janusgraph`

- [ ] **Step 6: Update the spec doc**

In `docs/superpowers/specs/2026-08-07-agent-platform-brain.md`, change the P4 row:

| P4 | Graphify (JanusGraph) brain — `knowledge/graph.py` + `knowledge/rag.py::scoped_query` (cache → pgvector → graph-expand), `brain_query_metrics` | add `janusgraph` service (compose `brain` profile, BerkeleyDB) | **done** (committed; `/api/brain/*`, graceful degradation when JanusGraph/Redis off, live-verified) |

- [ ] **Step 7: Run the full backend test suite**

Run: `python -m pytest tests/ -q --no-header`
Expected: all previously-passing tests still pass plus the new P4 tests (no regressions).

- [ ] **Step 8: Commit**

```bash
git add docs/superpowers/specs/2026-08-07-agent-platform-brain.md
git commit -m "docs(P4): mark graphify brain done, live-verified"
```

---

## Self-Review Notes

- **Spec coverage:** Spec P4 bullets map to: compose janusgraph service (Task 1), `knowledge/graph.py` ingest + traversal (Task 3), `knowledge/rag.py::scoped_query` = cache→pgvector→graph-expand→cache (Task 4), Redis cache + `brain_query_metrics` (Tasks 2+4), REST exposure (Task 5), live verification + risk-log degradation (Task 6).
- **P6 not included** (user chose to split): scoped retrieval filters into agents, async batch dispatch, metrics UI/endpoint expansion live on top of `/api/brain`.
- **Placeholders:** none; every step has concrete code or commands.
- **Type consistency:** `record_query` signature (Task 2) matches calls in Task 4; `search_chunks` signature matches existing `db/embeddings.py`; `expand_related_leads(terms, domain, limit)` consistent across Tasks 3/4; `scoped_query` payload keys consistent between Task 4 and Task 5 tests.
