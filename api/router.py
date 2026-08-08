"""Unified /api router for the SPA — includes the CRM REST router + new endpoints."""
from __future__ import annotations

import asyncio
import json
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from crm import schemas, service
from crm.agents_registry import roster_names
from crm.router import router as crm_router
from api.brain_router import router as brain_router

router = APIRouter()
router.include_router(crm_router)  # exposes /api/* inherited CRM routes
router.include_router(brain_router)  # exposes /api/brain/*


class ScoutThreadCreate(BaseModel):
    title: Optional[str] = None


class ScoutMessageCreate(BaseModel):
    content: str


class PromptUpdate(BaseModel):
    content: str


class AgentDispatchRequest(BaseModel):
    seed_query: Optional[str] = None
    mission: Optional[str] = None


class BatchMission(BaseModel):
    seed_query: Optional[str] = None
    mission: Optional[str] = None


class BatchDispatchRequest(BaseModel):
    missions: List[BatchMission] = Field(default_factory=list)


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
    return _agent_chat_events("discovery", thread_id, body.content)


def _agent_chat_events(
    agent_name: str, thread_id: str, content: str, profile=None
) -> StreamingResponse:
    """SSE stream for an agent chat turn.

    ``profile`` defaults to the real ``scout._load_agent_profile`` (resolved lazily by
    ``run_agent_turn``) when ``None``; pass an explicit profile to inject / avoid a
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


@router.get(
    "/scout/threads/{thread_id}/messages",
    response_model=List[schemas.ScoutMessageOut],
)
def api_list_messages(thread_id: str, limit: int = 200):
    try:
        return service.list_scout_messages(thread_id, limit=limit)
    except ValueError:
        raise HTTPException(status_code=422, detail="thread_id must be a UUID")


@router.get("/agents/{agent_name}/threads", response_model=List[schemas.ScoutThreadOut])
def api_list_agent_threads(agent_name: str, limit: int = 50):
    if agent_name not in roster_names():
        raise HTTPException(status_code=400, detail=f"Unknown agent: {agent_name}")
    return service.list_scout_threads(agent_name=agent_name, limit=limit)


@router.post("/agents/{agent_name}/threads", response_model=schemas.ScoutThreadOut, status_code=201)
def api_create_agent_thread(agent_name: str, body: ScoutThreadCreate):
    if agent_name not in roster_names():
        raise HTTPException(status_code=400, detail=f"Unknown agent: {agent_name}")
    return service.create_scout_thread(body.title, agent_name=agent_name)


@router.get(
    "/agents/{agent_name}/threads/{thread_id}/messages",
    response_model=List[schemas.ScoutMessageOut],
)
def api_list_agent_messages(agent_name: str, thread_id: str, limit: int = 200):
    if agent_name not in roster_names():
        raise HTTPException(status_code=400, detail=f"Unknown agent: {agent_name}")
    try:
        return service.list_scout_messages(thread_id, limit=limit)
    except ValueError:
        raise HTTPException(status_code=422, detail="thread_id must be a UUID")


@router.post("/agents/{agent_name}/threads/{thread_id}/messages")
def api_agent_chat(agent_name: str, thread_id: str, body: ScoutMessageCreate):
    if agent_name not in roster_names():
        raise HTTPException(status_code=400, detail=f"Unknown agent: {agent_name}")
    return _agent_chat_events(agent_name, thread_id, body.content)


@router.get("/agents/{agent_name}/prompt")
def api_get_agent_prompt(agent_name: str):
    if agent_name not in roster_names():
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
    if agent_name not in roster_names():
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
