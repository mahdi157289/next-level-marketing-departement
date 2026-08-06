# Start the marketing department

## Boot sequence

```powershell
cd "c:\Users\bacca\Desktop\next level marketing department"
docker compose up -d postgres redis litellm app
docker compose exec app alembic upgrade head
```

## LM Studio (required for agents)

1. Open LM Studio  
2. Load: `google_-_gemma-2-9b-it` (Discovery), `qwen3-14b` (Head)  
3. Start **Local Server** on **1234**  
4. Set Gemma **context length ≥ 4096** (avoids `Context size has been exceeded`)

## Open CRM

| Page | URL |
|------|-----|
| Leads | http://localhost:8000/crm/ui/leads |
| Agent runs | http://localhost:8000/crm/ui/runs |
| Agents | http://localhost:8000/crm/ui/agents |
| Discovery scout | http://localhost:8000/crm/ui/agents/discovery |
| API | http://localhost:8000/api/docs |
| SPA (React) | http://localhost:3000 |
| Scout HQ (chat + missions) | http://localhost:3000/scout-hq |

## Run a scout

1. Go to Discovery agent page  
2. Enable tools: `web_search`, `crm_write_leads`, `llm_chat`  
3. Enter goal / seed (e.g. `digital marketing agencies Tunisia`)  
4. Click **Start scout**  

Flow: **Head assigns tools** → **Discovery searches + writes leads** → CRM updates.

**Finish** cancels an in-flight scout (cooperative between steps).

## Scout HQ API (new)

| Endpoint | Purpose |
|----------|---------|
| GET /api/pipeline-runs | Mission board list with agent-run counts |
| GET /api/stats | Dashboard KPI aggregates |
| GET /api/scout/status | Active scout + latest missions (topbar badge) |
| GET/POST /api/scout/threads | List / create chat threads |
| GET /api/scout/threads/{id}/messages | Chat history |
| POST /api/scout/threads/{id}/messages | Send a message (SSE stream) |

The React SPA is served by the `web` container on port 3000 (dev: `cd web && npm run dev`, proxying `/api` to `localhost:8000`).

## Health checks

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://127.0.0.1:1234/v1/models
Invoke-RestMethod http://localhost:8000/crm/health
```

## Common failures

| Symptom | Cause | Fix |
|---------|--------|-----|
| Start says LM Studio not reachable | Server off | Start LM Studio on :1234 |
| Scout already running | Previous run stuck | Press **Finish**, or wait |
| Discovery failed: Context size exceeded | Gemma `n_ctx` too small / `max_tokens` too high | Raise context to 4096+; code now shrinks + falls back |
| No new leads | `crm_write_leads` disabled | Enable in Discovery tools |
| Every URL returns 404 (even `/health`) | Port 8000 is held by a **stale uvicorn from another project** (e.g. `uvicorn app.main:app` from `Desktop\PFE\...`), or Docker Desktop is off | Kill the foreign uvicorn: `Get-Process python | Where-Object { $_.StartTime -lt (Get-Date).AddHours(-1) }` → verify command line with `Get-CimInstance Win32_Process`, then `Stop-Process`. Start Docker Desktop, then `docker compose up -d app`. See 2026-08-05 incident below. |
| Compose says engine pipe not found | Docker Desktop not running | Start Docker Desktop and wait for the engine (poll `docker info`) |

## 2026-08-05 incident: foreign uvicorn on port 8000

A leftover `uvicorn app.main:app --host 127.0.0.1 --port 8000` (Python 3.9, from the PFE
FastAPI-Celery-NoSQL project on the Desktop) was bound to port 8000, so `localhost:8000`
served the wrong app — every route, including `/health`, returned 404 — while Docker Desktop
was off and the compose `app` container was down.

**Resolution:** killed PID 23272 (`Stop-Process -Id 23272 -Force`), started Docker Desktop,
polled `docker info` until ready, ran `docker compose up -d`. All URLs returned 200 after.

**Prevention:** never run local dev uvicorn on port 8000 (use 8001+) when the Docker stack owns
that port. If the CRM ever returns 404 on everything, check `Get-NetTCPConnection -LocalPort 8000 -State Listen`
and verify the owning process is the Docker `app` container, not a stray local python.

See [docs/crm/SCOUT_FAILURE_2026-07-19.md](../crm/SCOUT_FAILURE_2026-07-19.md) for the 2026-07-19 incident write-up.
