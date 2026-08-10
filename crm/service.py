"""CRM business logic — no FastAPI imports."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select, text, delete
from sqlalchemy.orm import Session

from db.models import (
    AgentMemory,
    AgentProfile,
    AgentRun,
    AgentSecret,
    Lead,
    LeadEvent,
    LeadStatus,
    PipelineRun,
    RunStatus,
    ScoutMessage,
    ScoutThread,
)
from db.session import SessionLocal
from db.secrets import decrypt_secret, encrypt_secret
from tools.registry import TOOL_CATALOG, catalog_for_agent, validate_tool_ids
from crm.agents_registry import AGENT_ROSTER, roster_entry


def _session() -> Session:
    return SessionLocal()


def _enum_val(v: Any) -> Any:
    return v.value if hasattr(v, "value") else v


def _row_to_dict(row: Any) -> Dict[str, Any]:
    d = dict(row.__dict__)
    d.pop("_sa_instance_state", None)
    for k, v in list(d.items()):
        if hasattr(v, "value"):
            d[k] = v.value
    return d


# Fields a lead-completion agent can fill using tools + existing fields.
FILLABLE_FIELDS: tuple = (
    "google_maps_url", "address", "rating", "review_count",
    "country", "industry", "business_type", "email", "phone", "seo_score",
    "hours", "description", "price_level", "facebook", "instagram",
    "linkedin", "twitter", "tags",
)


def _is_empty(value: Any) -> bool:
    """True when a field has no usable data (None/''/[]/{} or zero)."""
    if value is None:
        return True
    if isinstance(value, (list, dict)) and not value:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if value == 0:
        return True
    return False


def lead_gaps(lead: Dict[str, Any]) -> List[str]:
    """List FILLABLE_FIELDS that are currently empty on a lead."""
    return [f for f in FILLABLE_FIELDS if _is_empty(lead.get(f))]


# --- Leads ---


def list_leads(status: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    session = _session()
    try:
        q = select(Lead).order_by(Lead.created_at.desc()).limit(limit)
        if status:
            q = q.where(Lead.status == LeadStatus(status))
        rows = session.scalars(q).all()
        return [_row_to_dict(r) for r in rows]
    finally:
        session.close()


def get_lead(lead_id: str) -> Optional[Dict[str, Any]]:
    session = _session()
    try:
        lead = session.get(Lead, uuid.UUID(lead_id))
        if not lead:
            return None
        out = _row_to_dict(lead)
        events = session.scalars(
            select(LeadEvent).where(LeadEvent.lead_id == lead.id).order_by(LeadEvent.created_at.desc()).limit(50)
        ).all()
        out["events"] = [_row_to_dict(e) for e in events]
        return out
    finally:
        session.close()


def create_lead(data: Dict[str, Any], agent_run_id: Optional[str] = None) -> Dict[str, Any]:
    session = _session()
    try:
        existing = session.scalars(select(Lead).where(Lead.url == data["url"])).first()
        if existing:
            out = _row_to_dict(existing)
            out["created"] = False
            return out
        lead = Lead(
            id=uuid.uuid4(),
            name=data.get("name"),
            url=data["url"],
            google_maps_url=data.get("google_maps_url"),
            address=data.get("address"),
            rating=data.get("rating"),
            review_count=data.get("review_count"),
            status=LeadStatus(data.get("status", "raw")),
            source=data.get("source", "discovery"),
            country=data.get("country"),
            industry=data.get("industry"),
            business_type=data.get("business_type"),
            email=data.get("email"),
            phone=data.get("phone"),
            status_notes=data.get("status_notes"),
            hours=data.get("hours"),
            description=data.get("description"),
            price_level=data.get("price_level"),
            facebook=data.get("facebook"),
            instagram=data.get("instagram"),
            linkedin=data.get("linkedin"),
            twitter=data.get("twitter"),
            tags=data.get("tags"),
        )
        session.add(lead)
        session.flush()
        if agent_run_id:
            session.add(
                LeadEvent(
                    id=uuid.uuid4(),
                    lead_id=lead.id,
                    agent_run_id=uuid.UUID(agent_run_id),
                    event_type="created",
                    payload={"source": lead.source},
                )
            )
        session.commit()
        session.refresh(lead)
        out = _row_to_dict(lead)
        out["created"] = True
        return out
    finally:
        session.close()


def _to_rating(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return round(float(str(value).strip()), 2)
    except (TypeError, ValueError):
        return None


def _to_review_count(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(str(value).strip().replace(",", ""))
    except (TypeError, ValueError):
        return None


def create_lead_from_search_hit(hit: Dict[str, str], agent_run_id: Optional[str] = None) -> Dict[str, Any]:
    url = (hit.get("url") or "").strip()
    if not url or not url.startswith("http"):
        return {}
    title = (hit.get("title") or url)[:256]
    snippet = (hit.get("snippet") or "")[:500]
    lead = create_lead(
        {
            "name": title,
            "url": url,
            "status": "raw",
            "source": "discovery",
            "status_notes": snippet or None,
            "google_maps_url": _clean_field(hit.get("google_maps_url")),
            "address": _clean_field(hit.get("address")),
            "rating": _to_rating(hit.get("rating")),
            "review_count": _to_review_count(hit.get("review_count")),
            "phone": _clean_field(hit.get("phone")),
            "email": _clean_field(hit.get("email")),
            "industry": _clean_field(hit.get("category")),
            "country": _infer_country(hit),
            "business_type": _clean_field(hit.get("business_type")),
            "hours": _clean_field(hit.get("hours")),
            "description": _clean_field(hit.get("description")),
            "price_level": _clean_field(hit.get("price_level")),
            "facebook": _clean_field(hit.get("facebook")),
            "instagram": _clean_field(hit.get("instagram")),
            "linkedin": _clean_field(hit.get("linkedin")),
            "twitter": _clean_field(hit.get("twitter")),
            "tags": _clean_tags(hit.get("tags")),
        },
        agent_run_id=agent_run_id,
    )
    if lead.get("created"):
        return lead
    # Re-discovery of an existing lead: persist any newly found structured fields.
    structured = {
        "google_maps_url": _clean_field(hit.get("google_maps_url")),
        "address": _clean_field(hit.get("address")),
        "rating": _to_rating(hit.get("rating")),
        "review_count": _to_review_count(hit.get("review_count")),
        "phone": _clean_field(hit.get("phone")),
        "email": _clean_field(hit.get("email")),
        "industry": _clean_field(hit.get("category")),
        "country": _infer_country(hit),
        "business_type": _clean_field(hit.get("business_type")),
        "hours": _clean_field(hit.get("hours")),
        "description": _clean_field(hit.get("description")),
        "price_level": _clean_field(hit.get("price_level")),
        "facebook": _clean_field(hit.get("facebook")),
        "instagram": _clean_field(hit.get("instagram")),
        "linkedin": _clean_field(hit.get("linkedin")),
        "twitter": _clean_field(hit.get("twitter")),
        "tags": _clean_tags(hit.get("tags")),
    }
    structured = {k: v for k, v in structured.items() if v}
    if structured:
        enrich_lead(str(lead["id"]), structured, agent_run_id=agent_run_id)
        lead = get_lead(str(lead["id"])) or lead
        lead["created"] = False
    return lead


def _clean_field(value: Any) -> Optional[str]:
    if not value:
        return None
    s = str(value).strip()
    if not s or s.lower() in ("n/a", "none", "unknown"):
        return None
    return s[:256]


def _clean_tags(value: Any) -> Optional[List[str]]:
    if not isinstance(value, list):
        return None
    out: List[str] = []
    for item in value:
        s = _clean_field(item)
        if s:
            out.append(s)
    return out[:20] if out else None


_COUNTRY_HINTS = ("tunisie", "tunisia", "tunis")


def _infer_country(hit: Dict[str, Any]) -> Optional[str]:
    """Country from hit.country, else the address tail, else the URL TLD."""
    c = _clean_field(hit.get("country"))
    if c:
        return c
    address = _clean_field(hit.get("address"))
    if address:
        tail = address.split(",")[-1].strip().lower()
        if any(hint in tail for hint in _COUNTRY_HINTS):
            return "Tunisia"
        if "google.com/maps" in (hit.get("url") or "").lower():
            # Maps hits come from a Tunisia-scoped place search (region="Tunisia").
            return "Tunisia"
    url = (hit.get("url") or "").lower()
    if url.startswith("http"):
        host = url.split("/")[2].split(":")[0].split("?")[0]
        if host.endswith(".tn"):
            return "Tunisia"
    return None


def enrich_lead(lead_id: str, data: Dict[str, Any], agent_run_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Persist enriched fields on a lead and bump status raw → enriched when new data lands.

    Records a LeadEvent per enrichment so the CRM shows the data flowing in.
    """
    session = _session()
    try:
        lead = session.get(Lead, uuid.UUID(lead_id))
        if not lead:
            return None
        updated_fields: List[str] = []
        for key in (
            "email", "phone", "industry", "country", "business_type", "seo_score",
            "address", "google_maps_url", "rating", "review_count",
            "hours", "description", "price_level", "facebook", "instagram",
            "linkedin", "twitter", "tags", "research",
        ):
            if key not in data or data[key] is None:
                continue
            val = data[key]
            if key == "rating":
                val = _to_rating(val)
            elif key == "review_count":
                val = _to_review_count(val)
            elif key == "research":
                val = val if isinstance(val, dict) else None
            elif key == "tags":
                val = val if isinstance(val, list) else None
            elif key != "seo_score":
                val = _clean_field(val)
            if val is None:
                continue
            if getattr(lead, key) == val:
                continue
            setattr(lead, key, val)
            updated_fields.append(key)
        if not updated_fields:
            return _row_to_dict(lead)

        old_status = _enum_val(lead.status)
        if old_status != "enriched" and old_status in ("raw", "categorized"):
            lead.status = LeadStatus.enriched
            if agent_run_id:
                session.add(
                    LeadEvent(
                        id=uuid.uuid4(),
                        lead_id=lead.id,
                        agent_run_id=uuid.UUID(agent_run_id),
                        event_type="status_changed",
                        payload={"field": "status", "old": old_status, "new": "enriched"},
                    )
                )
        if agent_run_id:
            session.add(
                LeadEvent(
                    id=uuid.uuid4(),
                    lead_id=lead.id,
                    agent_run_id=uuid.UUID(agent_run_id),
                    event_type="enriched",
                    payload={"fields": updated_fields},
                )
            )
        lead.updated_at = datetime.utcnow()
        session.commit()
        session.refresh(lead)
        return _row_to_dict(lead)
    finally:
        session.close()


def enrich_missing(lead_id: str, data: Dict[str, Any], agent_run_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Fill only currently-empty fields on a lead.

    Unlike ``enrich_lead`` (which overwrites differing values), this never
    regresses existing data — it drops values for any field already populated.
    Used by the Lead Completion Agent so re-scrapes can't clobber good data.
    """
    lead = get_lead(lead_id)
    if not lead:
        return None
    filtered = {
        k: v for k, v in (data or {}).items()
        if v is not None and _is_empty(lead.get(k))
    }
    if not filtered:
        return lead
    return enrich_lead(lead_id, filtered, agent_run_id=agent_run_id)


def update_lead(lead_id: str, data: Dict[str, Any], agent_run_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    session = _session()
    try:
        lead = session.get(Lead, uuid.UUID(lead_id))
        if not lead:
            return None
        for key, val in data.items():
            if val is None or not hasattr(lead, key):
                continue
            if key == "status":
                old = _enum_val(lead.status)
                setattr(lead, key, LeadStatus(val))
                if agent_run_id and old != val:
                    session.add(
                        LeadEvent(
                            id=uuid.uuid4(),
                            lead_id=lead.id,
                            agent_run_id=uuid.UUID(agent_run_id),
                            event_type="status_changed",
                            payload={"field": "status", "old": old, "new": val},
                        )
                    )
            else:
                setattr(lead, key, val)
        lead.updated_at = datetime.utcnow()
        session.commit()
        session.refresh(lead)
        return _row_to_dict(lead)
    finally:
        session.close()


# --- Pipeline runs ---


def start_pipeline_run(trigger: str, seed_query: Optional[str], meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    session = _session()
    try:
        run = PipelineRun(
            id=uuid.uuid4(),
            trigger=trigger,
            seed_query=seed_query,
            status=RunStatus.running,
            meta=meta or {},
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        return _row_to_dict(run)
    finally:
        session.close()


def dispatch_agent_task(
    agent_name: str, seed_query: Optional[str], mission: Optional[str] = None
) -> Dict[str, Any]:
    """Dispatch a task to an agent via the pipeline runner (generic, agent-agnostic).

    Persists a PipelineRun with meta={mission, from_agent:<name>} so the operator
    and the Head Agent UI can inspect what was dispatched. Sub-agents that need
    live execution (e.g. Discovery) dispatch via their dedicated start endpoint
    (crm.router / runners), which also records to this run id.
    """
    if not get_agent_profile(agent_name):
        raise ValueError(f"Unknown agent: {agent_name}")
    return start_pipeline_run(
        trigger=f"agent:{agent_name}",
        seed_query=seed_query,
        meta={"mission": mission or "", "from_agent": agent_name, "mode": "dispatch"},
    )


def complete_pipeline_run(
    run_id: str,
    status: str = "success",
    meta: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    session = _session()
    try:
        run = session.get(PipelineRun, uuid.UUID(run_id))
        if not run:
            return None
        run.status = RunStatus(status)
        run.finished_at = datetime.utcnow()
        if meta:
            run.meta = {**(run.meta or {}), **meta}
        session.commit()
        session.refresh(run)
        return _row_to_dict(run)
    finally:
        session.close()


def merge_pipeline_meta(run_id: str, meta: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Merge keys into pipeline_runs.meta without changing status/finished_at."""
    session = _session()
    try:
        run = session.get(PipelineRun, uuid.UUID(run_id))
        if not run:
            return None
        run.meta = {**(run.meta or {}), **meta}
        session.commit()
        session.refresh(run)
        return _row_to_dict(run)
    finally:
        session.close()


def latest_head_assignment() -> Optional[Dict[str, Any]]:
    session = _session()
    try:
        rows = session.scalars(
            select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(20)
        ).all()
        for row in rows:
            meta = row.meta or {}
            if meta.get("head_assignment"):
                return meta["head_assignment"]
        return None
    finally:
        session.close()


def list_pipeline_runs(limit: int = 50) -> List[Dict[str, Any]]:
    session = _session()
    try:
        rows = session.scalars(
            select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(limit)
        ).all()
        out: List[Dict[str, Any]] = []
        for r in rows:
            d = _row_to_dict(r)
            n = session.scalar(
                select(func.count())
                .select_from(AgentRun)
                .where(AgentRun.pipeline_run_id == r.id)
            )
            d["agent_run_count"] = int(n or 0)
            out.append(d)
        return out
    finally:
        session.close()


def compute_stats() -> Dict[str, Any]:
    session = _session()
    try:
        today = datetime.utcnow().date()
        start_today = datetime(today.year, today.month, today.day)
        leads_total = session.scalar(select(func.count()).select_from(Lead)) or 0
        leads_by_status: Dict[str, int] = {}
        for st in LeadStatus:
            leads_by_status[st.value] = 0
        for (status, cnt) in session.execute(
            select(Lead.status, func.count()).group_by(Lead.status)
        ):
            leads_by_status[_enum_val(status)] = int(cnt)
        avg_score = session.scalar(select(func.avg(Lead.lead_score))) or 0.0
        runs_today = (
            session.scalar(
                select(func.count()).select_from(PipelineRun).where(PipelineRun.started_at >= start_today)
            )
            or 0
        )
        total_runs = session.scalar(select(func.count()).select_from(PipelineRun)) or 0
        success_runs = (
            session.scalar(
                select(func.count())
                .select_from(PipelineRun)
                .where(PipelineRun.status == RunStatus.success)
            )
            or 0
        )
        run_success_rate = round((success_runs / total_runs * 100.0) if total_runs else 0.0, 1)
        recent_rows = session.scalars(
            select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(5)
        ).all()
        recent_runs = [
            {
                "id": str(r.id),
                "trigger": r.trigger,
                "seed_query": r.seed_query,
                "status": _enum_val(r.status),
                "started_at": _iso_str(r.started_at),
            }
            for r in recent_rows
        ]
        active, seed = _scout_status()
        return {
            "leads_total": int(leads_total),
            "leads_by_status": leads_by_status,
            "leads_avg_score": round(float(avg_score or 0.0), 1),
            "runs_today": int(runs_today),
            "run_success_rate": run_success_rate,
            "recent_runs": recent_runs,
            "scout_active": active,
            "scout_last_seed": seed,
        }
    finally:
        session.close()


def _iso_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%dT%H:%M:%SZ")
    return str(v)


def _scout_status() -> tuple:
    try:
        from crm import runner

        active = runner.get_active()
        if active:
            return True, active.get("seed_query")
    except Exception:
        pass
    return False, None


# --- Agent runs ---


def start_agent_run(
    pipeline_run_id: str,
    agent_name: str,
    model: Optional[str] = None,
    input_summary: Optional[str] = None,
) -> Dict[str, Any]:
    session = _session()
    try:
        run = AgentRun(
            id=uuid.uuid4(),
            pipeline_run_id=uuid.UUID(pipeline_run_id),
            agent_name=agent_name,
            model=model,
            status=RunStatus.running,
            input_summary=input_summary,
            apis_consumed=[],
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        return _row_to_dict(run)
    finally:
        session.close()


def complete_agent_run(
    run_id: str,
    status: str = "success",
    output_summary: Optional[str] = None,
    output_json: Optional[Dict[str, Any]] = None,
    apis_consumed: Optional[List[Dict[str, Any]]] = None,
    records_processed: int = 0,
    error_message: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    session = _session()
    try:
        run = session.get(AgentRun, uuid.UUID(run_id))
        if not run:
            return None
        run.status = RunStatus(status)
        run.finished_at = datetime.utcnow()
        run.output_summary = output_summary
        run.output_json = output_json
        if apis_consumed is not None:
            run.apis_consumed = apis_consumed
        run.records_processed = records_processed
        run.error_message = error_message
        session.commit()
        session.refresh(run)
        return _row_to_dict(run)
    finally:
        session.close()


def list_agent_runs(
    agent_name: Optional[str] = None,
    pipeline_run_id: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    session = _session()
    try:
        q = select(AgentRun).order_by(AgentRun.started_at.desc()).limit(limit)
        if agent_name:
            q = q.where(AgentRun.agent_name == agent_name)
        if pipeline_run_id:
            q = q.where(AgentRun.pipeline_run_id == uuid.UUID(pipeline_run_id))
        rows = session.scalars(q).all()
        return [_row_to_dict(r) for r in rows]
    finally:
        session.close()


def get_agent_run(run_id: str) -> Optional[Dict[str, Any]]:
    session = _session()
    try:
        run = session.get(AgentRun, uuid.UUID(run_id))
        if not run:
            return None
        return _row_to_dict(run)
    finally:
        session.close()


def get_pipeline_run(run_id: str) -> Optional[Dict[str, Any]]:
    session = _session()
    try:
        run = session.get(PipelineRun, uuid.UUID(run_id))
        if not run:
            return None
        return _row_to_dict(run)
    finally:
        session.close()


# --- Agent profiles ---


def _profile_from_roster(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "agent_name": entry["name"],
        "display_name": entry["display_name"],
        "mission_prompt": None,
        "enabled_tools": list(entry["default_tools"]),
        "model": None,
        "default_seed_query": None,
        "default_domain": None,
        "updated_at": None,
        "available_tools": catalog_for_agent(entry["name"]),
    }


def list_agent_profiles() -> List[Dict[str, Any]]:
    session = _session()
    try:
        rows = session.scalars(select(AgentProfile).order_by(AgentProfile.agent_name)).all()
        seen = set()
        out = []
        for r in rows:
            seen.add(r.agent_name)
            d = _row_to_dict(r)
            d["available_tools"] = catalog_for_agent(r.agent_name)
            out.append(d)
        for entry in AGENT_ROSTER:
            if entry["name"] not in seen:
                out.append(_profile_from_roster(entry))
        return out
    finally:
        session.close()


def get_agent_profile(agent_name: str) -> Optional[Dict[str, Any]]:
    session = _session()
    try:
        row = session.get(AgentProfile, agent_name)
        if row:
            d = _row_to_dict(row)
            d["available_tools"] = catalog_for_agent(agent_name)
            return d
    finally:
        session.close()
    entry = roster_entry(agent_name)
    if not entry:
        return None
    return _profile_from_roster(entry)


def update_agent_profile(agent_name: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    session = _session()
    try:
        row = session.get(AgentProfile, agent_name)
        if not row:
            entry = roster_entry(agent_name)
            if not entry:
                return None
            row = AgentProfile(
                agent_name=agent_name,
                display_name=entry["display_name"],
                mission_prompt="",
                enabled_tools=list(entry["default_tools"]),
            )
            session.add(row)
        if "display_name" in data and data["display_name"] is not None:
            row.display_name = data["display_name"]
        if "mission_prompt" in data and data["mission_prompt"] is not None:
            row.mission_prompt = data["mission_prompt"]
        if "enabled_tools" in data and data["enabled_tools"] is not None:
            row.enabled_tools = validate_tool_ids(data["enabled_tools"], agent_name=agent_name)
        if "model" in data:
            row.model = data["model"]
        if "default_seed_query" in data:
            row.default_seed_query = data["default_seed_query"]
        if "default_domain" in data:
            row.default_domain = ((data["default_domain"] or "").strip() or None)
        row.updated_at = datetime.utcnow()
        session.commit()
        session.refresh(row)
        d = _row_to_dict(row)
        d["available_tools"] = catalog_for_agent(agent_name)
        return d
    finally:
        session.close()


# --- Scout chat ---


def create_scout_thread(
    title: Optional[str] = None, agent_name: str = "discovery"
) -> Dict[str, Any]:
    session = _session()
    try:
        thread = ScoutThread(
            id=uuid.uuid4(),
            title=title or "New scout thread",
            agent_name=agent_name,
        )
        session.add(thread)
        session.commit()
        session.refresh(thread)
        return _row_to_dict(thread)
    finally:
        session.close()


def list_scout_threads(agent_name: str = "discovery", limit: int = 50) -> List[Dict[str, Any]]:
    session = _session()
    try:
        rows = session.scalars(
            select(ScoutThread)
            .where(ScoutThread.agent_name == agent_name)
            .order_by(ScoutThread.created_at.desc())
            .limit(limit)
        ).all()
        return [_row_to_dict(r) for r in rows]
    finally:
        session.close()


def add_scout_message(
    thread_id: str,
    role: str,
    content: Optional[str] = None,
    tool_name: Optional[str] = None,
    tool_args: Optional[Dict[str, Any]] = None,
    tool_result: Optional[Any] = None,
    agent_name: str = "discovery",
) -> Dict[str, Any]:
    session = _session()
    try:
        msg = ScoutMessage(
            id=uuid.uuid4(),
            thread_id=uuid.UUID(thread_id),
            role=role,
            content=content,
            tool_name=tool_name,
            tool_args=tool_args,
            tool_result=tool_result,
            agent_name=agent_name,
        )
        session.add(msg)
        session.commit()
        session.refresh(msg)
        return _row_to_dict(msg)
    finally:
        session.close()


def list_scout_messages(thread_id: str, limit: int = 200) -> List[Dict[str, Any]]:
    session = _session()
    try:
        rows = session.scalars(
            select(ScoutMessage)
            .where(ScoutMessage.thread_id == uuid.UUID(thread_id))
            .order_by(ScoutMessage.created_at.asc())
            .limit(limit)
        ).all()
        return [_row_to_dict(r) for r in rows]
    finally:
        session.close()


# --- Agent secrets (encrypted store) ---


def set_agent_secret(agent_name: str, kind: str, name: str, value: str) -> Dict[str, Any]:
    """Create or replace an encrypted secret for (agent, provider)."""
    session = _session()
    try:
        row = session.get(AgentSecret, (agent_name, kind))
        if not row:
            row = AgentSecret(agent_name=agent_name, kind=kind, name=name, value=encrypt_secret(value))
            session.add(row)
        else:
            row.name = name
            row.value = encrypt_secret(value)
        row.updated_at = datetime.utcnow()
        session.commit()
        session.refresh(row)
        return {"agent_name": row.agent_name, "kind": row.kind, "name": row.name}
    finally:
        session.close()


def list_agent_secrets(agent_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """List secret metadata plus a short fingerprint (sha256 of the token).

    Fingerprints let operators confirm *which* key is set without exposing it.
    The raw encrypted value is never returned.
    """
    session = _session()
    try:
        q = select(AgentSecret)
        if agent_name:
            q = q.where(AgentSecret.agent_name == agent_name)
        q = q.order_by(AgentSecret.agent_name, AgentSecret.kind)
        rows = session.scalars(q).all()
        out = []
        for r in rows:
            out.append(
                {
                    "agent_name": r.agent_name,
                    "kind": r.kind,
                    "name": r.name,
                    "fingerprint": _fingerprint(decrypt_secret(r.value) or ""),
                }
            )
        return out
    finally:
        session.close()


def _fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:8]


# Known provider "kinds" operators can configure per agent.
KNOWN_PROVIDERS: List[str] = ["openai", "serpapi", "google_maps", "meta_ads"]


def list_providers(agent_name: str) -> List[Dict[str, Any]]:
    """Providers for an agent with has_key + fingerprint (no raw tokens)."""
    secrets = {s["kind"]: s for s in list_agent_secrets(agent_name)}
    out: List[Dict[str, Any]] = []
    for kind in KNOWN_PROVIDERS:
        sec = secrets.get(kind)
        out.append(
            {
                "kind": kind,
                "name": sec["name"] if sec else None,
                "has_key": sec is not None,
                "fingerprint": sec["fingerprint"] if sec else None,
            }
        )
    return out


def delete_agent_secret(agent_name: str, kind: str) -> bool:
    session = _session()
    try:
        row = session.get(AgentSecret, (agent_name, kind))
        if not row:
            return False
        session.delete(row)
        session.commit()
        return True
    finally:
        session.close()


def get_secret_name(agent_name: str, kind: str) -> Optional[str]:
    session = _session()
    try:
        row = session.get(AgentSecret, (agent_name, kind))
        return row.name if row else None
    finally:
        session.close()


def resolve_agent_secret(agent_name: str, kind: str) -> Optional[str]:
    """Return the decrypted secret value for a (agent, provider), or None."""
    session = _session()
    try:
        row = session.get(AgentSecret, (agent_name, kind))
        if not row:
            return None
        return decrypt_secret(row.value)
    finally:
        session.close()


def resolved_agent_profile(agent_name: str) -> Optional[Dict[str, Any]]:
    """Agent profile with resolved provider secrets injected (no tokens returned)."""
    profile = get_agent_profile(agent_name)
    if not profile:
        return None
    profile["secrets"] = [
        {"kind": s["kind"], "name": s["name"]} for s in list_agent_secrets(agent_name)
    ]
    return profile


# --- Agent memory (persistent, scoped) ---


def add_memory(agent_name: str, scope: str, key: str, value: str) -> Dict[str, Any]:
    session = _session()
    try:
        row = AgentMemory(agent_name=agent_name, scope=scope, key=key, value=value)
        session.add(row)
        session.commit()
        session.refresh(row)
        return _row_to_dict(row)
    finally:
        session.close()


def list_memory(agent_name: str, scope: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    session = _session()
    try:
        q = select(AgentMemory).where(AgentMemory.agent_name == agent_name)
        if scope:
            q = q.where(AgentMemory.scope == scope)
        q = q.order_by(AgentMemory.created_at.desc()).limit(limit)
        rows = session.scalars(q).all()
        return [_row_to_dict(r) for r in rows]
    finally:
        session.close()


def clear_memory(agent_name: str, scope: Optional[str] = None) -> int:
    """Remove matching memory rows; returns deleted count."""
    session = _session()
    try:
        q = delete(AgentMemory).where(AgentMemory.agent_name == agent_name)
        if scope:
            q = q.where(AgentMemory.scope == scope)
        count = int(session.execute(q).rowcount or 0)
        session.commit()
        return count
    finally:
        session.close()


# --- RAG vector store (P3) ---


def ingest_chunk(agent_name: str, content: str, scope: str = "shared", source_uri: Optional[str] = None) -> Dict[str, Any]:
    from db.embeddings import insert_chunk

    return insert_chunk(agent_name, content, scope=scope, source_uri=source_uri)


def search_chunks(agent_name: str, query: str, scope: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
    from db.embeddings import search_chunks as _search

    return _search(agent_name, query, scope=scope, limit=limit)


def tools_catalog() -> List[Dict[str, Any]]:
    return list(TOOL_CATALOG)


def llm_status() -> Dict[str, Any]:
    """LLM runtime info for the SPA status pill/drawer — never returns the API key."""
    from config.settings import get_settings
    from agents.lm_client import ensure_llm_reachable

    s = get_settings()
    base = s.openai_base_url().lower()
    if s.openai_api_base:
        if "openrouter" in base:
            provider = "OpenRouter"
        elif ":4000" in base or "litellm" in base:
            provider = "LiteLLM"
        else:
            provider = "OpenAI-compatible"
    else:
        provider = "LM Studio (local)"

    reachable, detail = ensure_llm_reachable()

    return {
        "provider": provider,
        "base_url": s.openai_base_url(),
        "api_key_set": bool(s.openai_api_key) and s.openai_api_key != "lm-studio",
        "models": [
            {"agent": "discovery", "model": s.agent_model_discovery},
            {"agent": "head", "model": s.agent_model_head},
        ],
        "reachable": reachable,
        "detail": detail,
        "checked_at": datetime.now().isoformat(),
    }


def health_check() -> Dict[str, str]:
    session = _session()
    try:
        session.execute(text("SELECT 1"))
        return {"status": "ok", "module": "crm"}
    finally:
        session.close()
