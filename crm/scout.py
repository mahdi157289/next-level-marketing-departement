"""Scout chat engine — conversational, tool-capable, persisted.

Pure logic (no FastAPI). Loads the Scout's own model + mission + enabled
tools from agent_profiles.discovery. Hybrid tool invocation: native OpenAI
function-calling first, JSON-decision fallback if the model rejects `tools`.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from agents import lm_client
from config.settings import get_settings
from crm import service
from tools import registry

_MAX_TOOL_ITERATIONS = 5

_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for real businesses and leads.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "max_results": {"type": "integer", "description": "Max results", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "google_maps_search",
            "description": "Find local businesses on Google Maps with contact info.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Business type / keyword"},
                    "region": {"type": "string", "description": "City, country", "default": "Tunisia"},
                    "max_results": {"type": "integer", "description": "Max results", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
]

_FALLBACK_DECISION_PROMPT = (
    "You are the Scout. Decide if you need tools. Respond with JSON only (no fences): "
    '{"tool_calls": [{"name": "web_search", "arguments": {"query": "..."}}]} '
    "or {\"tool_calls\": []} if you can answer directly."
)


def _load_scout_profile() -> Dict[str, Any]:
    s = get_settings()
    try:
        profile = service.get_agent_profile("discovery") or {}
    except Exception:
        profile = {}
    return {
        "model": profile.get("model") or s.agent_model_discovery,
        "mission_prompt": profile.get("mission_prompt") or "You are the Scout.",
        "enabled_tools": list(profile.get("enabled_tools") or []),
    }


def _tool_callable(name: str) -> Optional[Callable[..., Any]]:
    return registry.resolve_callable(name)


def _run_fallback_tools(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """JSON-decision fallback when the model rejects native tools."""
    user_body = _FALLBACK_DECISION_PROMPT + "\n\nLast message:\n" + (messages[-1].get("content") or "")
    try:
        text = lm_client.chat_completion(
            _load_scout_profile()["model"],
            [{"role": "user", "content": user_body}],
            temperature=0.2,
            max_tokens=256,
        )
        import json

        data = json.loads(text.strip().strip("`") or "{}")
        calls = data.get("tool_calls") or []
        return [{"id": f"fb{i}", "name": c.get("name"), "arguments": c.get("arguments") or {}} for i, c in enumerate(calls)]
    except Exception:
        return []


def _execute_tool(call: Dict[str, Any], enabled: Optional[List[str]] = None) -> Dict[str, Any]:
    name = call.get("name") or ""
    args = call.get("arguments") or {}
    enabled_set = set(enabled or [])
    if enabled_set and name not in enabled_set:
        return {"tool_name": name, "args": args, "result": None, "error": f"tool {name} not enabled"}
    fn = _tool_callable(name)
    if fn is None:
        return {"tool_name": name, "args": args, "result": None, "error": f"tool {name} not available"}
    try:
        result = fn(**args)
        return {"tool_name": name, "args": args, "result": result, "error": None}
    except Exception as exc:
        return {"tool_name": name, "args": args, "result": None, "error": str(exc)}


def run_scout_turn(
    thread_id: str,
    user_text: str,
    *,
    max_tool_iterations: int = _MAX_TOOL_ITERATIONS,
    profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if profile is None:
        profile = _load_scout_profile()
    enabled_tools = profile.get("enabled_tools") or []
    enabled_set = set(enabled_tools)
    if enabled_set:
        advertised_tools = [t for t in _TOOLS_SCHEMA if t["function"]["name"] in enabled_set]
    else:
        advertised_tools = _TOOLS_SCHEMA
    service.add_scout_message(thread_id, "user", content=user_text)

    history = service.list_scout_messages(thread_id, limit=200)
    messages: List[Dict[str, Any]] = [{"role": "system", "content": profile["mission_prompt"]}]
    for m in history:
        if m.get("role") == "tool":
            content = m.get("tool_name") or "tool"
            messages.append({"role": "user", "content": f"[{content} result] {m.get('tool_result')}"})
        else:
            messages.append({"role": m["role"], "content": m.get("content") or ""})

    assistant_text = ""
    tool_calls_made = 0
    message_ids: List[str] = []

    for _ in range(max_tool_iterations):
        tool_calls: List[Dict[str, Any]] = []
        try:
            resp = lm_client.chat_completion_tools(
                profile["model"],
                messages,
                tools=advertised_tools,
                temperature=0.2,
                max_tokens=1024,
            )
            tool_calls = resp.get("tool_calls") or []
            assistant_text = resp.get("content") or ""
        except Exception:
            tool_calls = _run_fallback_tools(messages)
            assistant_text = ""

        if not tool_calls:
            break

        tool_calls_made += 1
        for call in tool_calls:
            outcome = _execute_tool(call, enabled=enabled_tools)
            msg = service.add_scout_message(
                thread_id,
                "tool",
                content=f"[{outcome['tool_name']}]",
                tool_name=outcome["tool_name"],
                tool_args=outcome["args"],
                tool_result={"result": outcome["result"], "error": outcome["error"]},
            )
            message_ids.append(str(msg["id"]))
            messages.append(
                {
                    "role": "user",
                    "content": f"[{outcome['tool_name']} result] {outcome['result']}",
                }
            )

    if not assistant_text:
        assistant_text = lm_client.chat_completion(
            profile["model"],
            messages,
            temperature=0.25,
            max_tokens=1024,
        )

    msg = service.add_scout_message(thread_id, "assistant", content=assistant_text)
    message_ids.append(str(msg["id"]))

    return {
        "thread_id": thread_id,
        "assistant": assistant_text,
        "tool_calls": tool_calls_made,
        "message_ids": message_ids,
    }
