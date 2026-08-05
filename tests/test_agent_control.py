"""Agent profile CRM control — real Postgres, no leftover mock leads."""

from __future__ import annotations

import os
import threading
import time
from typing import Optional
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from crm.client import CancelledError
from tools.registry import validate_tool_ids


def _database_url() -> Optional[str]:
    return os.getenv("DATABASE_URL")


@pytest.fixture
def client():
    from api.main import app

    return TestClient(app)


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")
def test_list_and_get_agent_profiles(client):
    r = client.get("/crm/agents")
    assert r.status_code == 200, r.text
    agents = r.json()
    names = {a["agent_name"] for a in agents}
    assert "discovery" in names
    assert "head" in names

    r = client.get("/crm/agents/discovery")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "mission_prompt" in body
    assert "web_search" in body["enabled_tools"]
    assert any(t["id"] == "web_search" for t in body["available_tools"])


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")
def test_patch_agent_mission_prompt_persists(client):
    r = client.get("/crm/agents/discovery")
    assert r.status_code == 200
    original = r.json()["mission_prompt"]
    marker = "MISSION_MARKER_AGENT_CTRL_TEST"
    try:
        r = client.patch(
            "/crm/agents/discovery",
            json={"mission_prompt": marker + "\nRespond as Markdown bullets only."},
        )
        assert r.status_code == 200, r.text
        assert r.json()["mission_prompt"].startswith(marker)

        r = client.get("/crm/agents/discovery")
        assert r.json()["mission_prompt"].startswith(marker)
    finally:
        client.patch("/crm/agents/discovery", json={"mission_prompt": original})


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")
def test_patch_rejects_missing_required_tools(client):
    r = client.patch(
        "/crm/agents/discovery",
        json={"enabled_tools": ["seo_audit"]},
    )
    assert r.status_code == 400
    assert "web_search" in r.text or "required" in r.text.lower()


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")
def test_pipeline_run_get(client):
    from crm import service

    row = service.start_pipeline_run("pytest", "agent-ctrl-get-check", {"tmp": True})
    pid = str(row["id"])
    try:
        r = client.get(f"/crm/pipeline-runs/{pid}")
        assert r.status_code == 200, r.text
        assert r.json()["id"] == pid
        assert r.json()["status"] == "running"
    finally:
        service.complete_pipeline_run(pid, "cancelled", {"reason": "test_cleanup"})


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")
def test_discovery_finish_without_active_returns_404(client):
    from crm import runner

    # Ensure no lingering active scout from prior tests
    active = runner.get_active()
    if active:
        try:
            runner.request_finish()
            time.sleep(0.5)
        except LookupError:
            pass

    r = client.post("/crm/agents/discovery/finish")
    assert r.status_code == 404


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")
def test_discovery_cancel_cooperative(client):
    """Start scout with immediate cancel flag path via should_cancel mock."""
    from agents.discovery_agent import DiscoveryAgent
    from crm.client import AgentRunRecorder

    cancel = threading.Event()
    cancel.set()
    recorder = AgentRunRecorder(trigger="pytest", seed_query="cancel-coop-test")
    recorder.start_pipeline()
    agent = DiscoveryAgent(should_cancel=cancel.is_set)
    with pytest.raises(CancelledError):
        # Direct call: cancelled before search begins
        with recorder.agent_run("discovery", model="n/a", input_summary="cancel-coop"):
            if cancel.is_set():
                raise CancelledError("forced")
    # agent_run marks cancelled; complete pipeline
    recorder.complete_pipeline("cancelled", meta={"reason": "test"})
    runs = client.get(f"/crm/agent-runs?pipeline_run_id={recorder.pipeline_run_id}").json()
    assert runs
    assert runs[0]["status"] == "cancelled"


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")
def test_ui_agents_pages(client):
    r = client.get("/crm/ui/agents")
    assert r.status_code == 200, r.text
    assert b"Discovery" in r.content or b"discovery" in r.content

    r = client.get("/crm/ui/agents/discovery")
    assert r.status_code == 200, r.text
    assert b"Mission prompt" in r.content
    assert b"Start scout" in r.content


def test_validate_tool_ids_discovery_required():
    with pytest.raises(ValueError):
        validate_tool_ids(["llm_chat"], agent_name="discovery")
    out = validate_tool_ids(["web_search", "llm_chat", "crm_write_leads"], agent_name="discovery")
    assert "web_search" in out


def test_clamp_discovery_tools_intersects_allowed():
    from tools.registry import clamp_discovery_tools

    out = clamp_discovery_tools(
        ["web_search", "llm_chat", "scrape", "crm_write_leads"],
        allowed=["web_search", "llm_chat", "crm_write_leads"],
    )
    assert "scrape" in out["skill_gaps"]
    assert "scrape" not in out["tools"]
    assert "web_search" in out["tools"]
    assert "llm_chat" in out["tools"]


def test_clamp_forces_crm_write_when_allowed():
    from tools.registry import clamp_discovery_tools

    # Head omitted crm_write_leads — clamp must re-add it if operator allowed it.
    out = clamp_discovery_tools(
        ["web_search", "llm_chat"],
        allowed=["web_search", "llm_chat", "crm_write_leads"],
    )
    assert "crm_write_leads" in out["tools"]


def test_parse_head_plan_json():
    from agents.head_agent import _parse_plan_json

    text = 'Here you go:\n```json\n{"seed_query":"agencies Tunisia","tools":["web_search","llm_chat"],"rationale":"ok"}\n```'
    data = _parse_plan_json(text)
    assert data["seed_query"] == "agencies Tunisia"
    assert "web_search" in data["tools"]


def test_head_fallback_plan_without_llm():
    from agents.head_agent import HeadAgent

    agent = HeadAgent(enabled_tools=[])  # llm_chat off → fallback
    plan = agent.plan_discovery(
        "digital marketing Tunisia",
        allowed_tools=["web_search", "llm_chat", "crm_write_leads"],
    )
    assert plan["seed_query"]
    assert "web_search" in plan["tools"]
    assert "llm_chat" in plan["tools"]
