# NextLevel AI Marketing Department — Architecture Report

## 1. Overview
**Purpose**: Automate B2B marketing (discovery → outreach → content) using multi-agent AI.
**Stack**: FastAPI, PostgreSQL, LM Studio (local LLMs), Docker, DuckDuckGo, Meta Ads, Playwright.
**Constraints**: No paid APIs, local LLMs only, Tunisia-focused.

---

## 2. Architecture Diagram
```mermaid
flowchart TD
    subgraph Agents
        Discovery[Discovery Agent
Web Search + Meta Ads] -->|Leads| Head
        Head[Head Agent
Synthesis + Tool Assignment] -->|Plan| Qualifier
        Qualifier[Qualifier Agent
Lead Scoring] -->|Scores| CRM
    end

    subgraph Tools
        WebSearch[web_search_tool
DuckDuckGo] --> Discovery
        MetaAds[meta_ads_tool
Meta Ad Library] --> Discovery
        SEO[seo_audit_tool] --> Discovery
        Scrape[scrape_tool
Playwright] --> Discovery
        CRMTool[crm_tool
PostgreSQL] --> Discovery
        GoogleMaps[google_maps_tool
(Planned)] --> Discovery
    end

    subgraph External
        LMStudio[LM Studio
Local LLMs] -->|Chat| Agents
        DuckDuckGo --> WebSearch
        MetaAPI[Meta Ad Library] --> MetaAds
        GoogleAPI[Google Maps API] --> GoogleMaps
    end

    CRM[CRM Module
PostgreSQL + REST/UI] -->|Leads/Runs| Agents
    SiteDB[Site Database
(Planned)] -->|Services| Agents

    style Discovery fill:#f9f,stroke:#333
    style Head fill:#bbf,stroke:#333
    style Qualifier fill:#f96,stroke:#333
```

---

## 3. Key Components

### Agents (`agents/`)
| Agent       | Role                                                                 | Tools Used                          | Output                     |
|-------------|----------------------------------------------------------------------|-------------------------------------|----------------------------|
| Discovery   | Finds leads via web search + Meta Ads                                | `web_search`, `meta_ads`, `crm_write` | Leads + Report             |
| Head        | Synthesizes leads, assigns tools, plans next steps                  | `llm_chat`                          | Markdown Report + Tool Plan |
| Qualifier   | Scores leads against company profile                                 | `llm_chat`                          | Lead Scores                |

### Tools (`tools/`)
| Tool               | Purpose                                      | External Dependency       |
|--------------------|-----------------------------------------------|---------------------------|
| `web_search_tool`  | DuckDuckGo search                            | DuckDuckGo                |
| `meta_ads_tool`   | Meta Ad Library (businesses running ads)     | Meta API                  |
| `crm_tool`        | Write leads to PostgreSQL                    | PostgreSQL                |
| `seo_audit_tool`  | SEO analysis                                 | httpx + BeautifulSoup     |
| `scrape_tool`     | Playwright web scraping                      | Playwright                |
| `google_maps_tool`| **Planned**: Geocoding/places/routes          | Google Maps API           |

### CRM (`crm/`)
- **Models**: `Lead`, `AgentRun`, `PipelineRun`, `AgentProfile`, `LeadEvent`.
- **API**: REST endpoints (`/crm/leads`, `/crm/runs`).
- **UI**: Jinja templates (`/crm/ui/leads`).

### Pipeline (`workflows/main_pipeline.py`)
```python
def run_minimal_marketing_pipeline(seed_query: str):
    discovery = DiscoveryAgent().run(seed_query)
    head_report = HeadAgent().run(discovery)
    qualifications = QualifierAgent().qualify_batch(discovery.lead_ids)
    return {"discovery": discovery, "head_report": head_report, "qualifications": qualifications}
```

### Database (`db/models.py`)
- **Leads**: Company details, SEO scores, status.
- **Agent Runs**: Model used, input/output, APIs consumed.
- **Pipeline Runs**: Trigger, seed query, status.

---

## 4. Gap Analysis vs. PRD (`doc1_PRD.md`)

| PRD Requirement                          | Status          | Notes                                                                 |
|------------------------------------------|-----------------|-----------------------------------------------------------------------|
| No paid APIs                            | ✅ Implemented  | DuckDuckGo (free), Meta Ads (free tier), local LLMs.                 |
| Local LLM inference                      | ✅ Implemented  | LM Studio + LiteLLM proxy.                                            |
| Lead discovery (≥20 per scan)            | ⚠️ Partial      | Works but needs Google Maps for local businesses.                    |
| Outreach (email/WhatsApp)                | ❌ Missing      | Planned: `email_tool`, `whatsapp_tool`.                               |
| Content publishing (blog/social)        | ❌ Missing      | Planned: Site DB integration + `social_publish_tool`.                |
| Feedback loop (daily metrics)           | ❌ Missing      | Planned: Celery + CRM metrics.                                        |
| Site DB integration                      | ❌ Missing      | Requires Render app schema/API.                                       |
| MCP servers (shared capabilities)        | ❌ Missing      | Planned: `company_db_mcp`, `feedback_mcp`.                           |

---

## 5. Roadmap

### Phase 1: Immediate Fixes (1–2 Days)
1. **Upgrade to Python 3.11** (Docker + local env).
2. **Fix LM Studio connectivity** (ensure `http://127.0.0.1:1234` is running).
3. **Add Google Maps tool** (`google_maps_tool.py`).
4. **Test pipeline** with real leads (Tunisia startups).

### Phase 2: Core Enhancements (1 Week)
1. **Implement outreach tools** (`email_tool`, `whatsapp_tool`).
2. **Add feedback loop** (Celery + CRM metrics).
3. **Integrate site DB** (read services, write publishing controls).
4. **Add MCP servers** (`company_db_mcp`, `feedback_mcp`).

### Phase 3: Scaling (2 Weeks)
1. **Multi-agent orchestration** (CrewAI or custom).
2. **Rate limiting** (1 req/sec per domain).
3. **Monitoring** (Prometheus + Grafana).
4. **Deployment** (Render/self-hosted).

---

## 6. Critical Blockers
1. **Python 3.9 → 3.11**: Required for CrewAI and graphify.
2. **LM Studio**: Must be running for LLM inference.
3. **Site DB Contract**: Need schema/API from Render app.

---

## 7. Recommendations
1. **Prioritize Phase 1** to unblock testing.
2. **Add Google Maps tool** to improve lead discovery.
3. **Mock outreach tools** first (avoid API keys until ready).
4. **Use MCP servers** only for shared capabilities (e.g., site DB).