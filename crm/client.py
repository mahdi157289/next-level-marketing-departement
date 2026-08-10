"""Agent-side CRM recorder — in-process today, HTTP adapter later."""

from __future__ import annotations

import traceback
from contextlib import contextmanager
from typing import Any, Dict, Generator, List, Optional

from crm import service


class CancelledError(Exception):
    """Raised when an agent cooperatively stops after Finish was requested."""


class _AgentRunContext:
    def __init__(self, run_id: str) -> None:
        self.id = run_id
        self._apis: List[Dict[str, Any]] = []
        self._records_processed = 0
        self._output_summary: Optional[str] = None
        self._output_json: Optional[Dict[str, Any]] = None

    def record_api(self, name: str, call_type: str, **extra: Any) -> None:
        entry: Dict[str, Any] = {"name": name, "type": call_type}
        entry.update(extra)
        self._apis.append(entry)

    def set_output(self, summary: Optional[str] = None, json: Optional[Dict[str, Any]] = None) -> None:
        if summary is not None:
            self._output_summary = summary[:2000] if len(summary) > 2000 else summary
        if json is not None:
            self._output_json = json

    def increment_records(self, n: int = 1) -> None:
        self._records_processed += n

    def _complete(self, status: str, error_message: Optional[str] = None) -> None:
        service.complete_agent_run(
            self.id,
            status=status,
            output_summary=self._output_summary,
            output_json=self._output_json,
            apis_consumed=self._apis,
            records_processed=self._records_processed,
            error_message=error_message,
        )


class AgentRunRecorder:
    """Records pipeline + agent runs to CRM tables."""

    def __init__(
        self,
        trigger: str = "api",
        seed_query: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.trigger = trigger
        self.seed_query = seed_query
        self.meta = meta or {}
        self.pipeline_run_id: Optional[str] = None

    def start_pipeline(self) -> str:
        row = service.start_pipeline_run(self.trigger, self.seed_query, self.meta)
        self.pipeline_run_id = str(row["id"])
        return self.pipeline_run_id

    def complete_pipeline(self, status: str = "success", meta: Optional[Dict[str, Any]] = None) -> None:
        if self.pipeline_run_id:
            service.complete_pipeline_run(self.pipeline_run_id, status, meta)

    @contextmanager
    def agent_run(
        self,
        agent_name: str,
        *,
        model: Optional[str] = None,
        input_summary: Optional[str] = None,
    ) -> Generator[_AgentRunContext, None, None]:
        if not self.pipeline_run_id:
            self.start_pipeline()
        row = service.start_agent_run(self.pipeline_run_id, agent_name, model, input_summary)
        ctx = _AgentRunContext(str(row["id"]))
        try:
            yield ctx
            ctx._complete("success")
        except CancelledError as exc:
            ctx._complete("cancelled", error_message=str(exc) or "cancelled")
            raise
        except Exception as exc:
            ctx._complete("failed", error_message=f"{exc}\n{traceback.format_exc()}")
            raise

    def create_lead_from_hit(self, hit: Dict[str, str], agent_run_id: str) -> Dict[str, Any]:
        return service.create_lead_from_search_hit(hit, agent_run_id=agent_run_id)

    def enrich_lead(self, lead_id: str, data: Dict[str, Any], agent_run_id: str) -> Optional[Dict[str, Any]]:
        """Persist enriched fields (email/phone/industry/country/seo_score) back to a lead."""
        return service.enrich_lead(lead_id, data, agent_run_id=agent_run_id)
