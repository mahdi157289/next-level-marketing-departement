"""REST API routes for CRM module."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException

from crm import schemas, service

router = APIRouter(tags=["crm"])


@router.get("/health")
def crm_health() -> dict:
    return service.health_check()


@router.get("/leads", response_model=list[schemas.LeadOut])
def list_leads(status: Optional[str] = None, limit: int = 50):
    return service.list_leads(status=status, limit=limit)


@router.get("/leads/{lead_id}", response_model=schemas.LeadDetailOut)
def get_lead(lead_id: UUID):
    row = service.get_lead(str(lead_id))
    if not row:
        raise HTTPException(status_code=404, detail="Lead not found")
    return row


@router.post("/leads", response_model=schemas.LeadOut, status_code=201)
def create_lead(body: schemas.LeadCreate):
    return service.create_lead(body.model_dump())


@router.patch("/leads/{lead_id}", response_model=schemas.LeadOut)
def update_lead(lead_id: UUID, body: schemas.LeadUpdate):
    data = body.model_dump(exclude_unset=True)
    row = service.update_lead(str(lead_id), data)
    if not row:
        raise HTTPException(status_code=404, detail="Lead not found")
    return row


@router.post("/pipeline-runs", response_model=schemas.PipelineRunOut, status_code=201)
def start_pipeline_run(body: schemas.PipelineRunCreate):
    return service.start_pipeline_run(body.trigger, body.seed_query, body.meta)


@router.patch("/pipeline-runs/{run_id}", response_model=schemas.PipelineRunOut)
def complete_pipeline_run(run_id: UUID, body: schemas.PipelineRunComplete):
    row = service.complete_pipeline_run(str(run_id), body.status, body.meta)
    if not row:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    return row


@router.post("/agent-runs", response_model=schemas.AgentRunOut, status_code=201)
def start_agent_run(body: schemas.AgentRunCreate):
    return service.start_agent_run(
        str(body.pipeline_run_id),
        body.agent_name,
        body.model,
        body.input_summary,
    )


@router.patch("/agent-runs/{run_id}", response_model=schemas.AgentRunOut)
def complete_agent_run(run_id: UUID, body: schemas.AgentRunComplete):
    row = service.complete_agent_run(
        str(run_id),
        body.status,
        body.output_summary,
        body.output_json,
        body.apis_consumed,
        body.records_processed,
        body.error_message,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return row


@router.get("/agent-runs", response_model=list[schemas.AgentRunOut])
def list_agent_runs(
    agent_name: Optional[str] = None,
    pipeline_run_id: Optional[UUID] = None,
    limit: int = 100,
):
    pid = str(pipeline_run_id) if pipeline_run_id else None
    return service.list_agent_runs(agent_name=agent_name, pipeline_run_id=pid, limit=limit)


@router.get("/agent-runs/{run_id}", response_model=schemas.AgentRunOut)
def get_agent_run(run_id: UUID):
    row = service.get_agent_run(str(run_id))
    if not row:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return row


@router.get("/pipeline-runs/{run_id}", response_model=schemas.PipelineRunOut)
def get_pipeline_run(run_id: UUID):
    row = service.get_pipeline_run(str(run_id))
    if not row:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    return row


@router.get("/agents", response_model=list[schemas.AgentProfileOut])
def list_agents():
    return service.list_agent_profiles()


@router.get("/agents/tools", response_model=list[schemas.ToolInfo])
def list_tools():
    return service.tools_catalog()


@router.post("/agents/tools/health")
def tools_health_check() -> dict:
    """Run real live probes against every skill; returns green/red/amber verdicts."""
    from crm import skill_health

    return {
        "checked_at": datetime.utcnow().isoformat(),
        "results": skill_health.run_skill_checks(),
    }


@router.get("/agents/{agent_name}", response_model=schemas.AgentProfileOut)
def get_agent(agent_name: str):
    row = service.get_agent_profile(agent_name)
    if not row:
        raise HTTPException(status_code=404, detail="Agent not found")
    return row


@router.patch("/agents/{agent_name}", response_model=schemas.AgentProfileOut)
def patch_agent(agent_name: str, body: schemas.AgentProfileUpdate):
    try:
        row = service.update_agent_profile(agent_name, body.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not row:
        raise HTTPException(status_code=404, detail="Agent not found")
    return row


@router.get("/agents/{agent_name}/secrets", response_model=list[schemas.AgentSecretOut])
def list_secrets(agent_name: str):
    return service.list_agent_secrets(agent_name)


@router.get("/agents/{agent_name}/providers", response_model=list[schemas.ProviderInfo])
def list_providers(agent_name: str):
    if not service.get_agent_profile(agent_name):
        raise HTTPException(status_code=404, detail="Agent not found")
    return service.list_providers(agent_name)


@router.post("/agents/{agent_name}/secrets", response_model=schemas.AgentSecretOut)
def upsert_secret(agent_name: str, body: schemas.AgentSecretSet):
    service.set_agent_secret(agent_name, body.kind, body.name, body.value)
    return {"agent_name": agent_name, "kind": body.kind, "name": body.name}


@router.get("/agents/{agent_name}/secrets/{kind}/resolve")
def resolve_secret(agent_name: str, kind: str):
    value = service.resolve_agent_secret(agent_name, kind)
    if value is None:
        raise HTTPException(status_code=404, detail="Secret not found")
    name = service.get_secret_name(agent_name, kind)
    return {"kind": kind, "name": name, "value": value}


@router.delete("/agents/{agent_name}/secrets/{kind}", status_code=204)
def delete_secret(agent_name: str, kind: str):
    if not service.delete_agent_secret(agent_name, kind):
        raise HTTPException(status_code=404, detail="Secret not found")
    return None


@router.post("/agents/{agent_name}/memory", response_model=dict)
def add_memory(agent_name: str, body: schemas.AgentMemoryIn):
    return service.add_memory(agent_name, body.scope, body.key, body.value)


@router.get("/agents/{agent_name}/memory", response_model=list[dict])
def get_memory(agent_name: str, scope: Optional[str] = None, limit: int = 100):
    return service.list_memory(agent_name, scope=scope, limit=limit)


@router.post("/agents/{agent_name}/chunks", response_model=schemas.ChunkOut)
def ingest_chunk(agent_name: str, body: schemas.ChunkIngestRequest):
    row = service.ingest_chunk(agent_name, body.content, scope=body.scope, source_uri=body.source_uri)
    row["created_at"] = _now_iso()
    return row


@router.post("/agents/{agent_name}/chunks/search", response_model=list[schemas.ChunkOut])
def search_chunk(agent_name: str, body: schemas.ChunkSearchRequest):
    return service.search_chunks(agent_name, body.query, scope=body.scope, limit=body.limit)


def _now_iso() -> Optional[str]:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@router.post("/agents/discovery/start", response_model=schemas.DiscoveryStartOut)
def start_discovery(body: schemas.DiscoveryStartRequest):
    from crm import runner

    profile = service.get_agent_profile("discovery")
    if not profile:
        raise HTTPException(status_code=404, detail="Discovery agent profile missing — run migrations")
    seed = (body.seed_query or profile.get("default_seed_query") or "").strip()
    if len(seed) < 2:
        raise HTTPException(status_code=400, detail="seed_query required (or set default_seed_query on profile)")
    try:
        # Validate tools still meet discovery requirements
        from tools.registry import validate_tool_ids

        validate_tool_ids(profile.get("enabled_tools") or [], agent_name="discovery")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    try:
        return runner.start_discovery_scout(seed, max_search_results=body.max_search_results, mission=body.mission)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@router.post("/agents/discovery/finish", response_model=schemas.DiscoveryFinishOut)
def finish_discovery():
    from crm import runner

    try:
        return runner.request_finish()
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
