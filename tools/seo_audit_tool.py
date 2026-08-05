"""Basic SEO audit via HTTP fetch + BeautifulSoup (no browser)."""

from __future__ import annotations

import time
from typing import Any, Dict, List

import httpx
from bs4 import BeautifulSoup

DEFAULT_UA = (
    "Mozilla/5.0 (compatible; NextLevelMarketingDept/1.0; +https://the-next-level-tech-company-1.onrender.com)"
)


def seo_audit_tool(url: str, timeout_s: float = 8.0) -> Dict[str, Any]:
    """
    Return seo_score 0–100, issues list, load_time_s.
    On fetch/parse failure returns seo_score 0 and issues with error message.
    """
    try:
        start = time.time()
        with httpx.Client(timeout=timeout_s, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": DEFAULT_UA})
            resp.raise_for_status()
        load_time = time.time() - start
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        return {"seo_score": 0, "issues": [str(e)], "url": url, "load_time_s": None}

    issues: List[str] = []
    score = 100

    title = soup.find("title")
    if not title or len(title.text.strip()) < 10:
        issues.append("Missing or short title tag")
        score -= 20

    meta_desc = soup.find("meta", attrs={"name": "description"})
    if not meta_desc or not (meta_desc.get("content") or "").strip():
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

    return {
        "seo_score": max(0, score),
        "issues": issues,
        "load_time_s": round(load_time, 2),
        "url": url,
    }
