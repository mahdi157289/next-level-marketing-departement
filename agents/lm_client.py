"""OpenAI-compatible chat completions against LM Studio or LiteLLM (`/v1`).

Many LM Studio model templates only allow **user** and **assistant** turns; sending
`role: system` returns HTTP 400. Prefer a single **user** message with instructions + data.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from openai import OpenAI

from config.settings import get_settings

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        s = get_settings()
        _client = OpenAI(
            base_url=s.openai_base_url(),
            api_key=s.openai_api_key,
            timeout=s.agent_chat_timeout_s,
        )
    return _client


def _extract_message_text(msg: Any) -> str:
    """LM Studio Qwen3 may return text in reasoning_content when content is empty."""
    content = (getattr(msg, "content", None) or "").strip()
    if content:
        return content
    reasoning = getattr(msg, "reasoning_content", None)
    if reasoning and str(reasoning).strip():
        return str(reasoning).strip()
    extra = getattr(msg, "model_extra", None) or {}
    if isinstance(extra, dict):
        rc = extra.get("reasoning_content")
        if rc and str(rc).strip():
            return str(rc).strip()
    return ""


def chat_completion(
    model: str,
    messages: List[Dict[str, Any]],
    *,
    temperature: float = 0.35,
    max_tokens: int = 1024,
) -> str:
    client = _get_client()
    r = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    msg = r.choices[0].message
    return _extract_message_text(msg)


def ensure_llm_reachable(timeout_s: float = 3.0) -> tuple[bool, str]:
    """Fail fast if LM Studio (or the chat proxy path) cannot serve models.

    In Docker the app talks to LiteLLM, which forwards to host.docker.internal:1234.
    LiteLLM /models can succeed even when LM Studio is off — so we probe LM Studio
    (and fall back to a tiny chat via the configured OpenAI base).
    """
    import json
    import urllib.error
    import urllib.request

    s = get_settings()
    candidates = []
    for base in (
        "http://host.docker.internal:1234/v1",
        s.lm_studio_base_url.strip().rstrip("/"),
        s.openai_base_url(),
    ):
        b = (base or "").rstrip("/")
        if b and b not in candidates:
            candidates.append(b)

    last_err = "no endpoint tried"
    lm_ok = False
    for base in candidates:
        url = f"{base}/models"
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {s.openai_api_key}"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                data = json.loads(body) if body else {}
                models = data.get("data") if isinstance(data, dict) else None
                # Real LM Studio returns owned_by organization_owner; LiteLLM returns aliases.
                if "1234" in base or (isinstance(models, list) and any(
                    (m.get("owned_by") == "organization_owner") for m in models if isinstance(m, dict)
                )):
                    lm_ok = True
                    return True, f"ok LM Studio models via {url}"
                if isinstance(models, list) and models and ("litellm" in base or ":4000" in base):
                    # Proxy up — still verify backend with a tiny chat below.
                    last_err = f"proxy up {url} (checking chat)"
                    continue
                if isinstance(models, list) and models:
                    return True, f"ok {url}"
                last_err = f"empty model list from {url}"
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code} from {url}"
            if e.code in (401, 403) and "1234" in base:
                return True, f"LM Studio up (HTTP {e.code}) {url}"
        except Exception as e:
            last_err = f"{type(e).__name__}: {e} ({url})"

    if lm_ok:
        return True, "ok"

    # Last resort: tiny chat through configured OpenAI base (LiteLLM → LM Studio).
    try:
        client = OpenAI(
            base_url=s.openai_base_url(),
            api_key=s.openai_api_key,
            timeout=min(timeout_s, 8.0),
            max_retries=0,
        )
        client.chat.completions.create(
            model=s.agent_model_discovery,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
        )
        return True, "ok via chat probe"
    except Exception as e:
        return False, f"{last_err}; chat probe failed: {type(e).__name__}: {e}"


def reset_client_cache() -> None:
    """Tests only — force reloading Settings-derived HTTP client."""
    global _client
    _client = None
