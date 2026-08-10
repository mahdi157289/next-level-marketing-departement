"""Jinja2 UI for the CRM module.

Pages:
  /crm/ui             -> redirect to /crm/ui/leads
  /crm/ui/leads       -> table of leads
  /crm/ui/leads/{id}  -> lead detail
  /crm/ui/runs        -> table of agent runs
  /crm/ui/runs/{id}   -> agent run detail
  /crm/ui/agents      -> agent roster
  /crm/ui/agents/{name} -> edit mission/tools; Discovery Start/Finish
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from crm import service

router = APIRouter(tags=["crm-ui"])

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def _iso(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, str):
        return v
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return str(v)


def _duration_ms(row: Dict[str, Any]) -> str:
    start = row.get("started_at")
    end = row.get("finished_at")
    if not start or not end:
        return "—"
    if isinstance(start, str):
        start = datetime.fromisoformat(start)
    if isinstance(end, str):
        end = datetime.fromisoformat(end)
    delta = (end - start).total_seconds()
    if delta < 1.0:
        return f"{int(delta * 1000)} ms"
    return f"{delta:.2f} s"


def _apis_short(apis: List[Dict[str, Any]] | None) -> str:
    if not apis:
        return "—"
    seen: List[str] = []
    for entry in apis:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if name and name not in seen:
            seen.append(name)
    return ", ".join(seen) if seen else "—"


def _decorate_run(row: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(row)
    out["duration"] = _duration_ms(row)
    out["apis_short"] = _apis_short(row.get("apis_consumed"))
    out["started_at"] = _iso(row.get("started_at"))
    out["finished_at"] = _iso(row.get("finished_at"))
    return out


templates.env.filters["iso"] = _iso


@router.get("/ui", include_in_schema=False)
def ui_index():
    return RedirectResponse(url="/crm/ui/leads", status_code=307)


@router.get("/ui/leads", response_class=HTMLResponse)
def ui_leads(request: Request):
    rows = service.list_leads(limit=200)
    for r in rows:
        r["created_at"] = _iso(r.get("created_at"))
        r["updated_at"] = _iso(r.get("updated_at"))
    return templates.TemplateResponse(
        request,
        "leads.html",
        {"leads": rows},
    )


@router.get("/ui/leads/{lead_id}", response_class=HTMLResponse)
def ui_lead_detail(lead_id: UUID, request: Request):
    row = service.get_lead(str(lead_id))
    if not row:
        raise HTTPException(status_code=404, detail="Lead not found")
    row["created_at"] = _iso(row.get("created_at"))
    row["updated_at"] = _iso(row.get("updated_at"))
    events = row.get("events") or []
    for e in events:
        e["created_at"] = _iso(e.get("created_at"))
    return templates.TemplateResponse(
        request,
        "lead_detail.html",
        {"lead": row, "events": events},
    )


@router.get("/ui/runs", response_class=HTMLResponse)
def ui_runs(request: Request):
    rows = [r for r in (service.list_agent_runs(limit=200) or [])]
    decorated = [_decorate_run(r) for r in rows]
    return templates.TemplateResponse(
        request,
        "runs.html",
        {"runs": decorated},
    )


@router.get("/ui/runs/{run_id}", response_class=HTMLResponse)
def ui_run_detail(run_id: UUID, request: Request):
    row = service.get_agent_run(str(run_id))
    if not row:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return templates.TemplateResponse(
        request,
        "run_detail.html",
        {"run": _decorate_run(row)},
    )


@router.get("/ui/agents", response_class=HTMLResponse)
def ui_agents(request: Request):
    return templates.TemplateResponse(
        request,
        "agents.html",
        {"agents": service.list_agent_profiles()},
    )


def _agent_detail_context(
    agent_name: str,
    *,
    flash: Optional[str] = None,
    flash_err: bool = False,
    seed_query: Optional[str] = None,
) -> Dict[str, Any]:
    from crm import runner

    agent = service.get_agent_profile(agent_name)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    runs = service.list_agent_runs(agent_name=agent_name, limit=1)
    latest = _decorate_run(runs[0]) if runs else None
    last_assignment = (
        service.latest_head_assignment() if agent_name == "discovery" else None
    )
    return {
        "agent": agent,
        "active": runner.get_active() if agent_name == "discovery" else None,
        "latest_run": latest,
        "last_assignment": last_assignment,
        "flash": flash,
        "flash_err": flash_err,
        "seed_query": seed_query,
    }


@router.get("/ui/agents/{agent_name}", response_class=HTMLResponse)
def ui_agent_detail(agent_name: str, request: Request):
    return templates.TemplateResponse(
        request,
        "agent_detail.html",
        _agent_detail_context(agent_name),
    )


@router.post("/ui/agents/discovery/start")
def ui_discovery_start(
    request: Request,
    seed_query: str = Form(...),
    max_search_results: Optional[int] = Form(None),
):
    from crm import runner
    from tools.registry import validate_tool_ids

    seed = seed_query.strip()
    try:
        profile = service.get_agent_profile("discovery") or {}
        validate_tool_ids(profile.get("enabled_tools") or [], agent_name="discovery")
        out = runner.start_discovery_scout(seed, max_search_results=max_search_results)
        flash = f"Scout started — Head will assign tools, then Discovery runs (pipeline {out['pipeline_run_id']})"
        return templates.TemplateResponse(
            request,
            "agent_detail.html",
            _agent_detail_context("discovery", flash=flash, seed_query=seed),
        )
    except (RuntimeError, ValueError) as e:
        return templates.TemplateResponse(
            request,
            "agent_detail.html",
            _agent_detail_context("discovery", flash=str(e), flash_err=True, seed_query=seed),
            status_code=400,
        )


@router.post("/ui/agents/discovery/finish")
def ui_discovery_finish(request: Request):
    from crm import runner

    try:
        out = runner.request_finish()
        flash = f"Finish requested — cancelling {out['pipeline_run_id']}"
        return templates.TemplateResponse(
            request,
            "agent_detail.html",
            _agent_detail_context("discovery", flash=flash),
        )
    except LookupError as e:
        return templates.TemplateResponse(
            request,
            "agent_detail.html",
            _agent_detail_context("discovery", flash=str(e), flash_err=True),
            status_code=404,
        )


@router.post("/ui/agents/{agent_name}/save")
async def ui_agent_save(
    agent_name: str,
    request: Request,
    display_name: str = Form(...),
    mission_prompt: str = Form(...),
    model: str = Form(""),
    default_seed_query: str = Form(""),
):
    form = await request.form()
    enabled = form.getlist("enabled_tools")
    data: Dict[str, Any] = {
        "display_name": display_name.strip(),
        "mission_prompt": mission_prompt,
        "enabled_tools": list(enabled),
        "model": model.strip() or None,
    }
    if agent_name == "discovery":
        data["default_seed_query"] = default_seed_query.strip() or None
    try:
        row = service.update_agent_profile(agent_name, data)
    except ValueError as e:
        return templates.TemplateResponse(
            request,
            "agent_detail.html",
            _agent_detail_context(agent_name, flash=str(e), flash_err=True),
            status_code=400,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Agent not found")
    return templates.TemplateResponse(
        request,
        "agent_detail.html",
        _agent_detail_context(agent_name, flash="Profile saved — next Start will use this config."),
    )
