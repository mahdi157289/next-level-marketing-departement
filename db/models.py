import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, Enum, Float, Index, Integer, String, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class LeadStatus(str, enum.Enum):
    raw = "raw"
    categorized = "categorized"
    enriched = "enriched"
    contacted = "contacted"
    converted = "converted"
    unreachable = "unreachable"
    low_priority = "low_priority"


_lead_status_pg = Enum(
    LeadStatus,
    name="leadstatus",
    values_callable=lambda obj: [e.value for e in obj],
)


class Lead(Base):
    __tablename__ = "leads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(256))
    url = Column(String(512), unique=True)
    country = Column(String(64))
    industry = Column(String(128))
    business_type = Column(String(64))
    email = Column(String(256))
    phone = Column(String(64))
    seo_score = Column(Integer)
    automation_gaps = Column(JSON)
    social_engagement = Column(JSON)
    weaknesses = Column(JSON)
    lead_score = Column(Float, default=0.0)
    status = Column(_lead_status_pg, default=LeadStatus.raw)
    status_notes = Column(Text)
    source = Column(String(64))
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)


class OutreachRecord(Base):
    __tablename__ = "outreach_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id = Column(UUID(as_uuid=True), nullable=False)
    channel = Column(String(32))
    to_address = Column(String(256))
    subject = Column(String(512))
    message_text = Column(Text)
    sent_at = Column(TIMESTAMP)
    opened = Column(Boolean, default=False)
    replied = Column(Boolean, default=False)
    converted = Column(Boolean, default=False)


class CompanyKnowledge(Base):
    __tablename__ = "company_knowledge"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type = Column(String(32))
    title = Column(String(256))
    content = Column(Text)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)


class CampaignMetric(Base):
    __tablename__ = "campaign_metrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    date = Column(TIMESTAMP, default=datetime.utcnow)
    open_rate = Column(Float)
    reply_rate = Column(Float)
    conversion_rate = Column(Float)
    top_segment = Column(JSON)
    strategy_notes = Column(Text)


class TaskLog(Base):
    __tablename__ = "task_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_name = Column(String(64))
    task_id = Column(String(128))
    started_at = Column(TIMESTAMP)
    finished_at = Column(TIMESTAMP)
    status = Column(String(16))
    records_processed = Column(Integer)
    error_message = Column(Text)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)


class RunStatus(str, enum.Enum):
    running = "running"
    success = "success"
    failed = "failed"
    cancelled = "cancelled"


_run_status_pg = Enum(
    RunStatus,
    name="runstatus",
    values_callable=lambda obj: [e.value for e in obj],
)


class AgentProfile(Base):
    """Editable CRM agent config — mission prompt + enabled tools drive live runs."""

    __tablename__ = "agent_profiles"

    agent_name = Column(String(64), primary_key=True)
    display_name = Column(String(128), nullable=False)
    mission_prompt = Column(Text, nullable=False)
    enabled_tools = Column(JSON, nullable=False, default=list)
    model = Column(String(128))
    default_seed_query = Column(Text)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)


class AgentSecret(Base):
    """Encrypted provider/API-key secrets scoped per agent + provider.

    ``kind`` is the logical provider (e.g. ``openai``, ``serpapi``); ``name`` is
    a human label (e.g. ``OPENAI_API_KEY``). Secrets at rest are Fernet tokens;
    ``decrypt_secret`` is used by the provider loader.
    """

    __tablename__ = "agent_secrets"

    agent_name = Column(String(64), primary_key=True)
    kind = Column(String(64), primary_key=True)
    name = Column(String(128), nullable=False)
    value = Column("value", Text, nullable=False)  # stores Fernet token
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)


class AgentMemory(Base):
    """Per-agent persistent memory — one row per recalled fact / lesson.

    ``scope`` partitions memory (e.g. ``campaign:<id>``, ``domain``,
    ``shared``). Queries scoped to a domain read only the matching scopes.
    """

    __tablename__ = "agent_memory"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_name = Column(String(64), nullable=False)
    scope = Column(String(128), nullable=False, default="shared")
    key = Column(String(256), nullable=False)
    value = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_agent_memory_agent_scope", "agent_name", "scope"),
    )


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trigger = Column(String(32), default="api")
    seed_query = Column(Text)
    status = Column(_run_status_pg, default=RunStatus.running)
    started_at = Column(TIMESTAMP, default=datetime.utcnow)
    finished_at = Column(TIMESTAMP)
    meta = Column(JSON)


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pipeline_run_id = Column(UUID(as_uuid=True), nullable=False)
    agent_name = Column(String(64), nullable=False)
    model = Column(String(128))
    status = Column(_run_status_pg, default=RunStatus.running)
    input_summary = Column(Text)
    output_summary = Column(Text)
    output_json = Column(JSON)
    apis_consumed = Column(JSON)
    records_processed = Column(Integer, default=0)
    error_message = Column(Text)
    started_at = Column(TIMESTAMP, default=datetime.utcnow)
    finished_at = Column(TIMESTAMP)


class LeadEvent(Base):
    __tablename__ = "lead_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id = Column(UUID(as_uuid=True), nullable=False)
    agent_run_id = Column(UUID(as_uuid=True))
    event_type = Column(String(32), nullable=False)
    payload = Column(JSON)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)


class ScoutThread(Base):
    __tablename__ = "scout_threads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(Text)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)


class ScoutMessage(Base):
    __tablename__ = "scout_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id = Column(UUID(as_uuid=True), nullable=False)
    role = Column(String(16), nullable=False)
    content = Column(Text)
    tool_name = Column(String(64))
    tool_args = Column(JSON)
    tool_result = Column(JSON)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
