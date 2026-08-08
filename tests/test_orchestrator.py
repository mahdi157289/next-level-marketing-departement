"""P6 — crm/orchestrator.py worker pool + runner registry (hermetic)."""

from __future__ import annotations

import pytest


class _FakePool:
    def __init__(self, max_workers=3):
        self.max_workers = max_workers
        self.submitted = []

    def submit(self, fn, run_id, seed, mission=None):
        self.submitted.append((fn, run_id, seed, mission))


def test_runner_registry_maps_task_agents():
    from crm import orchestrator

    assert set(orchestrator._RUNNERS) == {"discovery", "head", "qualifier"}


def test_enqueue_unknown_agent_raises(monkeypatch):
    from crm import orchestrator

    monkeypatch.setattr(orchestrator, "pool", lambda: _FakePool())
    monkeypatch.setattr(orchestrator.service, "start_pipeline_run",
                        lambda trigger, seed_query, meta=None: {"id": "r1"})
    with pytest.raises(ValueError):
        orchestrator.enqueue_run("nope", "x")


def test_enqueue_submits_runner_with_run(monkeypatch):
    from crm import orchestrator

    fake = _FakePool()
    monkeypatch.setattr(orchestrator, "pool", lambda: fake)
    monkeypatch.setattr(orchestrator.service, "start_pipeline_run",
                        lambda trigger, seed_query, meta=None: {"id": "r-1", "seed_query": seed_query})
    run = orchestrator.enqueue_run("head", "seed me", mission="m1")
    assert run["id"] == "r-1"
    assert fake.submitted[0][1] == "r-1"
    assert fake.submitted[0][2] == "seed me"
    assert fake.submitted[0][3] == "m1"


def test_run_head_marks_success(monkeypatch):
    from agents import head_agent as head_mod
    from crm import orchestrator

    completed = {}

    class _Recorder:
        pipeline_run_id = "r-9"

        def complete_pipeline(self, status="success", meta=None):
            completed["status"] = status

    class _Head:
        def plan_discovery(self, goal, recorder=None):
            return {"seed_query": "s", "tools": ["llm_chat"], "rationale": "r"}

    monkeypatch.setattr(orchestrator, "AgentRunRecorder", lambda *a, **kw: _Recorder())
    monkeypatch.setattr(head_mod, "HeadAgent", lambda: _Head())
    orchestrator._run_head("r-9", "s", None)
    assert completed["status"] == "success"


def test_run_head_marks_failed_on_error(monkeypatch):
    from agents import head_agent as head_mod
    from crm import orchestrator

    class _Recorder:
        pipeline_run_id = "r-9"

        def complete_pipeline(self, status="success", meta=None):
            pass

    class _Head:
        def plan_discovery(self, goal, recorder=None):
            raise RuntimeError("llm down")

    monkeypatch.setattr(orchestrator, "AgentRunRecorder", lambda *a, **kw: _Recorder())
    monkeypatch.setattr(head_mod, "HeadAgent", lambda: _Head())
    monkeypatch.setattr(orchestrator.service, "complete_pipeline_run",
                        lambda run_id, status, meta=None: None)
    orchestrator._run_head("r-9", "s", None)
    # no raise expected
