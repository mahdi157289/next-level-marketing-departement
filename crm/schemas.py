"""Pydantic DTOs for CRM REST API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class LeadCreate(BaseModel):
    name: Optional[str] = None
    url: str
    status: str = "raw"
    source: str = "discovery"
    google_maps_url: Optional[str] = None
    address: Optional[str] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    country: Optional[str] = None
    industry: Optional[str] = None
    business_type: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    status_notes: Optional[str] = None
    hours: Optional[str] = None
    description: Optional[str] = None
    price_level: Optional[str] = None
    facebook: Optional[str] = None
    instagram: Optional[str] = None
    linkedin: Optional[str] = None
    twitter: Optional[str] = None
    tags: Optional[List[str]] = None


class LeadUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    status: Optional[str] = None
    google_maps_url: Optional[str] = None
    address: Optional[str] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    country: Optional[str] = None
    industry: Optional[str] = None
    business_type: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    seo_score: Optional[int] = None
    lead_score: Optional[float] = None
    status_notes: Optional[str] = None
    source: Optional[str] = None
    hours: Optional[str] = None
    description: Optional[str] = None
    price_level: Optional[str] = None
    facebook: Optional[str] = None
    instagram: Optional[str] = None
    linkedin: Optional[str] = None
    twitter: Optional[str] = None
    tags: Optional[List[str]] = None


class LeadOut(BaseModel):
    id: UUID
    name: Optional[str] = None
    url: Optional[str] = None
    google_maps_url: Optional[str] = None
    address: Optional[str] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    country: Optional[str] = None
    industry: Optional[str] = None
    business_type: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    seo_score: Optional[int] = None
    hours: Optional[str] = None
    description: Optional[str] = None
    price_level: Optional[str] = None
    facebook: Optional[str] = None
    instagram: Optional[str] = None
    linkedin: Optional[str] = None
    twitter: Optional[str] = None
    tags: Optional[List[str]] = None
    research: Optional[dict] = None
    lead_score: Optional[float] = None
    status: Optional[str] = None
    status_notes: Optional[str] = None
    source: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class LeadDetailOut(LeadOut):
    events: List["LeadEventOut"] = Field(default_factory=list)


class LeadEventOut(BaseModel):
    id: UUID
    lead_id: UUID
    agent_run_id: Optional[UUID] = None
    event_type: str
    payload: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PipelineRunCreate(BaseModel):
    trigger: str = "api"
    seed_query: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None


class PipelineRunComplete(BaseModel):
    status: str = "success"
    meta: Optional[Dict[str, Any]] = None


class PipelineRunOut(BaseModel):
    id: UUID
    trigger: Optional[str] = None
    seed_query: Optional[str] = None
    status: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    meta: Optional[Dict[str, Any]] = None

    model_config = {"from_attributes": True}


class PipelineRunListOut(PipelineRunOut):
    agent_run_count: int = 0


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


class AgentRunCreate(BaseModel):
    pipeline_run_id: UUID
    agent_name: str
    model: Optional[str] = None
    input_summary: Optional[str] = None


class AgentRunComplete(BaseModel):
    status: str = "success"
    output_summary: Optional[str] = None
    output_json: Optional[Dict[str, Any]] = None
    apis_consumed: Optional[List[Dict[str, Any]]] = None
    records_processed: int = 0
    error_message: Optional[str] = None


class AgentRunOut(BaseModel):
    id: UUID
    pipeline_run_id: UUID
    agent_name: str
    model: Optional[str] = None
    status: Optional[str] = None
    input_summary: Optional[str] = None
    output_summary: Optional[str] = None
    output_json: Optional[Dict[str, Any]] = None
    apis_consumed: Optional[List[Dict[str, Any]]] = None
    records_processed: Optional[int] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ToolInfo(BaseModel):
    id: str
    label: str
    agents: List[str] = Field(default_factory=list)


class AgentProfileOut(BaseModel):
    agent_name: str
    display_name: str
    mission_prompt: Optional[str] = None
    enabled_tools: List[str] = Field(default_factory=list)
    model: Optional[str] = None
    default_seed_query: Optional[str] = None
    default_domain: Optional[str] = None
    updated_at: Optional[datetime] = None
    available_tools: List[ToolInfo] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class AgentProfileUpdate(BaseModel):
    display_name: Optional[str] = None
    mission_prompt: Optional[str] = None
    enabled_tools: Optional[List[str]] = None
    model: Optional[str] = None
    default_seed_query: Optional[str] = None
    default_domain: Optional[str] = None


class AgentSecretSet(BaseModel):
    kind: str
    name: str
    value: str


class AgentSecretOut(BaseModel):
    agent_name: str
    kind: str
    name: str
    fingerprint: Optional[str] = None


class ProviderInfo(BaseModel):
    kind: str
    name: Optional[str] = None
    has_key: bool
    fingerprint: Optional[str] = None


class LlmModelAlias(BaseModel):
    agent: str
    model: str


class LlmStatus(BaseModel):
    provider: str
    base_url: str
    api_key_set: bool
    models: List[LlmModelAlias]
    reachable: bool
    detail: str
    checked_at: str


class AgentMemoryIn(BaseModel):
    scope: str = "shared"
    key: str
    value: str


class ChunkIngestRequest(BaseModel):
    agent_name: str
    content: str
    scope: str = "shared"
    source_uri: Optional[str] = None


class ChunkSearchRequest(BaseModel):
    query: str
    scope: Optional[str] = None
    limit: int = 5


class ChunkOut(BaseModel):
    id: UUID
    agent_name: str
    scope: str
    source_uri: Optional[str] = None
    content: str
    similarity: Optional[float] = None
    created_at: Optional[datetime] = None


class DiscoveryStartRequest(BaseModel):
    seed_query: Optional[str] = Field(None, min_length=2)
    # None → Head decides the per-mission search budget.
    max_search_results: Optional[int] = Field(None, ge=1)
    mission: Optional[str] = None


class DiscoveryStartOut(BaseModel):
    pipeline_run_id: UUID
    status: str
    seed_query: str
    note: Optional[str] = (
        "Head will assign Discovery tools from the operator-allowed set, then scout runs."
    )


class DiscoveryFinishOut(BaseModel):
    pipeline_run_id: UUID
    status: str


class EnrichLeadsRequest(BaseModel):
    # Either explicit lead_ids, or a limit of the most recent leads.
    lead_ids: Optional[List[UUID]] = None
    limit: Optional[int] = Field(None, ge=1, le=1000)


class EnrichLeadsOut(BaseModel):
    pipeline_run_id: UUID
    status: str
    target_count: int


class BrainQueryRequest(BaseModel):
    agent_name: str
    domain: str
    query: str
    limit: int = 5


LeadDetailOut.model_rebuild()
