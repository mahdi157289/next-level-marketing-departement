"""Discovery scout workflow with optional Head tool/seed assignment."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from agents.discovery_agent import DiscoveryAgent
from agents.head_agent import HeadAgent
from crm import service as crm_service
from crm.client import AgentRunRecorder, CancelledError


def run_discovery_only(
    seed_query: str,
    *,
    max_search_results: int = 5,
    recorder: Optional[AgentRunRecorder] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
    trigger: str = "crm_ui",
    enabled_tools: Optional[List[str]] = None,
    head_assign: bool = True,
) -> Dict[str, Any]:
    """Run scout. When head_assign=True, Head picks tools/seed then Discovery executes."""
    if recorder is None:
        recorder = AgentRunRecorder(trigger=trigger, seed_query=seed_query)

    if not recorder.pipeline_run_id:
        recorder.start_pipeline()

    assignment: Optional[Dict[str, Any]] = None
    effective_seed = seed_query
    tools = enabled_tools

    try:
        if should_cancel and should_cancel():
            raise CancelledError("cancelled before start")

        if head_assign:
            assignment = HeadAgent().plan_discovery(seed_query, recorder=recorder)
            effective_seed = (assignment.get("seed_query") or seed_query).strip() or seed_query
            tools = assignment.get("tools")
            assign_meta = {
                "seed_query": effective_seed,
                "tools": tools,
                "skill_gaps": assignment.get("skill_gaps"),
                "rationale": assignment.get("rationale"),
            }
            recorder.meta = {**(recorder.meta or {}), "head_assignment": assign_meta}
            crm_service.merge_pipeline_meta(
                recorder.pipeline_run_id,
                {"head_assignment": assign_meta},
            )

        if should_cancel and should_cancel():
            raise CancelledError("cancelled after Head plan")

        discovery = DiscoveryAgent(
            enabled_tools=tools,
            should_cancel=should_cancel,
        ).run(
            effective_seed,
            max_results=max_search_results,
            recorder=recorder,
        )
        if should_cancel and should_cancel():
            recorder.complete_pipeline(
                "cancelled",
                meta={"reason": "cancelled_after_success", "head_assignment": assignment},
            )
            return {
                "seed_query": effective_seed,
                "pipeline_run_id": recorder.pipeline_run_id,
                "status": "cancelled",
                "discovery": discovery,
                "head_assignment": assignment,
            }
        recorder.complete_pipeline(
            "success",
            meta={"head_assignment": assignment} if assignment else None,
        )
        return {
            "seed_query": effective_seed,
            "pipeline_run_id": recorder.pipeline_run_id,
            "status": "success",
            "discovery": discovery,
            "head_assignment": assignment,
        }
    except CancelledError as exc:
        recorder.complete_pipeline(
            "cancelled",
            meta={"error": str(exc), "head_assignment": assignment},
        )
        return {
            "seed_query": effective_seed,
            "pipeline_run_id": recorder.pipeline_run_id,
            "status": "cancelled",
            "error": str(exc),
            "discovery": None,
            "head_assignment": assignment,
        }
    except Exception as exc:
        recorder.complete_pipeline(
            "failed",
            meta={"error": str(exc), "head_assignment": assignment},
        )
        return {
            "seed_query": effective_seed,
            "pipeline_run_id": recorder.pipeline_run_id,
            "status": "failed",
            "error": str(exc),
            "discovery": None,
            "head_assignment": assignment,
        }
