# Technical Implementation Tracker — AI Marketing Department

**Purpose:** Single source of truth for technical progress: what is done, what is next, and decisions that affect implementation.  
**Audience:** Developers and AI assistants continuing this repo.  
**Last reviewed:** 2026-07-14 (Department CRM module wired)  

---

## 1. Product goal (north star)

Build **NextLevel AI Marketing Department** per `doc1_PRD.md` and `ide_prompt_updated.md`:

- Multi-agent pipeline (discovery → categorization → analysis → head review → outreach → content).
- **Local LLMs** via **LM Studio** at `http://127.0.0.1:1234` (OpenAI-compatible API).
- **PostgreSQL** for CRM/leads/metrics; **Redis + Celery** for async/scheduled work; **FAISS + embeddings** for company knowledge (or sync from site DB — see §8).
- **FastAPI** as the HTTP control plane.
- **No WordPress in Docker** — live site: [The Next Level Tech Company](https://the-next-level-tech-company-1.onrender.com/en). Publishing and service truth will integrate with **the site’s database / APIs** (see §8).

---

## 2. Locked decisions (do not regress without explicit change)

| Topic | Decision |
|-------|----------|
| LLM runtime | **LM Studio** Local Server; models: `phi-2`, `google/gemma-2-9b`, `mistralai/mistral-7b-instruct-v0.3`, `qwen/qwen3-14b`. |
| LiteLLM routing | `config/litellm_config.lmstudio.yaml` → `host.docker.internal:1234/v1` for containers on Windows Docker Desktop. |
| Blog/CMS (original spec) | **Not used:** no self-hosted WordPress container as the publishing target. |
| Site truth + publishing | Marketing dept will **integrate with the production site’s data layer** (read services/solutions; control publishing per agreed API/DB contract — §8). |

---

## 2a. Agents, tools, and “MCP” — speed and execution model

**Principle (matches your diagram):** prompts define **identity**, the LLM supplies **reasoning and language**, and **tools / MCP** supply **real-world power** so agents are *doers*, not only talkers.

**Two different “MCP” layers (do not conflate them):**

| Layer | Role | Examples |
|-------|------|----------|
| **IDE / assistant MCP** | Faster *development* — docs, research, design | Cursor servers (e.g. Context7 for library docs, Exa for research). These help humans and coding agents; they are **not** automatically wired into the shipped CrewAI runtime unless we add a bridge. |
| **Runtime tools in the product** | Fastest *execution* for the marketing pipeline — same process as the API/agents | Python functions in `tools/` (today: `crm_tool`, `web_search_tool`, `seo_audit_tool`, `scrape_tool`). CrewAI calls them **in-process** → minimal latency, no extra JSON-RPC hop. |
| **Runtime MCP servers (optional later)** | Standard **contract** for capabilities shared across apps or owned by another team/service | e.g. a small MCP server that fronts Postgres + site API for “company DB”, or adapters for Mailchimp / GA4 / HubSpot. Use when **multi-client reuse**, **security boundary**, or **vendor-shaped API** justifies the overhead. |

**Speed rule of thumb:** default to **Python tools** on the hot path; introduce **MCP** where an external system or a shared connector boundary clearly wins. We can still **name** capabilities “X MCP” in product docs while implementing them as FastAPI + tools first, then extracting an MCP facade if needed.

**Conceptual map (your list) → implementation in this repo:**

| Agent / subsystem | Your tools / MCPs | This repo (now / planned) |
|-------------------|-------------------|---------------------------|
| **Head** | Company DB, Feedback, Agent control | **Postgres CRM + site sync (§8)** for company/service truth; **workflow state + metrics** in DB/API; head uses `light-model` / `head-model` via LiteLLM. “Agent control” = pipeline status tables + logs (optional future MCP if multiple orchestrators). |
| **Discovery** | Web search, Social search, Directories | **`web_search_tool`** (ddgs) now; social/directory = **future tools** (PRD APIs + rate limits; no Google/Bing keys assumed). IDE: Exa MCP can speed *research while building*, not a substitute for in-app search. |
| **Categorization** | init_db, gauges, get_leads | **Alembic migrations** + **`crm_tool`**; extend models for gauges/tags; optional **`get_leads`-style** thin wrappers for agents. |
| **Analysis & enrichment** | SEO, scrape, social, Apollo | **`seo_audit_tool`**, **`scrape_tool`** now; social monitoring + **Apollo** = **credentialed HTTP tools** when you provide keys. |
| **Outreach** | Email, WhatsApp, CRM, status | **`email_tool` / `whatsapp_tool`** (mock-first per tracker); **CRM** = our Postgres + later HubSpot/Salesforce *adapters* if you want; **`crm_tool`** updates lead status. |
| **Content & media** | Image gen, blog CMS, social APIs | **Site / CMS API (§8)** instead of WordPress container; image/social per `doc7` when enabled. |
| **Feedback** | Mailchimp, CRM, GA4 | **Celery `feedback/`** + **CRM/metrics tables**; Mailchimp/GA4 as **separate tools** with secrets — good MCP *candidates* if we want isolated credentials and reuse. |

**Net:** we align fully with your architecture *semantically*; for **fastest runtime**, we implement most rows as **native Python tools + FastAPI**, and add **MCP servers only** where integration or reuse demands it.

---

## 3. Repository inventory (as of last update)

### Present

| Path | Role |
|------|------|
| `docker-compose.yml` | Postgres (`5433` on host), Redis, LiteLLM (LM Studio config), optional `ollama` profile; WordPress/MySQL profile-gated. |
| `config/litellm_config.yaml` | Ollama-oriented aliases (legacy / alternate). |
| `config/litellm_config.lmstudio.yaml` | **Active path for LiteLLM → LM Studio** model aliases (`head-model`, `discovery-model`, `analysis-model`, `light-model`). |
| `.env`, `.env.example` | Local URLs for DB, LiteLLM, LM Studio hint. |
| `scripts/smoke_test_lm_studio.py` | Verifies `/v1/models` + chat per model (long timeout for 14B). |
| `scripts/real_verification.py` | CLI: real CRM / DuckDuckGo / LM Studio traces (no mocks). |
| `tests/test_live.py` | `@pytest.mark.live`: real DDG + LM Studio when `RUN_LIVE_TESTS=1`. |
| `doc1_PRD.md` … `doc7_environment_config.md` | Requirements and specs. |
| `ide_prompt_updated.md` | Full IDE build prompt / step order. |
| `requirements.txt` | Core deps: FastAPI, SQLAlchemy, Alembic, pytest (agents/ML deps later). |
| `Dockerfile` | Python 3.11 app image for `app` service. |
| `db/models.py`, `db/session.py` | ORM models + session factory (includes `PipelineRun`, `AgentRun`, `LeadEvent`). |
| `crm/` | Extractable CRM module: service, REST `/crm/*`, Jinja UI, `AgentRunRecorder`. |
| `docs/crm/` | CRM README, SCHEMA, API, AGENT_INTEGRATION, CREATION_LOG. |
| `config/settings.py` | Pydantic settings (`DATABASE_URL`, etc.). |
| `api/main.py` | FastAPI: `/health`, `/health/db`, `/crm/*`, `/run/pipeline/minimal`. |
| `migrations/` | Alembic; `20260507_0001_initial_schema` + `20260711_0002_crm_agent_runs`. |
| `tests/test_db.py` | DB connectivity + lead roundtrip (needs `DATABASE_URL`). |
| `tests/test_crm_api.py` | CRM API/UI integration tests (needs Postgres). |
| `main.py` | Local `uvicorn` entry. |
| `agents/lm_client.py`, `agents/discovery_agent.py`, `agents/head_agent.py` | Phase D — OpenAI SDK → LM Studio / LiteLLM; DuckDuckGo-backed Discovery → Head; CRM recorder wired. |
| `workflows/main_pipeline.py` | `run_minimal_marketing_pipeline` entrypoint (non-CrewAI; CrewAI optional Py≥3.10 — see `requirements-agents-crewai.txt`). |
| `scripts/docker_entrypoint.py` | Container migrate + exec (avoids Windows CRLF on shell entrypoint). |
| `scripts/real_verification.py --docker-smoke` | Ordered in-container smoke: tools → LiteLLM → pipeline. |
| `tools/`, `feedback/` | Tools expanding per Phase C/E; `feedback/` still scaffold. |

### Not yet created (required for “complete” system)

- `data/company_kb.json` + seed script for FAISS (or replacement sync from site DB).
- Production-hardening: secrets management, rate limits, robots.txt compliance in scrapers.

---

## 4. Completed work (checklist)

Use this section to mark factual completion; update dates when items change.

- [x] **LM Studio model mapping documented** — Four models mapped to logical roles (head / discovery / analysis / light).
- [x] **`config/litellm_config.lmstudio.yaml`** — Aliases point at LM Studio model IDs; `api_base` uses `host.docker.internal` for Docker↔host.
- [x] **`docker-compose.yml`** — LiteLLM mounts LM Studio config; `extra_hosts` for `host.docker.internal`; Ollama optional via profile `ollama`.
- [x] **`.env.example` extended** — Notes for `LM_STUDIO_BASE_URL`, integration placeholders.
- [x] **`scripts/smoke_test_lm_studio.py`** — Automated connectivity test for LM Studio (adjust timeouts if 14B is slow on CPU).
- [x] **Smoke run (historical)** — Phi / Gemma / Mistral responded; Qwen 14B may need longer timeout or explicit load in LM Studio.
- [x] **Phase B scaffold** — `db/models.py`, Alembic initial migration, `api/main.py`, `Dockerfile`, `app` in `docker-compose.yml`, `tests/test_db.py`, stub packages.
- [x] **Compose** — `wordpress` / `wordpress_db` gated behind profile `wordpress` (default stack excludes them).
- [x] **Validation run (2026-05-10)** — Postgres/Redis healthy, Alembic migrated, `tests/test_db.py` passed with `DATABASE_URL=postgresql://admin:secret@localhost:5433/marketing_db`.

---

## 5. In progress / blocked

| Item | Status | Notes |
|------|--------|------|
| Full Python scaffold | **Phase B done** | Tools, agents, pipeline = next. |
| Phase C tools slice 1 | **Done** | `crm_tool` + `web_search_tool` implemented with tests passing. |
| LiteLLM model health | **Partially healthy** | `phi-2` healthy; larger models require load/warm state in LM Studio. |
| Docker image pulls / compose `up` | **Environment-dependent** | Large pulls; user machine may need time or selective `up` (postgres + redis + litellm only). |
| Site DB / API contract | **Pending user input** | Need DB type, connection pattern (read-only vs publish), or REST surface from Render app. |

---

## 6. Planned work — phased technical steps

Phases align with `ide_prompt_updated.md` but adjusted for **LM Studio** and **no WordPress**.

### Phase A — Infrastructure sanity

1. [x] `docker compose up -d postgres redis litellm app` — stack runs; `app` on Python 3.11 with CrewAI deps.
2. [x] Health checks — postgres/redis/litellm healthy; LiteLLM health requires `Authorization: Bearer dev-key`.
3. [ ] Confirm LiteLLM → LM Studio chat (`light-model`) — **blocked until LM Studio Local Server ON** on host `:1234`.
4. [x] WordPress profile-gated (default stack excludes wordpress).

### Phase B — Application scaffold

1. [x] Create layout from `ide_prompt_updated.md` §1 (`agents/`, `tools/`, `db/`, `api/`, `workflows/`, `feedback/`, `tests/`, `scripts/`, `config/`).
2. [x] `requirements.txt` — core stack first; expand with CrewAI / LiteLLM / scrapers in Phase C.
3. [x] `Dockerfile` + `app` service in compose.
4. [x] `db/models.py` + Alembic + initial migration `20260507_0001`.
5. [x] `config/settings.py` reading `DATABASE_URL`, `LITELLM_BASE_URL`, `LM_STUDIO_BASE_URL`.

### Phase C — Tools (incremental, each with tests)

1. [x] `web_search_tool` (DuckDuckGo).
2. [x] `scrape_tool` (Playwright; `urllib.robotparser` for robots.txt).
3. [x] `seo_audit_tool` (httpx + BeautifulSoup).
4. [x] `crm_tool` (SQLAlchemy → Postgres).
5. [ ] `vector_store_tool` + `seed_vector_db.py` **OR** site-backed ingestion (§8).
6. [ ] `email_tool`, `whatsapp_tool`, `social_publish_tool` — **mock tests first**; real keys only when user provides.
7. [ ] `image_gen_tool` — optional/local GPU; may stay mocked on weak hardware.
8. [ ] **`blog_tool` / publishing tool** — replace WordPress REST with **site integration** (§8).

### Phase D — Agents & pipeline

1. [x] **Minimal pipeline** — Discovery + Head via OpenAI SDK; live verification in host or Docker.
2. [x] **Docker Step 1** — `Dockerfile` (Py3.11, CrewAI, Playwright Chromium); `app` env → `litellm:4000/v1`; `--docker-smoke --skip-llm` **PASSED** in container (2026-05-10).
3. [ ] **CrewAI hierarchical flow** (Step 2) — deps installed in image; implement `workflows/crew_pipeline.py` next.
3. [ ] Additional agents (`categorization_agent`, `analysis_agent`, …) + richer tool wiring (`seo_audit_tool`, `scrape_tool`, CRM mutations).
4. [ ] Integration test with small lead-batch limit; external sends gated behind credentials / dry-run flags.

### Phase E — Feedback & API

1. [ ] Celery app + `run_feedback_system` task.
2. [x] **Department CRM module** (`crm/`) — REST `/crm/*`, Jinja UI `/crm/ui/*`, `pipeline_runs` / `agent_runs` / `lead_events`, agent recorder wired to Discovery + Head (2026-07-14).
3. [ ] FastAPI routes (`/run/pipeline` full, `/company_db`, `/feedback/*`, `/metrics`).
4. [ ] Prometheus scrape config if using Grafana stack.

### Phase F — Site database integration (your stated requirement)

1. [ ] Document **schema or API** from the Render-hosted app (Postgres tables, CMS, or REST).
2. [ ] Read path: sync or query **services, solutions, tiers** into agent context + vector store.
3. [ ] Write path: **publishing controls** (posts, pages, flags) via agreed API or restricted DB role — never ad-hoc full prod admin from agents without audit.
4. [ ] Replace or supplement `data/company_kb.json` with live sync job (scheduled Celery task).

### Phase G — Hardening

1. [ ] Secrets outside `.env` in production; rotate keys.
2. [ ] Rate limiting for scrapers and external APIs (PRD: max 1 req/sec per domain).
3. [ ] Full test suite + CI optional.

---

## 7. Credentials / secrets — when to ask the user

Ask only when enabling the corresponding integration:

| Capability | Typical secrets | Phase |
|------------|-----------------|-------|
| Email | `GMAIL_USER`, `GMAIL_APP_PASSWORD` | C |
| WhatsApp | `WA_PHONE_NUMBER_ID`, `WA_ACCESS_TOKEN` | C |
| LinkedIn / X / Reddit | Per `doc7_environment_config.md` | C |
| Site DB / API | Connection string or API keys; **read vs publish** credentials | F |
| LM Studio | Usually none (local); if remote server, URL + auth | A |

---

## 8. Site database integration — design placeholders

**Requirement:** Marketing department accesses **the site’s database** (or equivalent) to **understand offerings** and **control publishing**.

**Implementation tracks (pick one or hybrid with user):**

1. **Read replica / read-only DB user** — SELECT on content/service tables for embeddings and prompts.
2. **Backend API** on Render — canonical services JSON + authenticated publish endpoints (preferred for safety).
3. **Hybrid** — Read from DB or API; publish only through audited endpoints.

**TODO before coding:** Confirm stack on Render (Postgres? Supabase? Headless CMS?), network path (VPN, IP allowlist, tunnel), and whether publishing is synchronous or queued.

---

## 9. How to update this file

1. After each merge/session: tick boxes in §4–§6, adjust §5 blocked items, bump **Last reviewed** date.
2. Add a one-line entry under **§10 Changelog** with date and short note.

---

## 10. Changelog

| Date | Change |
|------|--------|
| 2026-05-07 | Initial tracker: LM Studio path, no WordPress, site DB requirement, repo inventory, phased roadmap. |
| 2026-05-07 | Phase B: DB models, Alembic, FastAPI health endpoints, Dockerfile, `app` service, WordPress profile, `test_db.py`. |
| 2026-05-10 | Fixed host Postgres port conflict by remapping project DB to `5433`; migrations and DB tests now pass end-to-end. |
| 2026-05-10 | Phase C slice 1 complete: `tools/crm_tool.py`, `tools/web_search_tool.py`, `tests/test_tools.py`; 4 tests passed. |
| 2026-05-10 | Removed DDG mocks; added `tests/test_live.py` + `scripts/real_verification.py` for real DuckDuckGo + LM Studio traces (`RUN_LIVE_TESTS=1`). |
| 2026-05-10 | Step A fix: `web_search_tool` prefers `ddgs`, retries on empty, diagnostic string; `ddgs<9.9` for Python 3.9 compatibility. |
| 2026-05-10 | Phase C slice 2: `seo_audit_tool.py`, `scrape_tool.py`; live tests + `real_verification.py --seo` / `--scrape`. |
| 2026-05-10 | §2a: agent/tool/MCP execution model — in-process Python tools for speed; MCP optional for shared or external integrations; maps Head/Discovery/… diagram to repo. |
| 2026-05-10 | Phase D slice 1: minimal Discovery→Head pipeline (OpenAI SDK + LM Studio); FastAPI `/run/pipeline/minimal`; CrewAI deferred (Py≥3.10). |
| 2026-05-10 | LM Studio compatibility: agent prompts use **user** role only (fix HTTP 400 / Jinja “Only user and assistant roles”). Removed mocked `tests/test_pipeline.py`; pipeline proof is live-only. |
| 2026-05-10 | Docker Step 1: Py3.11 image + CrewAI deps; compose wires `app`→LiteLLM→host LM Studio; `--docker-smoke --skip-llm` passed in container; Phase B LLM smoke pending LM Studio ON. |
| 2026-07-03 | Verification: Phase A docker smoke PASSED again; Phase B blocked — LM Studio Local Server not reachable on host :1234 (phi loaded in UI insufficient without server ON). |
| 2026-07-03 | Phase B phi: light-model chat PASSED; Scout+Head pipeline PASSED (both on phi-2, 3 DDG hits, discovery+head markdown). Prod gemma+qwen pipeline test still pending. |
| 2026-07-11 | Prod multi-LLM: litellm ids aligned to LM Studio (`google_-_gemma-2-9b-it`, `qwen3-14b`); Gemma+Qwen chat + full pipeline PASSED in Docker (~161s). Qwen3 `/no_think` + reasoning_content fallback. |
| 2026-07-14 | Department CRM module: `crm/` service+router+UI+client; migration `20260711_0002`; Discovery persists leads; pipeline/agent runs recorded with `apis_consumed`; docs under `docs/crm/`. |
