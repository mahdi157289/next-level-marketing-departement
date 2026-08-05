# Doc 5 — Tool & API Specifications

All tools are free and open-source. No paid API keys required except Meta WhatsApp (free tier) and Gmail SMTP (free with app password).

---

## 5.1 duckduckgo_search_tool

**Library:** `duckduckgo-search` (PyPI, free, no API key)

```python
# tools/web_search_tool.py
from duckduckgo_search import DDGS
from crewai.tools import tool

@tool("Web Search Tool")
def web_search_tool(query: str, max_results: int = 10) -> list[dict]:
    """Search the web using DuckDuckGo. Returns list of {title, url, snippet}."""
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=max_results))
    return [{"title": r["title"], "url": r["href"], "snippet": r["body"]} for r in results]

# Error handling:
# - Retry 3x on ConnectionError with 2s backoff
# - Return [] on persistent failure, log to task_log
# - Rate limit: 1 request per 2 seconds
```

**Test:**
```python
def test_web_search_tool():
    results = web_search_tool("e-commerce startups Tunisia 2024")
    assert isinstance(results, list)
    assert len(results) > 0
    assert "url" in results[0]
    assert results[0]["url"].startswith("http")
```

---

## 5.2 playwright_scraper

**Library:** `playwright` (free, install chromium with `playwright install chromium`)

```python
# tools/scrape_tool.py
import re
from playwright.async_api import async_playwright
from crewai.tools import tool

@tool("Website Scraper Tool")
async def scrape_tool(url: str) -> dict:
    """
    Scrape a website for emails, phone numbers, and text content.
    Respects robots.txt. Returns {emails, phones, text_sample, title}.
    """
    # Step 1: check robots.txt
    robots_url = f"{url.rstrip('/')}/robots.txt"
    # ... check if path is allowed ...

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, timeout=10000)
        html = await page.content()
        title = await page.title()
        await browser.close()

    emails = list(set(re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", html)))
    phones = list(set(re.findall(r"\+?[\d\s\-().]{7,15}", html)))
    return {"emails": emails[:5], "phones": phones[:3], "title": title, "url": url}

# Error handling:
# - Timeout after 10s → return {"error": "timeout", "url": url}
# - If robots.txt disallows "/" → return {"error": "robots_disallowed", "url": url}
# - Log all errors to task_log
```

**Test:**
```python
def test_scrape_tool():
    result = scrape_tool("https://example.com")
    assert "emails" in result
    assert "phones" in result
    assert isinstance(result["emails"], list)
```

---

## 5.3 requests_seo_tool

**Library:** `requests` + `beautifulsoup4` (free, no API key)

```python
# tools/seo_audit_tool.py
import requests
from bs4 import BeautifulSoup
from crewai.tools import tool

@tool("SEO Audit Tool")
def seo_audit_tool(url: str) -> dict:
    """
    Run a basic SEO audit on a URL. Returns seo_score (0-100) and issues list.
    Checks: title, meta description, H1, viewport meta, image alts, response time.
    """
    try:
        import time
        start = time.time()
        resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        load_time = time.time() - start
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        return {"seo_score": 0, "issues": [str(e)], "url": url}

    issues = []
    score = 100

    title = soup.find("title")
    if not title or len(title.text.strip()) < 10:
        issues.append("Missing or short title tag")
        score -= 20

    meta_desc = soup.find("meta", attrs={"name": "description"})
    if not meta_desc or not meta_desc.get("content"):
        issues.append("Missing meta description")
        score -= 15

    h1 = soup.find("h1")
    if not h1:
        issues.append("Missing H1 tag")
        score -= 15

    viewport = soup.find("meta", attrs={"name": "viewport"})
    if not viewport:
        issues.append("Not mobile-friendly (no viewport meta)")
        score -= 20

    imgs_no_alt = [img for img in soup.find_all("img") if not img.get("alt")]
    if len(imgs_no_alt) > 3:
        issues.append(f"{len(imgs_no_alt)} images missing alt text")
        score -= 10

    if load_time > 3.0:
        issues.append(f"Slow load: {load_time:.1f}s")
        score -= 10

    return {"seo_score": max(0, score), "issues": issues, "load_time_s": round(load_time, 2)}

# Rate limit: 1 req/sec per domain
```

**Test:**
```python
def test_seo_audit_tool():
    result = seo_audit_tool("https://example.com")
    assert "seo_score" in result
    assert 0 <= result["seo_score"] <= 100
    assert isinstance(result["issues"], list)
```

---

## 5.4 crm_tool (PostgreSQL via SQLAlchemy)

**Library:** `sqlalchemy` + `psycopg2-binary` (free)

```python
# tools/crm_tool.py
from sqlalchemy import create_engine, text
from crewai.tools import tool
import os

engine = create_engine(os.getenv("DATABASE_URL"))

@tool("CRM Read Tool")
def crm_read_tool(status: str = None, limit: int = 100) -> list[dict]:
    """Read leads from PostgreSQL. Filter by status if provided."""
    with engine.connect() as conn:
        q = "SELECT * FROM leads"
        params = {}
        if status:
            q += " WHERE status = :status"
            params["status"] = status
        q += " LIMIT :limit"
        params["limit"] = limit
        rows = conn.execute(text(q), params).mappings().all()
    return [dict(r) for r in rows]

@tool("CRM Write Tool")
def crm_write_tool(table: str, data: dict, where_id: str = None) -> str:
    """INSERT or UPDATE a row in the CRM. Returns affected row id."""
    with engine.begin() as conn:
        if where_id:
            sets = ", ".join([f"{k}=:{k}" for k in data])
            data["_id"] = where_id
            conn.execute(text(f"UPDATE {table} SET {sets} WHERE id=:_id"), data)
            return f"updated:{where_id}"
        else:
            cols = ", ".join(data.keys())
            vals = ", ".join([f":{k}" for k in data.keys()])
            result = conn.execute(text(f"INSERT INTO {table} ({cols}) VALUES ({vals}) RETURNING id"), data)
            return f"inserted:{result.fetchone()[0]}"
```

**Test:**
```python
def test_crm_roundtrip():
    row_id = crm_write_tool("leads", {"name": "Test Co", "url": "http://test.com", "status": "raw"})
    assert "inserted:" in row_id
    leads = crm_read_tool(status="raw", limit=1)
    assert any(l["name"] == "Test Co" for l in leads)
```

---

## 5.5 vector_store_search (FAISS)

**Library:** `faiss-cpu` + `sentence-transformers` (free)

```python
# db/vector_store.py
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from crewai.tools import tool

model = SentenceTransformer("all-MiniLM-L6-v2")  # free, runs locally
index = faiss.read_index("data/company_kb.index")
metadata = []  # loaded from JSON at startup

@tool("Vector Store Search Tool")
def vector_store_search(query: str, top_k: int = 3) -> list[dict]:
    """
    Search company knowledge base for services matching the query.
    Returns top_k results with {title, content, score}.
    """
    embedding = model.encode([query])
    distances, indices = index.search(np.array(embedding, dtype="float32"), top_k)
    results = []
    for i, idx in enumerate(indices[0]):
        if idx < len(metadata):
            results.append({**metadata[idx], "score": float(distances[0][i])})
    return results
```

**Test:**
```python
def test_vector_store_search():
    results = vector_store_search("company has no SEO optimization")
    assert len(results) > 0
    assert "title" in results[0]
    assert "score" in results[0]
```

---

## 5.6 smtp_email_tool

**Free provider:** Gmail SMTP (requires Google account + app password)
**Alternative:** Local Postfix Docker container (zero cost, no account needed)

```python
# tools/email_tool.py
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from crewai.tools import tool
import os

@tool("SMTP Email Tool")
def smtp_email_tool(to: str, subject: str, body_html: str) -> dict:
    """
    Send an email via Gmail SMTP (free).
    Requires: GMAIL_USER, GMAIL_APP_PASSWORD in environment.
    Returns: {status, message_id}
    """
    msg = MIMEMultipart("alternative")
    msg["From"] = os.getenv("GMAIL_USER")
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body_html, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
            server.login(os.getenv("GMAIL_USER"), os.getenv("GMAIL_APP_PASSWORD"))
            server.sendmail(os.getenv("GMAIL_USER"), to, msg.as_string())
        return {"status": "sent", "to": to}
    except smtplib.SMTPRecipientsRefused:
        return {"status": "bounced", "to": to, "error": "recipient refused"}
    except Exception as e:
        return {"status": "failed", "to": to, "error": str(e)}

# Daily limit safety: track count in Redis, abort if > 20/day
```

**Test (dry run, no real send):**
```python
def test_smtp_email_tool_mock(mocker):
    mocker.patch("smtplib.SMTP_SSL")
    result = smtp_email_tool("test@example.com", "Test Subject", "<p>Hello</p>")
    assert result["status"] == "sent"
```

---

## 5.7 meta_whatsapp_tool

**Free tier:** Meta WhatsApp Cloud API — 1,000 free conversations/month
**Setup:** Register at developers.facebook.com, create app, get PHONE_NUMBER_ID and ACCESS_TOKEN (both free)

```python
# tools/whatsapp_tool.py
import requests
from crewai.tools import tool
import os

@tool("WhatsApp Send Tool")
def meta_whatsapp_tool(to_number: str, message: str) -> dict:
    """
    Send WhatsApp message via Meta Cloud API (free tier).
    to_number must be in E.164 format: +21612345678
    """
    url = f"https://graph.facebook.com/v18.0/{os.getenv('WA_PHONE_NUMBER_ID')}/messages"
    headers = {
        "Authorization": f"Bearer {os.getenv('WA_ACCESS_TOKEN')}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": message}
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=10)
    resp.raise_for_status()
    return {"status": "sent", "to": to_number, "wa_id": resp.json().get("messages", [{}])[0].get("id")}

# Error handling:
# - 400: invalid number format → log, skip
# - 429: rate limit → wait 60s, retry once
# - 500: Meta server error → log, retry next cycle
```

**Test:**
```python
def test_meta_whatsapp_tool_mock(requests_mock):
    requests_mock.post("https://graph.facebook.com/v18.0/TEST_ID/messages",
                       json={"messages": [{"id": "wamid.test"}]})
    result = meta_whatsapp_tool("+21612345678", "Hello test")
    assert result["status"] == "sent"
```

---

## 5.8 stable_diffusion_tool

**Library:** `diffusers` + `torch` (free, local inference)
**Model:** `stabilityai/stable-diffusion-2-1` (free, download once from HuggingFace)

```python
# tools/image_gen_tool.py
from diffusers import StableDiffusionPipeline
import torch
from crewai.tools import tool
import uuid, os

pipe = StableDiffusionPipeline.from_pretrained(
    "stabilityai/stable-diffusion-2-1",
    torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32
)
pipe = pipe.to("cuda" if torch.cuda.is_available() else "cpu")

@tool("Image Generation Tool")
def stable_diffusion_tool(prompt: str, size: str = "512x512") -> str:
    """
    Generate an image locally using Stable Diffusion 2.1 (free).
    Returns file path of saved image.
    """
    w, h = map(int, size.split("x"))
    image = pipe(prompt, height=h, width=w, num_inference_steps=20).images[0]
    path = f"static/images/{uuid.uuid4()}.png"
    os.makedirs("static/images", exist_ok=True)
    image.save(path)
    return path

# CPU fallback: inference takes 2-5 minutes on CPU. Consider --num_inference_steps 10 for speed.
```

**Test:**
```python
def test_stable_diffusion_tool():
    path = stable_diffusion_tool("a tech company logo, minimal, blue")
    assert os.path.exists(path)
    assert path.endswith(".png")
```

---

## 5.9 wordpress_rest_tool

**Setup:** Self-hosted WordPress in Docker (free). Use `wordpress:latest` official Docker image.

```python
# tools/blog_tool.py
import requests
from crewai.tools import tool
import os, base64

@tool("WordPress Blog Post Tool")
def wordpress_rest_tool(title: str, content_markdown: str, tags: list[str]) -> dict:
    """
    Publish a blog post to self-hosted WordPress via REST API (free).
    Returns: {post_id, url}
    """
    auth = base64.b64encode(
        f"{os.getenv('WP_USER')}:{os.getenv('WP_APP_PASSWORD')}".encode()
    ).decode()
    resp = requests.post(
        f"{os.getenv('WP_API_URL')}/wp-json/wp/v2/posts",
        headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
        json={"title": title, "content": content_markdown, "status": "publish"},
        timeout=15
    )
    resp.raise_for_status()
    data = resp.json()
    return {"post_id": data["id"], "url": data["link"]}
```

---

## 5.10 Social Publishing Tools

### LinkedIn (free API)
```python
# tools/social_publish_tool.py
import requests
from crewai.tools import tool
import os

@tool("LinkedIn Post Tool")
def linkedin_post_tool(text: str, image_path: str = None) -> dict:
    """Post to LinkedIn company page via LinkedIn API v2 (free)."""
    headers = {"Authorization": f"Bearer {os.getenv('LINKEDIN_ACCESS_TOKEN')}",
               "Content-Type": "application/json"}
    payload = {
        "author": f"urn:li:organization:{os.getenv('LINKEDIN_ORG_ID')}",
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "NONE"
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"}
    }
    resp = requests.post("https://api.linkedin.com/v2/ugcPosts",
                         headers=headers, json=payload, timeout=10)
    resp.raise_for_status()
    return {"status": "posted", "post_id": resp.json().get("id")}
```

### Twitter/X (free v2 API — 500 posts/month)
```python
@tool("Twitter Post Tool")
def twitter_post_tool(text: str) -> dict:
    """Post tweet via Twitter API v2 (free tier). Max 500 posts/month."""
    import tweepy
    client = tweepy.Client(
        consumer_key=os.getenv("TWITTER_API_KEY"),
        consumer_secret=os.getenv("TWITTER_API_SECRET"),
        access_token=os.getenv("TWITTER_ACCESS_TOKEN"),
        access_token_secret=os.getenv("TWITTER_ACCESS_SECRET")
    )
    response = client.create_tweet(text=text[:280])
    return {"status": "posted", "tweet_id": response.data["id"]}
```

### Reddit (free API via PRAW)
```python
@tool("Reddit Post Tool")
def reddit_post_tool(subreddit: str, title: str, text: str) -> dict:
    """Post to Reddit via PRAW (free API, no cost)."""
    import praw
    reddit = praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        username=os.getenv("REDDIT_USERNAME"),
        password=os.getenv("REDDIT_PASSWORD"),
        user_agent="NextLevelMarketing/1.0"
    )
    submission = reddit.subreddit(subreddit).submit(title, selftext=text)
    return {"status": "posted", "url": submission.url}
```

---

## 5.11 Error Handling Standard (All Tools)

Every tool must implement:

```python
import time
import logging
from functools import wraps

def with_retry(max_retries=3, backoff=2.0):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        logging.error(f"[{fn.__name__}] Failed after {max_retries} attempts: {e}")
                        raise
                    time.sleep(backoff ** attempt)
        return wrapper
    return decorator
```

Apply `@with_retry(max_retries=3, backoff=2.0)` to all tools that make network calls.
