# CRM REST API

Mounted at `/crm/*` on the FastAPI app (port 8000). OpenAPI auto-docs at
`/docs`.

All responses are JSON unless noted. `UUID` query/path params are standard
RFC 4122 strings.

---

## 1. Health

### `GET /crm/health`
Verifies the CRM module can reach the database.

```bash
curl http://localhost:8000/crm/health
# 200 OK
# {"status": "ok", "module": "crm"}
```

---

## 2. Leads

### `GET /crm/leads?status=&limit=`
List leads, newest first.

```bash
curl "http://localhost:8000/crm/leads?status=raw&limit=20"
```

| Query | Type | Default |
|---|---|---|
| `status` | string (one of `LeadStatusStr`) | none |
| `limit` | int 1..500 | 100 |

Response: `LeadRead[]`

### `GET /crm/leads/{lead_id}`
Lead detail + recent `lead_events`.

```bash
curl http://localhost:8000/crm/leads/8c4b6c66-...
```

Response: `LeadDetailOut` (extends `LeadRead` with `events: LeadEventRead[]`).

### `POST /crm/leads`
Create a lead (idempotent on `url`).

```bash
curl -X POST http://localhost:8000/crm/leads \
  -H "Content-Type: application/json" \
  -d '{"name":"Acme","url":"https://acme.tn","status":"raw","source":"api"}'
```

| Body | Type | Required | Notes |
|---|---|---|---|
| `name` | string | no | |
| `url` | string | no (but UNIQUE-keyed) | provide for idempotency |
| `status` | string | no | default `raw` |
| `source` | string | no | default `discovery` |
| `country`, `industry`, `business_type`, `email`, `phone` | string | no | |
| `seo_score` | int | no | |
| `lead_score` | float | no | |
| `status_notes` | text | no | |

Response: `201 Created`, `LeadOut`

### `PATCH /crm/leads/{lead_id}`
Partial update. Every field optional. On `status` change, a `lead_events`
row of type `status_changed` is written.

```bash
curl -X PATCH http://localhost:8000/crm/leads/8c4b6c66-... \
  -H "Content-Type: application/json" \
  -d '{"status":"enriched","lead_score":78.5}'
```

Response: `200 OK`, `LeadOut`

---

## 3. Pipeline runs

### `POST /crm/pipeline-runs`
Open a pipeline run. **Used internally by the `/run/pipeline/minimal`
route** — clients normally don't need to call this.

```bash
curl -X POST http://localhost:8000/crm/pipeline-runs \
  -H "Content-Type: application/json" \
  -d '{"trigger":"api","seed_query":"software agency Tunisia","meta":{}}'
```

Response: `201 Created`, `PipelineRunOut`

### `PATCH /crm/pipeline-runs/{run_id}`
Close a pipeline run. Sets `status`, `finished_at`, optionally merges
`meta`.

```bash
curl -X PATCH http://localhost:8000/crm/pipeline-runs/8c4b6c66-... \
  -H "Content-Type: application/json" \
  -d '{"status":"success","meta":{"discovery_hits":4}}'
```

Response: `200 OK`, `PipelineRunOut`

### `GET /crm/pipeline-runs?limit=`
List pipeline runs, newest first.

Response: `PipelineRunOut[]`

### `GET /crm/pipeline-runs/{run_id}`
Single run.

---

## 4. Agent runs

### `POST /crm/agent-runs`
Start an agent run. **Used internally by `crm.client.AgentRunRecorder`** —
clients normally don't need to call this.

```bash
curl -X POST http://localhost:8000/crm/agent-runs \
  -H "Content-Type: application/json" \
  -d '{
        "pipeline_run_id":"8c4b6c66-...",
        "agent_name":"discovery",
        "model":"discovery-model",
        "input_summary":"seed_query=... max_results=5"
      }'
```

Response: `201 Created`, `AgentRunOut`

### `PATCH /crm/agent-runs/{run_id}`
Complete an agent run. This is where the agent reports its outcome.

```bash
curl -X PATCH http://localhost:8000/crm/agent-runs/8c4b6c66-... \
  -H "Content-Type: application/json" \
  -d '{
        "status":"success",
        "output_summary":"Found 4 leads...",
        "output_json":{"leads_persisted":4},
        "apis_consumed":[
          {"name":"ddgs","type":"web_search","query":"...","hits":4,"duration_ms":1820},
          {"name":"litellm","type":"chat","model":"discovery-model","duration_ms":12340}
        ],
        "records_processed":4
      }'
```

| Body | Type | Notes |
|---|---|---|
| `status` | enum | `success` or `failed` (running is implicit) |
| `output_summary` | text | truncated markdown / one-liner |
| `output_json` | object | structured payload |
| `apis_consumed` | array | see `AGENT_INTEGRATION.md` §3 |
| `records_processed` | int | leads touched |
| `error_message` | text | on failure |

Response: `200 OK`, `AgentRunOut`

### `GET /crm/agent-runs?agent_name=&pipeline_run_id=&limit=`
List agent runs, newest first.

```bash
curl "http://localhost:8000/crm/agent-runs?agent_name=discovery&limit=20"
curl "http://localhost:8000/crm/agent-runs?pipeline_run_id=8c4b6c66-...&limit=20"
```

Response: `AgentRunOut[]`

### `GET /crm/agent-runs/{run_id}`
Single agent run with full `output_json` and `apis_consumed`.

---

## 5. UI routes (HTML)

| URL | Page |
|---|---|
| `GET /crm/ui` | redirect to `/crm/ui/leads` |
| `GET /crm/ui/leads` | leads table |
| `GET /crm/ui/leads/{id}` | lead detail (events) |
| `GET /crm/ui/runs` | agent runs table |
| `GET /crm/ui/runs/{id}` | run detail (input/output/apis) |

UI is read-only.

---

## 6. Errors

The router uses standard HTTP semantics:

| Code | When |
|---|---|
| 200 | success |
| 201 | created (`POST` only) |
| 404 | id not found |
| 422 | Pydantic validation failure (bad body / query) |
| 500 | unexpected error (logged; will show as `failed` agent_run if it occurs inside the pipeline) |
