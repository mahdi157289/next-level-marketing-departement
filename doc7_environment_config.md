# Doc 7 — Environment & Configuration Files

---

## 7.1 .env File (All Environment Variables)

```env
# ─── Database ───────────────────────────────────────────
DATABASE_URL=postgresql://admin:secret@localhost:5432/marketing_db

# ─── LiteLLM ────────────────────────────────────────────
LITELLM_BASE_URL=http://localhost:4000

# ─── Ollama ─────────────────────────────────────────────
OLLAMA_BASE_URL=http://localhost:11434

# ─── Email (Gmail SMTP — free with app password) ────────
GMAIL_USER=yourmail@gmail.com
GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx   # Google account > Security > App Passwords

# ─── WhatsApp (Meta Cloud API — free tier) ───────────────
WA_PHONE_NUMBER_ID=your_phone_number_id
WA_ACCESS_TOKEN=your_meta_access_token

# ─── LinkedIn API (free) ────────────────────────────────
LINKEDIN_ACCESS_TOKEN=your_linkedin_token
LINKEDIN_ORG_ID=your_org_id

# ─── Twitter/X API v2 (free — 500 posts/month) ──────────
TWITTER_API_KEY=your_key
TWITTER_API_SECRET=your_secret
TWITTER_ACCESS_TOKEN=your_token
TWITTER_ACCESS_SECRET=your_token_secret

# ─── Reddit API (free via PRAW) ─────────────────────────
REDDIT_CLIENT_ID=your_client_id
REDDIT_CLIENT_SECRET=your_client_secret
REDDIT_USERNAME=your_username
REDDIT_PASSWORD=your_password

# ─── WordPress self-hosted (free Docker) ────────────────
WP_API_URL=http://localhost:8080
WP_USER=admin
WP_APP_PASSWORD=xxxx xxxx xxxx xxxx   # WordPress > Users > Application Passwords

# ─── Google Analytics 4 (free API) ──────────────────────
GA4_PROPERTY_ID=123456789
GA4_SERVICE_ACCOUNT_JSON=/app/config/ga4_service_account.json

# ─── Celery / Redis ──────────────────────────────────────
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1

# ─── Stable Diffusion (local, free) ─────────────────────
SD_MODEL_ID=stabilityai/stable-diffusion-2-1
SD_DEVICE=cuda    # or "cpu" if no GPU

# ─── App ─────────────────────────────────────────────────
APP_PORT=8000
DEBUG=true
LOG_LEVEL=INFO
MAX_EMAILS_PER_DAY=20
MIN_LEAD_SCORE_FOR_OUTREACH=60
OUTREACH_COOLDOWN_DAYS=30
```

---

## 7.2 requirements.txt (All Free / Open-Source)

```
# Agent framework
crewai>=0.28.0
crewai-tools>=0.1.0

# LLM routing
litellm>=1.0.0

# Web framework
fastapi>=0.110.0
uvicorn>=0.29.0

# Database
sqlalchemy>=2.0.0
psycopg2-binary>=2.9.9
alembic>=1.13.0

# Vector store (free, local)
faiss-cpu>=1.7.4
sentence-transformers>=2.7.0

# Web scraping (free)
playwright>=1.43.0
beautifulsoup4>=4.12.0
requests>=2.31.0
duckduckgo-search>=5.3.0

# Social media (free APIs)
tweepy>=4.14.0
praw>=7.7.1

# Email (built-in smtplib, no extra package needed)

# Image generation (local, free)
diffusers>=0.27.0
torch>=2.2.0
transformers>=4.39.0
accelerate>=0.29.0

# Task scheduling (free)
celery>=5.3.6
redis>=5.0.3

# Google Analytics 4 (free API)
google-analytics-data>=0.18.0
google-auth>=2.29.0

# Monitoring (free)
prometheus-client>=0.20.0

# Utilities
python-dotenv>=1.0.0
pydantic>=2.6.0
httpx>=0.27.0
tenacity>=8.2.3
pytest>=8.1.0
pytest-mock>=3.12.0
pytest-asyncio>=0.23.0
```

---

## 7.3 docker-compose.yml (All Free Images)

```yaml
version: "3.9"

services:

  postgres:
    image: postgres:16-alpine
    container_name: marketing_postgres
    environment:
      POSTGRES_DB: marketing_db
      POSTGRES_USER: admin
      POSTGRES_PASSWORD: secret
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U admin -d marketing_db"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: marketing_redis
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      retries: 3

  ollama:
    image: ollama/ollama:latest
    container_name: marketing_ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]   # Remove if no GPU
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:11434/api/tags"]
      interval: 30s
      retries: 5

  litellm:
    image: ghcr.io/berriai/litellm:main-latest
    container_name: marketing_litellm
    ports:
      - "4000:4000"
    volumes:
      - ./config/litellm_config.yaml:/app/config.yaml
    command: ["--config", "/app/config.yaml", "--port", "4000"]
    depends_on:
      ollama:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:4000/health"]
      interval: 20s
      retries: 5

  wordpress:
    image: wordpress:latest
    container_name: marketing_wordpress
    ports:
      - "8080:80"
    environment:
      WORDPRESS_DB_HOST: wordpress_db
      WORDPRESS_DB_USER: wp_user
      WORDPRESS_DB_PASSWORD: wp_pass
      WORDPRESS_DB_NAME: wordpress
    depends_on:
      - wordpress_db
    volumes:
      - wordpress_data:/var/www/html

  wordpress_db:
    image: mysql:8-debian
    container_name: marketing_wpdb
    environment:
      MYSQL_DATABASE: wordpress
      MYSQL_USER: wp_user
      MYSQL_PASSWORD: wp_pass
      MYSQL_ROOT_PASSWORD: root_pass
    volumes:
      - wpdb_data:/var/lib/mysql

  app:
    build: .
    container_name: marketing_app
    ports:
      - "8000:8000"
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      litellm:
        condition: service_healthy
    volumes:
      - ./data:/app/data
      - ./static:/app/static
    command: uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

  celery_worker:
    build: .
    container_name: marketing_celery
    env_file: .env
    depends_on:
      - redis
      - postgres
    command: celery -A feedback.celery_app worker --loglevel=info

  celery_beat:
    build: .
    container_name: marketing_celery_beat
    env_file: .env
    depends_on:
      - redis
    command: celery -A feedback.celery_app beat --loglevel=info

  grafana:
    image: grafana/grafana:latest
    container_name: marketing_grafana
    ports:
      - "3000:3000"
    volumes:
      - grafana_data:/var/lib/grafana
      - ./config/grafana_dashboards:/etc/grafana/provisioning/dashboards

  prometheus:
    image: prom/prometheus:latest
    container_name: marketing_prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./config/prometheus.yml:/etc/prometheus/prometheus.yml

volumes:
  postgres_data:
  ollama_data:
  wordpress_data:
  wpdb_data:
  grafana_data:
```

---

## 7.4 Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# System deps for Playwright and Torch
RUN apt-get update && apt-get install -y \
    curl wget git build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium
RUN playwright install-deps chromium

COPY . .

# Create data directories
RUN mkdir -p data static/images config

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 7.5 Alembic Migration Setup

```bash
# Initialize (run once)
alembic init migrations

# Edit migrations/env.py to import your models:
# from db.models import Base
# target_metadata = Base.metadata

# Create first migration
alembic revision --autogenerate -m "initial_schema"

# Apply migration
alembic upgrade head
```

---

## 7.6 Logging Configuration (`config/logging.yaml`)

```yaml
version: 1
formatters:
  standard:
    format: "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
handlers:
  console:
    class: logging.StreamHandler
    formatter: standard
    level: INFO
  file:
    class: logging.FileHandler
    filename: logs/app.log
    formatter: standard
    level: DEBUG
root:
  level: DEBUG
  handlers: [console, file]
loggers:
  crewai:
    level: INFO
  sqlalchemy.engine:
    level: WARNING
  httpx:
    level: WARNING
```

---

## 7.7 Prometheus Config (`config/prometheus.yml`)

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: "marketing_app"
    static_configs:
      - targets: ["app:8000"]
    metrics_path: /metrics
```

---

## 7.8 Startup Script (`scripts/startup.sh`)

```bash
#!/bin/bash
set -e

echo "=== Step 1: Starting infrastructure ==="
docker-compose up -d postgres redis ollama litellm wordpress wordpress_db

echo "=== Step 2: Waiting for Postgres to be ready ==="
sleep 10
docker-compose exec postgres pg_isready -U admin -d marketing_db

echo "=== Step 3: Pulling Ollama models ==="
docker-compose exec ollama ollama pull qwen3:14b
docker-compose exec ollama ollama pull mistral:7b
docker-compose exec ollama ollama pull phi
docker-compose exec ollama ollama pull qwen:1.8b

echo "=== Step 4: Running database migrations ==="
docker-compose run --rm app alembic upgrade head

echo "=== Step 5: Seeding VectorDB with company knowledge ==="
docker-compose run --rm app python scripts/seed_vector_db.py

echo "=== Step 6: Installing Playwright browsers ==="
docker-compose run --rm app playwright install chromium

echo "=== Step 7: Starting app and workers ==="
docker-compose up -d app celery_worker celery_beat grafana prometheus

echo "=== DONE: System running ==="
echo "App:      http://localhost:8000"
echo "WordPress http://localhost:8080"
echo "Grafana:  http://localhost:3000 (admin/admin)"
echo "Ollama:   http://localhost:11434"
echo "LiteLLM:  http://localhost:4000"
```

---

## 7.9 Monitoring Preferences

- **Grafana dashboards to import:**
  - LiteLLM dashboard: ID 18457 (grafana.com)
  - PostgreSQL dashboard: ID 9628
  - Redis dashboard: ID 11835
  - Custom: agent task duration and lead pipeline funnel (build manually from `task_log` table)

- **Alerts (Grafana):**
  - Any `task_log.status = failed` in last hour → notify via log file
  - `outreach_records` daily count < 5 → pipeline may be stalled
  - FAISS index file size = 0 → VectorDB not seeded

- **Log rotation:** Use Docker's built-in `json-file` driver with `max-size: 50m, max-file: 3`
