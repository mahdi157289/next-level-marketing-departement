"""In-process Discovery scout runner with cooperative cancel."""

from __future__ import annotations

import threading
from typing import Any, Dict, Optional

from crm import service
from crm.client import AgentRunRecorder

_lock = threading.Lock()
_active: Optional[Dict[str, Any]] = None
_active_enrich: Optional[Dict[str, Any]] = None


def _slot_status(slot: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not slot:
        return None
    thread = slot.get("thread")
    if thread is not None and not thread.is_alive():
        return None
    return {
        "pipeline_run_id": slot["pipeline_run_id"],
        "seed_query": slot.get("seed_query"),
        "started": True,
    }


def get_active() -> Optional[Dict[str, Any]]:
    with _lock:
        return _slot_status(_active) or _slot_status(_active_enrich)


def _clear_stale_active_unlocked() -> None:
    """Drop slot if worker thread already exited (or never started)."""
    global _active, _active_enrich
    for slot in (_active, _active_enrich):
        if not slot:
            continue
        thread = slot.get("thread")
        if thread is None or not thread.is_alive():
            if slot is _active:
                _active = None
            else:
                _active_enrich = None


def request_finish() -> Dict[str, Any]:
    """Signal Finish (cancel) for the active Discovery scout or enrich job."""
    with _lock:
        _clear_stale_active_unlocked()
        slot = _active or _active_enrich
        if not slot:
            raise LookupError("No active Discovery scout or enrich job to finish")
        slot["cancel_event"].set()
        pid = slot["pipeline_run_id"]
    return {"pipeline_run_id": pid, "status": "cancelling"}


def start_discovery_scout(
    seed_query: str,
    *,
    max_search_results: Optional[int] = None,
    mission: Optional[str] = None,
) -> Dict[str, Any]:
    """Start Discovery-only in a background thread; return pipeline_run_id immediately."""
    global _active

    # Fail fast with a clear message — Head plan + Discovery LLM both need LM Studio.
    from agents.lm_client import ensure_llm_reachable

    ok, detail = ensure_llm_reachable()
    if not ok:
        raise RuntimeError(
            "LLM provider is not reachable. Check OPENAI_API_BASE / OPENAI_API_KEY in .env "
            f"and that the model is available. ({detail})"
        )

    with _lock:
        _clear_stale_active_unlocked()
        if (
            _active
            and _active.get("thread")
            and _active["thread"].is_alive()
            and not _active["cancel_event"].is_set()
        ):
            raise RuntimeError(
                f"Discovery scout already running: {_active['pipeline_run_id']}. "
                "Press Finish (cancel) first, or wait for it to complete."
            )
        cancel_event = threading.Event()
        recorder = AgentRunRecorder(
            trigger="crm_ui",
            seed_query=seed_query,
            meta={
                "max_search_results": max_search_results,
                "mode": "discovery_only",
                "head_assign": True,
                "mission": mission or "",
            },
        )
        pipeline_run_id = recorder.start_pipeline()
        slot: Dict[str, Any] = {
            "pipeline_run_id": pipeline_run_id,
            "seed_query": seed_query,
            "cancel_event": cancel_event,
            "thread": None,
            "result": None,
        }
        _active = slot

    def _worker() -> None:
        global _active
        from workflows.discovery_only import run_discovery_only

        def should_cancel() -> bool:
            return cancel_event.is_set()

        try:
            result = run_discovery_only(
                seed_query,
                max_search_results=max_search_results,
                recorder=recorder,
                should_cancel=should_cancel,
                trigger="crm_ui",
            )
        except Exception as exc:
            result = {
                "pipeline_run_id": pipeline_run_id,
                "status": "failed",
                "error": str(exc),
            }
            try:
                service.complete_pipeline_run(pipeline_run_id, "failed", {"error": str(exc)})
            except Exception:
                pass

        with _lock:
            if _active and _active.get("pipeline_run_id") == pipeline_run_id:
                _active["result"] = result
                _active = None

    t = threading.Thread(
        target=_worker,
        name=f"discovery-scout-{pipeline_run_id[:8]}",
        daemon=True,
    )
    with _lock:
        if _active and _active.get("pipeline_run_id") == pipeline_run_id:
            _active["thread"] = t
    t.start()

    return {
        "pipeline_run_id": pipeline_run_id,
        "status": "running",
        "seed_query": seed_query,
    }


def start_enrich_job(
    lead_ids: Optional[list] = None,
    *,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """Start a Lead Completion (enrich) backfill job in a background thread."""
    global _active_enrich

    if not lead_ids:
        leads = service.list_leads(limit=limit or 200)
        lead_ids = [str(l["id"]) for l in leads]
    if not lead_ids:
        raise ValueError("No leads to enrich")

    with _lock:
        _clear_stale_active_unlocked()
        for slot in (_active, _active_enrich):
            if (
                slot
                and slot.get("thread")
                and slot["thread"].is_alive()
                and not slot["cancel_event"].is_set()
            ):
                raise RuntimeError(
                    f"Another job is already running: {slot['pipeline_run_id']}. "
                    "Press Finish (cancel) first, or wait for it to complete."
                )
        cancel_event = threading.Event()
        recorder = AgentRunRecorder(
            trigger="enrich_backfill",
            seed_query=f"enrich {len(lead_ids)} leads",
            meta={"mode": "lead_completion", "target_count": len(lead_ids)},
        )
        pipeline_run_id = recorder.start_pipeline()
        slot: Dict[str, Any] = {
            "pipeline_run_id": pipeline_run_id,
            "seed_query": f"enrich {len(lead_ids)} leads",
            "cancel_event": cancel_event,
            "thread": None,
            "result": None,
        }
        _active_enrich = slot

    def _worker() -> None:
        global _active_enrich
        from workflows.enrich_leads import enrich_leads

        def should_cancel() -> bool:
            return cancel_event.is_set()

        try:
            result = enrich_leads(
                lead_ids,
                recorder=recorder,
                should_cancel=should_cancel,
                max_workers=1,
            )
        except Exception as exc:
            result = {
                "pipeline_run_id": pipeline_run_id,
                "status": "failed",
                "error": str(exc),
            }
            try:
                service.complete_pipeline_run(pipeline_run_id, "failed", {"error": str(exc)})
            except Exception:
                pass

        with _lock:
            if _active_enrich and _active_enrich.get("pipeline_run_id") == pipeline_run_id:
                _active_enrich["result"] = result
                _active_enrich = None

    t = threading.Thread(
        target=_worker,
        name=f"enrich-job-{pipeline_run_id[:8]}",
        daemon=True,
    )
    with _lock:
        if _active_enrich and _active_enrich.get("pipeline_run_id") == pipeline_run_id:
            _active_enrich["thread"] = t
    t.start()

    return {
        "pipeline_run_id": pipeline_run_id,
        "status": "running",
        "target_count": len(lead_ids),
    }
