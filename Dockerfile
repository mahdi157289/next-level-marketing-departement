FROM python:3.11-slim

WORKDIR /app

# Install Node.js 20.x (for the bundled Google Maps JS scraper)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gnupg \
    build-essential \
    libpq-dev \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-agents-crewai.txt requirements-crawl4ai.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-agents-crewai.txt -r requirements-crawl4ai.txt

RUN playwright install-deps chromium \
    && playwright install chromium

RUN crawl4ai-setup

COPY . .

# Install the bundled Google Maps JS scraper deps (native Linux binaries)
RUN cd tools/google_maps_scraper && npm install --omit=dev \
    && npx playwright install chromium

RUN mkdir -p data static/images logs \
    && sed -i 's/\r$//' scripts/docker_entrypoint.sh 2>/dev/null || true \
    && chmod +x scripts/docker_entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["python", "scripts/docker_entrypoint.py"]
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
