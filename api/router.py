"""Unified /api router for the SPA — includes the CRM REST router + new endpoints."""
from __future__ import annotations

import asyncio
import json
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from crm import schemas, service
from crm.router import router as crm_router
from api.brain_router import router as brain_router

router = APIRouter()
router.include_router(crm_router)  # exposes /api/* inherited CRM routes
router.include_router(brain_router)  # exposes /api/brain/*


class ScoutThreadCreate(BaseModel):
    title: Optional[str] = None


class ScoutMessageCreate(BaseModel):
    content: str


class AgentDispatchRequest(BaseModel):
    seed_query: Optional[str] = None
    mission: Optional[str] = None


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
    return _scout_chat_events(thread_id, body.content)


def _scout_chat_events(
    thread_id: str, content: str, profile=None
) -> StreamingResponse:
    """SSE stream for a Scout chat turn.

    ``profile`` defaults to the real ``scout._load_scout_profile`` (resolved lazily by
    ``run_scout_turn``) when ``None``; pass an explicit profile to inject / avoid a
    profile lookup.
    """
    from crm import scout

    async def gen():
        try:
            yield "event: start\ndata: {}\n\n"
            run_kwargs = {}
            if profile is not None:
                run_kwargs["profile"] = profile
            result = await asyncio.to_thread(
                scout.run_scout_turn, thread_id, content, **run_kwargs
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


def _chunk_text(text: str, size: int) -> List[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]


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


@router.post("/agents/{agent_name}/dispatch", response_model=schemas.PipelineRunOut, status_code=201)
def api_dispatch_agent(agent_name: str, body: AgentDispatchRequest):
    """Generic, agent-agnostic dispatch. Reuses the pipeline-run mechanism.

    For Discovery, delegates to the live scout runner (records a PipelineRun with
    the mission in its meta, then returns the full PipelineRun). For other agents,
    records a PipelineRun so the Head UI can track dispatch (execution is left to
    the agent's own start endpoint / scheduler). Always returns PipelineRunOut.
    """
    if agent_name == "discovery":
        from crm import runner

        seed = (body.seed_query or "").strip()
        if len(seed) < 2:
            profile = service.get_agent_profile("discovery") or {}
            seed = (profile.get("default_seed_query") or "").strip()
        if len(seed) < 2:
            raise HTTPException(
                status_code=400,
                detail="seed_query required (or set default_seed_query on the Discovery profile)",
            )
        try:
            kicked = runner.start_discovery_scout(seed, mission=body.mission)
        except RuntimeError as e:
            raise HTTPException(status_code=409, detail=str(e))
        run = service.get_pipeline_run(kicked["pipeline_run_id"])
        if run is None:
            raise HTTPException(status_code=500, detail="pipeline run not found after dispatch")
        return run
    # Non-discovery agents: record a dispatch run (execution by the agent's own start endpoint).
    try:
        run = service.dispatch_agent_task(agent_name, body.seed_query, body.mission)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return run


@router.get(
    "/scout/threads/{thread_id}/messages",
    response_model=List[schemas.ScoutMessageOut],
)
def api_list_messages(thread_id: str, limit: int = 200):
    try:
        return service.list_scout_messages(thread_id, limit=limit)
    except ValueError:
        raise HTTPException(status_code=422, detail="thread_id must be a UUID")
