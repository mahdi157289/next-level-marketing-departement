"""
Quick check that LM Studio Local Server is reachable and each model answers.
Requires: LM Studio server running on http://127.0.0.1:1234
Load the model you test in LM Studio if your build only runs one model at a time.

Usage (from project root):
  python scripts/smoke_test_lm_studio.py
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:1234"
MODELS = [
    "phi-2",
    "google/gemma-2-9b",
    "mistralai/mistral-7b-instruct-v0.3",
    "qwen/qwen3-14b",
]


def post_json(path: str, body: dict, timeout: float = 120.0) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_json(path: str, timeout: float = 15.0) -> dict:
    req = urllib.request.Request(f"{BASE}{path}", method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    print(f"Checking LM Studio at {BASE} ...")
    try:
        meta = get_json("/v1/models")
    except urllib.error.URLError as e:
        print(f"FAIL: cannot reach {BASE} — is LM Studio Local Server started? ({e})")
        return 1

    known = {m.get("id") for m in meta.get("data", []) if isinstance(m, dict)}
    print(f"OK: /v1/models returned {len(known)} id(s).")

    failures = 0
    for model_id in MODELS:
        if known and model_id not in known:
            print(f"WARN: '{model_id}' not listed in /v1/models — still trying chat ...")
        print(f"  -> chat.completions model={model_id!r} ...", flush=True)
        try:
            out = post_json(
                "/v1/chat/completions",
                {
                    "model": model_id,
                    "messages": [{"role": "user", "content": "Reply with exactly one word: OK"}],
                    "temperature": 0.2,
                    "max_tokens": 16,
                    "stream": False,
                },
                # 14B on CPU / first-token latency can exceed 300s; allow long runs.
                timeout=900.0,
            )
            text = (out.get("choices") or [{}])[0].get("message", {}).get("content", "")
            if not str(text).strip():
                print(f"FAIL: empty completion for {model_id}")
                failures += 1
            else:
                print(f"    OK: {str(text).strip()[:120]!r}")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:500]
            print(f"FAIL: HTTP {e.code} for {model_id}: {body}")
            failures += 1
        except Exception as e:
            print(f"FAIL: {model_id}: {e}")
            failures += 1

    if failures:
        print(f"\nDone with {failures} failure(s). Load the model in LM Studio if needed.")
        return 2
    print("\nAll model smoke checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
