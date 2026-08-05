# AI Marketing Department — Full IDE Build Prompt (Updated)

## Constraints
- Every tool, library, API, and service must be FREE or open-source.
- All LLM inference runs locally via Ollama (no OpenAI API costs).
- All storage is local (PostgreSQL + FAISS + Redis).
- Every step includes a debug check and a test before proceeding to the next step.

---

## 0. Project Overview

Build a multi-agent AI Marketing Department using:
- **CrewAI** (orchestration, hierarchical process)
- **LiteLLM** (local model routing to Ollama)
- **Ollama** (local LLM inference — free)
- **PostgreSQL** (CRM and leads database)
- **FAISS + sentence-transformers** (vector DB for company knowledge — free, local)
- **Redis** (Celery task queue)
- **Celery** (background tasks and scheduling)
- **FastAPI** (REST API wrapper)
- **Playwright + BeautifulSoup4** (web scraping — free)
- **DuckDuckGo Search API** (web search — free, no key)
- **Gmail SMTP** (email sending — free)
- **Meta WhatsApp Cloud API** (WhatsApp — free tier, 1000/month)
- **diffusers / Stable Diffusion 2.1** (image generation — free, local)
- **Self-hosted WordPress** (blog CMS — free Docker image)
- **LinkedIn API, Twitter v2 API, Reddit PRAW** (social publishing — all free tiers)
- **Grafana + Prometheus** (monitoring — free)

---

## 1. Folder Structure

Create this exact structure:

```
ai_marketing_dept/
├── agents/
│   ├── __init__.py
│   ├── head_agent.py
│   ├── discovery_agent.py
│   ├── categorization_agent.py
│   ├── analysis_agent.py
│   ├── outreach_agent.py
│   └── content_media_agent.py
├── feedback/
│   ├── __init__.py
│   ├── feedback_system.py
│   └── celery_app.py
├── tools/
│   ├── __init__.py
│   ├── web_search_tool.py       # DuckDuckGo, free
│   ├── scrape_tool.py           # Playwright, free
│   ├── seo_audit_tool.py        # requests + bs4, free
│   ├── crm_tool.py              # SQLAlchemy, free
│   ├── vector_store_tool.py     # FAISS, free
│   ├── email_tool.py            # smtplib Gmail, free
│   ├── whatsapp_tool.py         # Meta Cloud API, free tier
│   ├── image_gen_tool.py        # Stable Diffusion, free local
│   ├── blog_tool.py             # WordPress REST, free
│   └── social_publish_tool.py   # LinkedIn/Twitter/Reddit, free
├── db/
│   ├── __init__.py
│   ├── models.py
│   └── vector_store.py
├── api/
│   ├── __init__.py
│   └── main.py
├── workflows/
│   ├── __init__.py
│   ├── tasks.yaml
│   └── main_pipeline.py
├── scripts/
│   ├── seed_vector_db.py
│   └── startup.sh
├── tests/
│   ├── __init__.py
│   ├── test_tools.py
│   ├── test_agents.py
│   ├── test_pipeline.py
│   └── test_feedback.py
├── config/
│   ├── litellm_config.yaml
│   ├── logging.yaml
│   └── prometheus.yml
├── data/
│   └── company_kb.json          # seed data for VectorDB
├── logs/
├── static/
│   └── images/
├── migrations/                  # Alembic
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env
├── .env.example
└── main.py
```

---

## 2. Step-by-Step Build Order (with Debugging and Testing)

### STEP 1 — Start Infrastructure Containers

**Build:**
```bash
docker-compose up -d postgres redis ollama litellm wordpress wordpress_db
```

**Debug checks:**
```bash
# Check all containers are healthy
docker-compose ps
# Expected: all show "healthy" or "running"

# Test PostgreSQL
docker-compose exec postgres pg_isready -U admin -d marketing_db
# Expected: marketing_db - accepting connections

# Test Redis
docker-compose exec redis redis-cli ping
# Expected: PONG

# Test Ollama
curl http://localhost:11434/api/tags
# Expected: JSON response with empty models list

# Test LiteLLM
curl http://localhost:4000/health
# Expected: {"status": "healthy"}
```

**DO NOT proceed to Step 2 until all health checks pass.**

---

### STEP 2 — Pull Local LLM Models via Ollama

**Build:**
```bash
docker-compose exec ollama ollama pull qwen3:14b
docker-compose exec ollama ollama pull mistral:7b
docker-compose exec ollama ollama pull phi
docker-compose exec ollama ollama pull qwen:1.8b
```

**Debug checks:**
```bash
# List all pulled models
curl http://localhost:11434/api/tags | python3 -m json.tool
# Expected: models array contains qwen3:14b, mistral:7b, phi, qwen:1.8b

# Test inference for each model
curl http://localhost:11434/api/generate \
  -d '{"model": "phi", "prompt": "Reply only: OK", "stream": false}'
# Expected: response field contains text

curl http://localhost:11434/api/generate \
  -d '{"model": "mistral:7b", "prompt": "Reply only: OK", "stream": false}'
# Expected: response field contains text
```

**Test via LiteLLM:**
```bash
curl http://localhost:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "light-model", "messages": [{"role":"user","content":"Reply only: OK"}]}'
# Expected: choices[0].message.content not empty
```

**DO NOT proceed to Step 3 until all 4 models respond correctly.**

---

### STEP 3 — Database Schema and Migrations

**Build:**

Create `db/models.py` with SQLAlchemy ORM:

```python
from sqlalchemy import Column, String, Float, Integer, Boolean, JSON, Text, Enum, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase
import enum, uuid
from datetime import datetime

class Base(DeclarativeBase):
    pass

class LeadStatus(str, enum.Enum):
    raw = "raw"
    categorized = "categorized"
    enriched = "enriched"
    contacted = "contacted"
    converted = "converted"
    unreachable = "unreachable"
    low_priority = "low_priority"

class Lead(Base):
    __tablename__ = "leads"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(256))
    url = Column(String(512), unique=True)
    country = Column(String(64))
    industry = Column(String(128))
    business_type = Column(String(64))
    email = Column(String(256))
    phone = Column(String(64))
    seo_score = Column(Integer)
    automation_gaps = Column(JSON)
    social_engagement = Column(JSON)
    weaknesses = Column(JSON)
    lead_score = Column(Float, default=0.0)
    status = Column(Enum(LeadStatus), default=LeadStatus.raw)
    status_notes = Column(Text)
    source = Column(String(64))
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)

class OutreachRecord(Base):
    __tablename__ = "outreach_records"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id = Column(UUID(as_uuid=True), nullable=False)
    channel = Column(String(32))
    to_address = Column(String(256))
    subject = Column(String(512))
    message_text = Column(Text)
    sent_at = Column(TIMESTAMP)
    opened = Column(Boolean, default=False)
    replied = Column(Boolean, default=False)
    converted = Column(Boolean, default=False)

class CompanyKnowledge(Base):
    __tablename__ = "company_knowledge"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type = Column(String(32))   # service / blog / solution
    title = Column(String(256))
    content = Column(Text)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)

class CampaignMetric(Base):
    __tablename__ = "campaign_metrics"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    date = Column(TIMESTAMP, default=datetime.utcnow)
    open_rate = Column(Float)
    reply_rate = Column(Float)
    conversion_rate = Column(Float)
    top_segment = Column(JSON)
    strategy_notes = Column(Text)

class TaskLog(Base):
    __tablename__ = "task_log"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_name = Column(String(64))
    task_id = Column(String(128))
    started_at = Column(TIMESTAMP)
    finished_at = Column(TIMESTAMP)
    status = Column(String(16))
    records_processed = Column(Integer)
    error_message = Column(Text)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
```

**Run migrations:**
```bash
docker-compose run --rm app alembic init migrations
docker-compose run --rm app alembic revision --autogenerate -m "initial_schema"
docker-compose run --rm app alembic upgrade head
```

**Debug checks:**
```bash
docker-compose exec postgres psql -U admin -d marketing_db -c "\dt"
# Expected: lists leads, outreach_records, company_knowledge, campaign_metrics, task_log

docker-compose exec postgres psql -U admin -d marketing_db \
  -c "SELECT column_name FROM information_schema.columns WHERE table_name='leads';"
# Expected: all Lead columns listed
```

**Test:**
```python
# tests/test_db.py
def test_lead_insert_and_read(db_session):
    lead = Lead(name="Test Co", url="https://test.com", status=LeadStatus.raw)
    db_session.add(lead)
    db_session.commit()
    found = db_session.query(Lead).filter_by(name="Test Co").first()
    assert found is not None
    assert found.status == LeadStatus.raw

# Run:
# docker-compose run --rm app pytest tests/test_db.py -v
```

**DO NOT proceed to Step 4 until all 5 tables exist and the test passes.**

---

### STEP 4 — Build and Test Each Tool Individually

Build each tool file. After each tool, run its isolated test before building the next.

#### 4a. web_search_tool

```python
# tools/web_search_tool.py
from duckduckgo_search import DDGS
from crewai.tools import tool

@tool("Web Search Tool")
def web_search_tool(query: str, max_results: int = 10) -> list:
    """Search web via DuckDuckGo. Returns list of {title, url, snippet}."""
    with DDGS() as ddgs:
        return [{"title": r["title"], "url": r["href"], "snippet": r["body"]}
                for r in ddgs.text(query, max_results=max_results)]
```

**Test:**
```bash
docker-compose run --rm app python -c "
from tools.web_search_tool import web_search_tool
results = web_search_tool('tech startups Tunisia')
assert len(results) > 0, 'No results returned'
assert 'url' in results[0], 'Missing url key'
print(f'PASS: {len(results)} results returned')
print(f'Sample: {results[0][\"url\"]}')
"
```

#### 4b. scrape_tool

```bash
docker-compose run --rm app playwright install chromium

docker-compose run --rm app python -c "
import asyncio
from tools.scrape_tool import scrape_tool
result = asyncio.run(scrape_tool('https://example.com'))
assert 'emails' in result, 'Missing emails key'
assert 'title' in result, 'Missing title key'
print(f'PASS: title={result[\"title\"]}, emails={result[\"emails\"]}')
"
```

#### 4c. seo_audit_tool

```bash
docker-compose run --rm app python -c "
from tools.seo_audit_tool import seo_audit_tool
result = seo_audit_tool('https://example.com')
assert 'seo_score' in result
assert 0 <= result['seo_score'] <= 100
print(f'PASS: score={result[\"seo_score\"]}, issues={result[\"issues\"]}')
"
```

#### 4d. crm_tool

```bash
docker-compose run --rm app python -c "
from tools.crm_tool import crm_write_tool, crm_read_tool
row_id = crm_write_tool('leads', {'name': 'Debug Co', 'url': 'https://debugco.com', 'status': 'raw'})
assert 'inserted:' in row_id
leads = crm_read_tool(status='raw', limit=5)
assert any(l['name'] == 'Debug Co' for l in leads)
print(f'PASS: inserted {row_id}, found in read query')
"
```

#### 4e. vector_store_tool

```bash
# First seed VectorDB with company data
docker-compose run --rm app python scripts/seed_vector_db.py

docker-compose run --rm app python -c "
from tools.vector_store_tool import vector_store_search
results = vector_store_search('company has no chatbot or automation')
assert len(results) > 0
assert 'title' in results[0]
print(f'PASS: matched service = {results[0][\"title\"]} (score={results[0][\"score\"]:.3f})')
"
```

#### 4f. smtp_email_tool (dry-run mock)

```bash
docker-compose run --rm app pytest tests/test_tools.py::test_smtp_email_tool_mock -v
# Expected: PASSED
```

#### 4g. meta_whatsapp_tool (mock)

```bash
docker-compose run --rm app pytest tests/test_tools.py::test_meta_whatsapp_tool_mock -v
# Expected: PASSED
```

#### 4h. stable_diffusion_tool

```bash
docker-compose run --rm app python -c "
import os
from tools.image_gen_tool import stable_diffusion_tool
path = stable_diffusion_tool('a minimal blue tech logo', '512x512')
assert os.path.exists(path)
assert path.endswith('.png')
print(f'PASS: image saved at {path}')
"
# Note: first run downloads SD model (~4GB). Takes 2-10 min.
```

#### 4i. wordpress_rest_tool

```bash
# WordPress must be running and configured
docker-compose run --rm app python -c "
from tools.blog_tool import wordpress_rest_tool
result = wordpress_rest_tool('Debug Post', '## Hello\nThis is a test.', ['test'])
assert 'post_id' in result
assert 'url' in result
print(f'PASS: post_id={result[\"post_id\"]}, url={result[\"url\"]}')
"
```

#### 4j. social_publish_tool

```bash
docker-compose run --rm app pytest tests/test_tools.py::test_social_tools_mock -v
# Expected: all social tool mocks PASSED
```

**DO NOT proceed to Step 5 until every tool test above passes.**

---

### STEP 5 — Build Each Agent

Build each agent file in `agents/`. Use CrewAI `Agent` class.

**Agent base pattern:**
```python
# agents/discovery_agent.py
from crewai import Agent
from tools.web_search_tool import web_search_tool
from tools.scrape_tool import scrape_tool
from tools.crm_tool import crm_write_tool
from config.settings import LITELLM_BASE_URL

discovery_agent = Agent(
    role="Prospect Scout",
    goal=(
        "Find startups, stores, and companies that may need tech solutions. "
        "Use web and directory search tools. "
        "Output structured JSON lead lists with name, url, country, industry."
    ),
    backstory="You are DiscoveryAgent. Curious, fast, data-driven. You find businesses that need tech help.",
    llm=f"openai/discovery-model",   # LiteLLM alias resolves to qwen:1.8b via Ollama
    tools=[web_search_tool, scrape_tool, crm_write_tool],
    allow_delegation=False,
    verbose=True,
    max_iter=5,
    memory=False
)
```

Repeat the same pattern for: categorization_agent, analysis_agent, outreach_agent, content_media_agent.

**HeadAgent:**
```python
from crewai import Agent
from tools.vector_store_tool import vector_store_search
from tools.crm_tool import crm_read_tool
from tools.blog_tool import wordpress_rest_tool

head_agent = Agent(
    role="Strategic Marketing Supervisor",
    goal=(
        "Align all marketing actions with company services and solutions. "
        "Supervise all subordinate agents. Inspect their outputs. "
        "Match prospect weaknesses to company services using semantic search. "
        "Issue precise instructions to OutreachAgent and ContentMediaAgent. "
        "Update strategies based on feedback metrics."
    ),
    backstory=(
        "You are HeadAgent of The Next Level Tech Company. "
        "You have full access to the company knowledge base. "
        "You are analytical, decisive, and adaptive."
    ),
    llm="openai/head-model",
    tools=[vector_store_search, crm_read_tool, wordpress_rest_tool],
    allow_delegation=True,
    verbose=True,
    memory=True   # HeadAgent retains context across tasks
)
```

**Debug check per agent:**
```bash
docker-compose run --rm app python -c "
from agents.discovery_agent import discovery_agent
print(f'PASS: {discovery_agent.role} loaded')
print(f'Tools: {[t.name for t in discovery_agent.tools]}')
"
# Repeat for each agent
```

**Test single agent task (isolated):**
```python
# tests/test_agents.py
from crewai import Task

def test_discovery_agent_task(discovery_agent):
    task = Task(
        description="Find 3 e-commerce companies in Tunisia. Return a JSON list.",
        expected_output="JSON array of 3 leads with name and url fields.",
        agent=discovery_agent
    )
    result = task.execute()
    assert result is not None
    assert len(result) > 10   # non-empty string
    print(f"Discovery result sample: {result[:200]}")
```

```bash
docker-compose run --rm app pytest tests/test_agents.py::test_discovery_agent_task -v -s
```

**DO NOT proceed to Step 6 until all 6 agent import tests pass.**

---

### STEP 6 — Build Workflow Pipeline

**Build `workflows/main_pipeline.py`:**

```python
from crewai import Crew, Task, Process
from agents.head_agent import head_agent
from agents.discovery_agent import discovery_agent
from agents.categorization_agent import categorization_agent
from agents.analysis_agent import analysis_agent
from agents.outreach_agent import outreach_agent
from agents.content_media_agent import content_media_agent

def create_pipeline(industry: str, country: str, limit: int = 10):
    discovery_task = Task(
        description=f"Find {limit} companies in {industry} sector in {country}. Output JSON list.",
        expected_output="JSON array of leads with: name, url, industry, source.",
        agent=discovery_agent
    )
    categorization_task = Task(
        description="Categorize all raw leads in CRM by country, industry, business_type. Update status to categorized.",
        expected_output="Count of categorized leads as confirmation string.",
        agent=categorization_agent,
        context=[discovery_task]
    )
    analysis_task = Task(
        description="Enrich all categorized leads: SEO audit, contact extraction, automation gap detection, lead_score. Set status=enriched.",
        expected_output="JSON array of enriched profiles.",
        agent=analysis_agent,
        context=[categorization_task]
    )
    head_review_task = Task(
        description=(
            "Review enriched leads. Search VectorDB for matching services per lead weakness. "
            "Approve leads with lead_score >= 60. "
            "Output JSON: {approved_leads: [{lead_id, weakness_summary, matched_services, channel_priority}], content_brief: {...}}"
        ),
        expected_output="JSON with approved_leads array and content_brief object.",
        agent=head_agent,
        context=[analysis_task]
    )
    outreach_task = Task(
        description=(
            "For each lead in approved_leads, write a personalized email (200 words max) and/or WhatsApp (80 words max). "
            "Send via specified channel. Log to OutreachRecord."
        ),
        expected_output="JSON array of OutreachRecord entries (lead_id, channel, sent_at).",
        agent=outreach_agent,
        context=[head_review_task]
    )
    content_task = Task(
        description=(
            "Using content_brief from HeadAgent, write one blog post, generate one image via Stable Diffusion, "
            "write captions for LinkedIn/Twitter/Reddit. Publish blog to WordPress. Schedule social posts."
        ),
        expected_output="Blog URL and list of scheduled social posts.",
        agent=content_media_agent,
        context=[head_review_task]
    )

    crew = Crew(
        agents=[head_agent, discovery_agent, categorization_agent,
                analysis_agent, outreach_agent, content_media_agent],
        tasks=[discovery_task, categorization_task, analysis_task,
               head_review_task, outreach_task, content_task],
        process=Process.hierarchical,
        manager_agent=head_agent,
        verbose=True
    )
    return crew
```

**Debug check:**
```bash
docker-compose run --rm app python -c "
from workflows.main_pipeline import create_pipeline
crew = create_pipeline('e-commerce', 'TN', limit=3)
print(f'PASS: Crew created with {len(crew.agents)} agents and {len(crew.tasks)} tasks')
"
```

**Pipeline integration test (3 leads, end-to-end):**
```bash
docker-compose run --rm app python -c "
from workflows.main_pipeline import create_pipeline
crew = create_pipeline('e-commerce', 'TN', limit=3)
result = crew.kickoff()
print('=== Pipeline Result ===')
print(result)
"
# Watch logs. Expected: each task completes, leads appear in DB, outreach logged.
```

**Verify results in DB:**
```bash
docker-compose exec postgres psql -U admin -d marketing_db \
  -c "SELECT name, status, lead_score, email FROM leads ORDER BY created_at DESC LIMIT 10;"

docker-compose exec postgres psql -U admin -d marketing_db \
  -c "SELECT lead_id, channel, sent_at FROM outreach_records ORDER BY sent_at DESC LIMIT 5;"
```

**DO NOT proceed to Step 7 until the pipeline completes and DB rows are visible.**

---

### STEP 7 — Build FeedbackSystem

**Build `feedback/feedback_system.py`:**

```python
from feedback.celery_app import celery_app
from tools.crm_tool import crm_read_tool, crm_write_tool
from db.models import CampaignMetric
from sqlalchemy import create_engine, text
import os, logging
from datetime import datetime, timedelta

@celery_app.task(name="run_feedback_system")
def run_feedback_system():
    logging.info("FeedbackSystem starting...")
    engine = create_engine(os.getenv("DATABASE_URL"))

    with engine.connect() as conn:
        # Compute metrics for last 7 days
        rows = conn.execute(text("""
            SELECT
                COUNT(*) as total,
                AVG(CASE WHEN opened THEN 1 ELSE 0 END) as open_rate,
                AVG(CASE WHEN replied THEN 1 ELSE 0 END) as reply_rate,
                AVG(CASE WHEN converted THEN 1 ELSE 0 END) as conversion_rate
            FROM outreach_records
            WHERE sent_at > NOW() - INTERVAL '7 days'
        """)).fetchone()

        open_rate = float(rows[1] or 0)
        reply_rate = float(rows[2] or 0)
        conversion_rate = float(rows[3] or 0)

        # Update lead scores
        conn.execute(text("""
            UPDATE leads l SET lead_score = lead_score + 10
            WHERE id IN (SELECT lead_id FROM outreach_records WHERE converted = true)
        """))
        conn.execute(text("""
            UPDATE leads l SET lead_score = lead_score + 5
            WHERE id IN (SELECT lead_id FROM outreach_records WHERE replied = true)
        """))
        conn.execute(text("""
            UPDATE leads l SET lead_score = GREATEST(0, lead_score - 5)
            WHERE id IN (
                SELECT lead_id FROM outreach_records
                WHERE opened = false AND sent_at < NOW() - INTERVAL '3 days'
            )
        """))
        conn.commit()

        # Write daily metric
        conn.execute(text("""
            INSERT INTO campaign_metrics (open_rate, reply_rate, conversion_rate, strategy_notes)
            VALUES (:o, :r, :c, :notes)
        """), {
            "o": open_rate, "r": reply_rate, "c": conversion_rate,
            "notes": f"Auto-generated. Open={open_rate:.2%} Reply={reply_rate:.2%} Convert={conversion_rate:.2%}"
        })
        conn.commit()

    logging.info(f"FeedbackSystem complete: open={open_rate:.2%} reply={reply_rate:.2%}")
    return {"open_rate": open_rate, "reply_rate": reply_rate, "conversion_rate": conversion_rate}
```

**Build `feedback/celery_app.py`:**
```python
from celery import Celery
from celery.schedules import crontab
import os

celery_app = Celery("marketing", broker=os.getenv("CELERY_BROKER_URL"))
celery_app.conf.beat_schedule = {
    "daily-feedback": {
        "task": "run_feedback_system",
        "schedule": crontab(hour=7, minute=0)
    }
}
```

**Debug and test:**
```bash
# Start Celery worker and beat
docker-compose up -d celery_worker celery_beat

# Manually trigger FeedbackSystem (no need to wait for 07:00)
docker-compose run --rm app python -c "
from feedback.feedback_system import run_feedback_system
result = run_feedback_system()
print(f'PASS: FeedbackSystem result = {result}')
"

# Verify CampaignMetric row was written
docker-compose exec postgres psql -U admin -d marketing_db \
  -c "SELECT * FROM campaign_metrics ORDER BY date DESC LIMIT 1;"
```

---

### STEP 8 — Build FastAPI REST Layer

**Build `api/main.py`:**

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from workflows.main_pipeline import create_pipeline
from tools.crm_tool import crm_read_tool, crm_write_tool
from db.vector_store import add_to_vector_store
from feedback.feedback_system import run_feedback_system
from prometheus_client import make_asgi_app, Counter, Histogram
import logging

app = FastAPI(title="AI Marketing Department API")

# Mount Prometheus metrics
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

pipeline_runs = Counter("pipeline_runs_total", "Total pipeline runs")
task_duration = Histogram("task_duration_seconds", "Task duration", ["agent"])

class PipelineRequest(BaseModel):
    industry: str
    country: str
    limit: int = 10

class KnowledgeRequest(BaseModel):
    type: str          # service / blog / solution
    title: str
    content: str

@app.post("/run/pipeline")
async def run_pipeline(req: PipelineRequest):
    pipeline_runs.inc()
    crew = create_pipeline(req.industry, req.country, req.limit)
    result = crew.kickoff()
    return {"status": "completed", "result": str(result)[:500]}

@app.get("/leads")
async def get_leads(status: str = None, min_score: float = 0.0, limit: int = 50):
    leads = crm_read_tool(status=status, limit=limit)
    if min_score > 0:
        leads = [l for l in leads if (l.get("lead_score") or 0) >= min_score]
    return {"leads": leads, "count": len(leads)}

@app.post("/company_db")
async def add_company_knowledge(req: KnowledgeRequest):
    row_id = crm_write_tool("company_knowledge", {
        "type": req.type, "title": req.title, "content": req.content
    })
    add_to_vector_store(req.title, req.content)
    return {"status": "added", "id": row_id}

@app.get("/feedback/latest")
async def get_latest_feedback():
    rows = crm_read_tool.__wrapped__("SELECT * FROM campaign_metrics ORDER BY date DESC LIMIT 1")
    return rows[0] if rows else {"message": "No feedback yet"}

@app.post("/feedback/run")
async def trigger_feedback():
    result = run_feedback_system()
    return {"status": "completed", "metrics": result}
```

**Debug and test:**
```bash
docker-compose up -d app

# Health check
curl http://localhost:8000/docs
# Expected: FastAPI Swagger UI loads

# Test leads endpoint
curl "http://localhost:8000/leads?limit=5"
# Expected: JSON with leads array

# Test pipeline trigger
curl -X POST http://localhost:8000/run/pipeline \
  -H "Content-Type: application/json" \
  -d '{"industry": "retail", "country": "DZ", "limit": 3}'
# Expected: {"status": "completed", "result": "..."}

# Test Prometheus metrics
curl http://localhost:8000/metrics | grep pipeline_runs
# Expected: pipeline_runs_total line
```

---

### STEP 9 — Run Full Test Suite

```bash
docker-compose run --rm app pytest tests/ -v --tb=short 2>&1 | tee logs/test_results.log
```

**Expected output:**
```
tests/test_tools.py::test_web_search_tool              PASSED
tests/test_tools.py::test_scrape_tool                  PASSED
tests/test_tools.py::test_seo_audit_tool               PASSED
tests/test_tools.py::test_crm_roundtrip                PASSED
tests/test_tools.py::test_vector_store_search          PASSED
tests/test_tools.py::test_smtp_email_tool_mock         PASSED
tests/test_tools.py::test_meta_whatsapp_tool_mock      PASSED
tests/test_tools.py::test_stable_diffusion_tool        PASSED
tests/test_tools.py::test_wordpress_rest_tool          PASSED
tests/test_tools.py::test_social_tools_mock            PASSED
tests/test_agents.py::test_discovery_agent_task        PASSED
tests/test_agents.py::test_categorization_agent_task   PASSED
tests/test_agents.py::test_analysis_agent_task         PASSED
tests/test_agents.py::test_head_agent_task             PASSED
tests/test_agents.py::test_outreach_agent_task         PASSED
tests/test_agents.py::test_content_agent_task          PASSED
tests/test_pipeline.py::test_full_pipeline_3_leads     PASSED
tests/test_feedback.py::test_feedback_system_run       PASSED

18 passed, 0 failed
```

**If any test fails:**
1. Read the error traceback.
2. Check the relevant container logs: `docker-compose logs app`
3. Check Ollama: `docker-compose logs ollama`
4. Fix the failing component.
5. Re-run only that test: `pytest tests/test_tools.py::failing_test -v -s`
6. Do not proceed until 0 failures.

---

### STEP 10 — Setup Monitoring

```bash
docker-compose up -d grafana prometheus

# Open Grafana
# URL: http://localhost:3000
# Login: admin / admin

# Import dashboards:
# LiteLLM:    Dashboard ID 18457
# PostgreSQL: Dashboard ID 9628
# Redis:      Dashboard ID 11835
```

**Add Prometheus datasource in Grafana:**
- URL: http://prometheus:9090
- Name: Prometheus

**Create custom panel for pipeline funnel:**
- Query: `SELECT status, COUNT(*) FROM leads GROUP BY status`
- Visualization: Bar chart

---

### STEP 11 — Production Deployment

```bash
# Build production image
docker-compose -f docker-compose.yml build

# Set DEBUG=false in .env

# Start all services
docker-compose up -d

# Verify all containers healthy
docker-compose ps

# Set up daily pipeline cron (alternative to manual trigger)
# Add to crontab:
# 0 8 * * * curl -X POST http://localhost:8000/run/pipeline \
#   -d '{"industry":"e-commerce","country":"TN","limit":20}'
```

---

## 3. Model Allocation Reference

| Agent | Model alias | Ollama model |
|---|---|---|
| HeadAgent | head-model | qwen3:14b |
| DiscoveryAgent | discovery-model | qwen:1.8b |
| CategorizationAgent | light-model | phi |
| AnalysisAgent | analysis-model | mistral:7b |
| OutreachAgent | analysis-model | mistral:7b |
| ContentMediaAgent | analysis-model | mistral:7b |
| FeedbackSystem | light-model | phi |

---

## 4. Free API Setup Checklist

```
[ ] Gmail SMTP app password: Google Account > Security > 2FA > App Passwords
[ ] Meta WhatsApp Cloud API: developers.facebook.com > New App > WhatsApp > free tier
[ ] LinkedIn API: linkedin.com/developers > Create App > Marketing Developer Platform (free)
[ ] Twitter v2 API: developer.twitter.com > Free plan (500 posts/month)
[ ] Reddit API: reddit.com/prefs/apps > Create app (free)
[ ] Google Analytics 4: analytics.google.com (free) + Service Account for API access
[ ] WordPress Application Password: WP Admin > Users > Profile > Application Passwords
```

---

## 5. What Each Free Tool Replaces

| Paid tool replaced | Free alternative used |
|---|---|
| OpenAI API | Ollama (local LLMs) |
| SerpAPI | DuckDuckGo Search (no key) |
| Twilio WhatsApp | Meta Cloud API free tier |
| SendGrid | Gmail SMTP (smtplib) |
| DALL·E | Stable Diffusion 2.1 (local) |
| Hootsuite | Direct platform APIs |
| Mailchimp | Listmonk (optional) or GA4 only |
| Weaviate Cloud | FAISS (local) |
| Ahrefs / SEMrush | Custom requests + bs4 SEO checker |
| Crunchbase Pro | Playwright scraping public pages |
