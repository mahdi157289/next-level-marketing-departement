"""Unified /api router for the SPA — includes the CRM REST router + new endpoints."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from crm import schemas, service
from crm.router import router as crm_router

router = APIRouter()
router.include_router(crm_router)  # exposes /api/* inherited CRM routes


class ScoutThreadCreate(BaseModel):
    title: Optional[str] = None


@router.get("/pipeline-runs", response_model=List[schemas.PipelineRunListOut])
def api_list_pipeline_runs(limit: int = 50):
    return service.list_pipeline_runs(limit=limit)


@router.get("/stats")
def api_stats():
    return service.compute_stats()


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
