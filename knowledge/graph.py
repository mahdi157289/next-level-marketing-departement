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
            g = traversal().withRemote(_conn)
            # gremlinpython connects lazily; force the WebSocket handshake so
            # connection errors surface as GraphUnavailable here, not later.
            g.V().limit(1).count().next()
        else:
            g = traversal().withRemote(_conn)
        return g
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
        .id_().next()
    )
    return str(v)


def _upsert_lead(g, pg_id: str, url: Optional[str], name: Optional[str], industry: Optional[str]) -> str:
    v = (
        g.V().hasLabel("lead").has("pg_id", pg_id)
        .fold().coalesce(__.unfold(), __.addV("lead").property("pg_id", pg_id))
        .id_().next()
    )
    for key, val in (("url", url), ("name", name), ("industry", industry)):
        if val is not None:
            g.V(v).property(key, str(val)).iterate()
    return str(v)


def _upsert_run(g, run_id: str, status: Optional[str]) -> str:
    v = (
        g.V().hasLabel("run").has("run_id", run_id)
        .fold().coalesce(__.unfold(), __.addV("run").property("run_id", run_id))
        .id_().next()
    )
    if status is not None:
        g.V(v).property("status", str(status)).iterate()
    return str(v)


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
        .where(__.out("belongs_to").has("name", domain))
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
