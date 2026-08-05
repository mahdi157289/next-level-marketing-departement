# Agent Integration Contract

How every agent in the marketing department talks to the CRM.

---

## 1. The recorder

Every agent that needs to be observable uses `crm.client.AgentRunRecorder`.

```python
from crm.client import AgentRunRecorder

recorder = AgentRunRecorder(trigger="api", seed_query="...", meta={...})
recorder.start_pipeline()           # opens pipeline_runs row
try:
    with recorder.agent_run("discovery", model=..., input_summary=...) as run:
        run.record_api("ddgs", "web_search", query=..., hits=4, duration_ms=1820)
        run.record_api("litellm", "chat", model="discovery-model", duration_ms=12340)
        ...
        run.increment_records(4)    # leads created
        run.set_output(summary="...", json={"...": "..."})
        # success path: ctx.__exit__(None, None, None) -> service.complete_agent_run(success)
    # next agent
    with recorder.agent_run("head", model=..., input_summary=...) as run:
        run.record_api("litellm", "chat", model="head-model", duration_ms=8420)
        run.set_output(summary="...", json={"...": "..."})
    recorder.complete_pipeline(status="success", meta={"...": "..."})
except Exception:
    recorder.complete_pipeline(status="failed", meta={"error": "..."})
    raise
```

**Three rules:**

1. **One `agent_run` context per agent step.** Nesting is not supported.
2. **`record_api` is the technical trace.** Call it once per external
   dependency the agent touched. The list is what the UI shows.
3. **`set_output` is the human summary.** The first 500 chars go to
   `output_summary`; the structured payload goes to `output_json`.

---

## 2. Persisting leads

Discovery currently writes `Lead` rows via `recorder.create_lead_from_hit(...)`:

```python
row = recorder.create_lead_from_hit(hit, agent_run_id=run.id)
if row and row.get("created"):
    leads_created += 1
```

- `hit` is a `{title, url, snippet}` dict from `tools.web_search_tool`.
- The service validates `url.startswith("http")`; non-http hits are
  silently dropped.
- On URL duplicate, the service returns the existing row with
  `created=False`. **Don't count duplicates as new leads.**

Each new lead produces a `lead_events` row of type `created` with
`payload={"source":"discovery"}`.

---

## 3. `apis_consumed` schema

JSON array of `ApiConsumedEntry`:

```json
{
  "name": "litellm",
  "type": "chat",
  "model": "discovery-model",
  "duration_ms": 12340,
  "query": null,
  "hits": null,
  "url": null,
  "extra": null
}
```

| Field | Type | Used by |
|---|---|---|
| `name` | string (required) | `ddgs`, `duckduckgo_search`, `litellm`, `openai`, `playwright`, `httpx`, `smtp`, `whatsapp` |
| `type` | string (required) | `web_search`, `chat`, `scrape`, `seo_audit`, `email`, `whatsapp` |
| `model` | string | when `type=chat` |
| `query` | string | when `type=web_search` |
| `hits` | int | when `type=web_search` |
| `url` | string | when `type=scrape` / `seo_audit` |
| `duration_ms` | int | **always include** when measurable |
| `extra` | object | open-ended |

---

## 4. Lead write rules

| Agent | Source | Default status | Field defaults |
|---|---|---|---|
| Discovery | `discovery` | `raw` | `name` = hit title; `url` = hit url; `status_notes` = hit snippet |
| Categorization | `categorization` | `categorized` | `country`, `industry`, `business_type` |
| Analysis | `analysis` | `enriched` | `seo_score`, `automation_gaps`, `weaknesses`, `email`, `phone`, `lead_score` |
| Outreach | `outreach` | `contacted` | writes to `outreach_records` (not leads) |
| Content | (no lead writes) | — | — |

A status transition must be accompanied by a `lead_events` row of type
`status_changed` with `payload={field:"status", old, new}`. The service
does this automatically when you `update_lead` with a status.

---

## 5. Failure handling

If an exception is raised inside `with recorder.agent_run(...) as run:`,
the context manager:

1. Calls `service.complete_agent_run(status="failed", error_message=traceback)`.
2. **Re-raises** the exception so the pipeline can handle it.

The pipeline route catches it, calls `recorder.complete_pipeline(status="failed")`,
and re-raises so FastAPI returns 500. The CRM rows are still there —
you'll see the `failed` rows in the UI and can debug from there.

---

## 6. Per-agent checklist

| Agent | Records `apis_consumed` | Writes leads | Sets `records_processed` |
|---|---|---|---|
| Discovery | `ddgs`, `litellm` | yes (idempotent) | yes (leads created) |
| Head | `litellm` | no | n/a |
| Categorization | (planned) `llm` | yes (tags) | yes |
| Analysis | (planned) `httpx`, `playwright`, `litellm` | yes (enrichment) | yes |
| Outreach | (planned) `smtp`, `whatsapp` | no (writes `outreach_records`) | yes (sent count) |
| Content | (planned) `diffusers`, `wordpress`, social APIs | no | yes (assets published) |
