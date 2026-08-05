from fastapi import Depends, FastAPI
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.router import router as api_router
from crm.client import AgentRunRecorder
from crm.router import router as crm_router
from crm.ui import router as crm_ui_router
from db.session import get_db


def _unique_operation_id(route) -> str:
    method = sorted(route.methods)[0].lower() if route.methods else "get"
    segments = [seg for seg in route.path.split("/") if seg]
    cleaned = [seg.replace("{", "").replace("}", "").replace("-", "_") for seg in segments]
    path_part = "_".join(cleaned) if cleaned else "root"
    return f"{method}_{path_part}"


app = FastAPI(
    title="AI Marketing Department API",
    version="0.1.0",
    generate_unique_id_function=_unique_operation_id,
)
app.include_router(crm_router, prefix="/crm")
app.include_router(crm_ui_router, prefix="/crm")
app.include_router(api_router, prefix="/api")


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/crm/ui/leads")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/db")
def health_db(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}


class MinimalPipelineRequest(BaseModel):
    seed_query: str = Field(..., min_length=2, description="Discovery seed passed to DuckDuckGo + agents")
    max_search_results: int = Field(5, ge=1)


@app.post("/run/pipeline/minimal")
def run_pipeline_minimal(body: MinimalPipelineRequest) -> dict:
    """Run Discovery → Head over LM Studio / LiteLLM (blocking). Records CRM runs."""
    from workflows.main_pipeline import run_minimal_marketing_pipeline

    recorder = AgentRunRecorder(
        trigger="api",
        seed_query=body.seed_query,
        meta={"max_search_results": body.max_search_results},
    )
    return run_minimal_marketing_pipeline(
        body.seed_query,
        max_search_results=body.max_search_results,
        recorder=recorder,
    )
