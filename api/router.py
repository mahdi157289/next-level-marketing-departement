"""Unified /api router for the SPA — includes the CRM REST router + new endpoints."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from crm import schemas, service
from crm.router import router as crm_router

router = APIRouter()
router.include_router(crm_router)  # exposes /api/* inherited CRM routes


class ScoutThreadCreate(BaseModel):
    title: Optional[str] = None


class ScoutMessageCreate(BaseModel):
    content: str


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
