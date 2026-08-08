"""REST API for the graph/RAG brain (P4)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from crm import schemas

router = APIRouter(prefix="/brain", tags=["brain"])


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


@router.get("/worker/status")
def worker_status():
    from crm import orchestrator

    return {
        "active": orchestrator.active_count(),
        "max_workers": orchestrator.pool().max_workers,
        "queued": orchestrator.queued_count(),
    }
