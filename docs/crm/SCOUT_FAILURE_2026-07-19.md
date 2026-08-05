# Scout failure log — 2026-07-19

## Symptom

Pressing **Start scout** on `/crm/ui/agents/discovery` showed **failed** after Head planned successfully.

## Evidence (Postgres)

Latest pipeline `8ba6be09-…`:

| Step | Status | Notes |
|------|--------|--------|
| Head `plan_discovery` | success | Assigned `web_search`, `llm_chat` only |
| Discovery | failed | `Context size has been exceeded` on `discovery-model` (Gemma via LiteLLM) |
| Leads written | 0 | Head omitted `crm_write_leads` → no CRM inserts |

Error (truncated):

```text
litellm.BadRequestError: OpenAIException - Error code: 400 -
{'error': 'Context size has been exceeded.'}
Received Model Group=discovery-model
```

Earlier related failures the same night:

- LM Studio off → scout hung / “already running” on second Start
- Brief HTTP 500 from a bad `lm_client.py` reload (fixed)
- Web search / scrape could hang without timeouts

## Root cause

Two bugs stacked:

1. **Gemma context overflow**  
   LM Studio rejects the request when `prompt_tokens + max_tokens > n_ctx`.  
   Discovery used `max_tokens=512` plus search JSON → 400 even after light prompt shrink.

2. **Head skipped `crm_write_leads`**  
   Planner JSON often returned only `web_search` + `llm_chat`.  
   Even a successful LLM report would not write leads.

## Fixes applied

| Change | File |
|--------|------|
| Shrink prompt + lower `max_tokens` on retry (192 → 96 → 64) | `agents/discovery_agent.py` |
| If LLM still fails → deterministic Markdown report (scout succeeds) | `agents/discovery_agent.py` |
| Force `crm_write_leads` when operator enabled it | `tools/registry.py` (`DISCOVERY_FORCE_IF_ALLOWED`) |
| Head plan prompt: always include `crm_write_leads` when allowed | `agents/head_agent.py` |
| Search engine timeout 12s; scrape timeout 25s | `tools/web_search_tool.py`, `agents/discovery_agent.py` |
| Preflight: refuse Start if LM Studio unreachable | `agents/lm_client.py`, `crm/runner.py` |

## Operator checklist (before Start scout)

1. `docker compose up -d postgres redis litellm app`
2. LM Studio Local Server **ON** at port **1234**
3. Load at least `google_-_gemma-2-9b-it` and `qwen3-14b`
4. In LM Studio for Gemma: set **context length ≥ 4096** (recommended)
5. Discovery tools: enable `web_search`, `crm_write_leads`, `llm_chat` (uncheck `scrape` unless needed)
6. Open http://localhost:8000/crm/ui/agents/discovery → **Start scout**

## Verify

```powershell
# After a run:
Invoke-RestMethod "http://localhost:8000/crm/agent-runs?agent_name=discovery&limit=1"
Invoke-RestMethod "http://localhost:8000/crm/leads?limit=10"
```

Expect: pipeline `success`, Discovery `success` (or success with degraded LLM note), new `source=discovery` leads.

## Related docs

- [docs/crm/AGENT_INTEGRATION.md](AGENT_INTEGRATION.md) — recorder contract
- [docs/ops/START_DEPARTMENT.md](../ops/START_DEPARTMENT.md) — boot sequence
