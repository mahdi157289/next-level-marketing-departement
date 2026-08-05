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
    country: Optional[str] = None
    industry: Optional[str] = None
    business_type: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    status_notes: Optional[str] = None


class LeadUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    status: Optional[str] = None
    country: Optional[str] = None
    industry: Optional[str] = None
    business_type: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    seo_score: Optional[int] = None
    lead_score: Optional[float] = None
    status_notes: Optional[str] = None
    source: Optional[str] = None


class LeadOut(BaseModel):
    id: UUID
    name: Optional[str] = None
    url: Optional[str] = None
    country: Optional[str] = None
    industry: Optional[str] = None
    business_type: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    seo_score: Optional[int] = None
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
    mission_prompt: str
    enabled_tools: List[str] = Field(default_factory=list)
    model: Optional[str] = None
    default_seed_query: Optional[str] = None
    updated_at: Optional[datetime] = None
    available_tools: List[ToolInfo] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class AgentProfileUpdate(BaseModel):
    display_name: Optional[str] = None
    mission_prompt: Optional[str] = None
    enabled_tools: Optional[List[str]] = None
    model: Optional[str] = None
    default_seed_query: Optional[str] = None


class DiscoveryStartRequest(BaseModel):
    seed_query: Optional[str] = Field(None, min_length=2)
    max_search_results: int = Field(5, ge=1)


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


LeadDetailOut.model_rebuild()
