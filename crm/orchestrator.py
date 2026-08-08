"""P6 — async agent dispatch: N-worker pool with Postgres-backed queue state.

Each dispatch creates a PipelineRun (status `running`) as the queue record; a
worker thread runs the agent's runner, then completes the run to success/failed.
The pool is process-local: on app restart `reclaim_stale_runs` marks orphaned
running runs failed.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, Optional

from config.settings import get_settings
from crm import service
from crm.client import AgentRunRecorder

_pool: Optional["WorkerPool"] = None
_lock = threading.Lock()


class WorkerPool:
    def __init__(self, max_workers: int) -> None:
        self.max_workers = max_workers
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="agent-worker")
        self._running = 0
        self._running_lock = threading.Lock()

    def submit(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        with self._running_lock:
            self._running += 1

        def _wrap(*a: Any, **kw: Any) -> Any:
            try:
                return fn(*a, **kw)
            finally:
                with self._running_lock:
                    self._running -= 1

        return self._executor.submit(_wrap, *args, **kwargs)

    def active_count(self) -> int:
        with self._running_lock:
            return self._running

    def queued_count(self) -> int:
        q = getattr(self._executor, "_work_queue", None)
        return q.qsize() if q is not None else 0


def pool() -> WorkerPool:
    global _pool
    with _lock:
        if _pool is None:
            _pool = WorkerPool(max_workers=get_settings().orchestrator_workers)
    return _pool


def active_count() -> int:
    try:
        return pool().active_count()
    except Exception:  # noqa: BLE001
        return 0


def queued_count() -> int:
    try:
        return pool().queued_count()
    except Exception:  # noqa: BLE001
        return 0


def _find_lead(seed_query: str) -> Optional[Dict[str, Any]]:
    query = (seed_query or "").strip()
    if not query:
        return None
    try:
        lead = service.get_lead(query)
        if lead:
            return lead
    except Exception:  # noqa: BLE001
        pass
    url = query.rstrip("/")
    for lead in service.list_leads(limit=10000):
        if (lead.get("url") or "").strip().rstrip("/") == url:
            return lead
    return None


def _run_discovery(run_id: str, seed_query: str, mission: Optional[str]) -> None:
    from workflows.discovery_only import run_discovery_only

    recorder = AgentRunRecorder(
        trigger="agent:discovery",
        seed_query=seed_query,
        meta={"from_agent": "discovery", "mode": "dispatch", "mission": mission or ""},
    )
    recorder.pipeline_run_id = run_id
    try:
        run_discovery_only(seed_query, recorder=recorder, trigger="agent:discovery")
    except Exception as exc:  # noqa: BLE001
        try:
            service.complete_pipeline_run(run_id, "failed", {"error": str(exc)})
        except Exception:  # noqa: BLE001
            pass


def _run_head(run_id: str, seed_query: str, mission: Optional[str]) -> None:
    from agents.head_agent import HeadAgent

    recorder = AgentRunRecorder(
        trigger="agent:head",
        seed_query=seed_query,
        meta={"from_agent": "head", "mode": "dispatch", "mission": mission or ""},
    )
    recorder.pipeline_run_id = run_id
    try:
        plan = HeadAgent().plan_discovery(seed_query or "Improve the pipeline", recorder=recorder)
        recorder.complete_pipeline(
            "success",
            meta={"mode": "dispatch", "seed_query": plan.get("seed_query"), "tools": plan.get("tools")},
        )
    except Exception as exc:  # noqa: BLE001
        try:
            service.complete_pipeline_run(run_id, "failed", {"error": str(exc)})
        except Exception:  # noqa: BLE001
            pass


def _run_qualifier(run_id: str, seed_query: str, mission: Optional[str]) -> None:
    from agents.qualifier_agent import QualifierAgent

    recorder = AgentRunRecorder(
        trigger="agent:qualifier",
        seed_query=seed_query,
        meta={"from_agent": "qualifier", "mode": "dispatch", "mission": mission or ""},
    )
    recorder.pipeline_run_id = run_id
    try:
        lead = _find_lead(seed_query)
        if lead is None:
            raise ValueError(f"qualifier dispatch needs a lead id or URL; got: {seed_query[:120]!r}")
        result = QualifierAgent().qualify(lead)
        recorder.complete_pipeline(
            "success",
            meta={
                "mode": "dispatch",
                "lead_id": str(lead.get("id")),
                "score": result.get("score"),
                "fit": result.get("fit"),
            },
        )
    except Exception as exc:  # noqa: BLE001
        try:
            service.complete_pipeline_run(run_id, "failed", {"error": str(exc)})
        except Exception:  # noqa: BLE001
            pass


_RUNNERS: Dict[str, Callable[[str, str, Optional[str]], None]] = {
    "discovery": _run_discovery,
    "head": _run_head,
    "qualifier": _run_qualifier,
}


def enqueue_run(agent_name: str, seed_query: str, mission: Optional[str] = None) -> Dict[str, Any]:
    """Enqueue a task for agent_name; returns the created PipelineRun dict."""
    if agent_name not in _RUNNERS:
        raise ValueError(f"No runner for agent: {agent_name}")
    run = service.start_pipeline_run(
        trigger=f"agent:{agent_name}",
        seed_query=seed_query,
        meta={"mission": mission or "", "from_agent": agent_name, "mode": "dispatch"},
    )
    run_id = str(run["id"])
    pool().submit(_RUNNERS[agent_name], run_id, seed_query, mission)
    return run


def reclaim_stale_runs() -> int:
    """Mark orchestrator-owned running runs failed (app restarted mid-run)."""
    runs = service.list_pipeline_runs(limit=500)
    n = 0
    for r in runs:
        if (
            r.get("status") == "running"
            and not r.get("finished_at")
            and (r.get("trigger") or "").startswith("agent:")
        ):
            service.complete_pipeline_run(str(r["id"]), "failed", {"error": "app restarted mid-run"})
            n += 1
    return n
