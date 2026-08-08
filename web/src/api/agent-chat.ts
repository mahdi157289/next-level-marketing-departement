import { apiGet, apiSend } from "./client";
import { takeFrames } from "./sse";
import type { AgentPrompt, ScoutMessage, ScoutThread } from "./types";

export function fetchAgentThreads(agentName: string, limit = 50): Promise<ScoutThread[]> {
  return apiGet<ScoutThread[]>(`/api/agents/${agentName}/threads?limit=${limit}`);
}

export function createAgentThread(agentName: string, title?: string): Promise<ScoutThread> {
  return apiSend<ScoutThread>(`/api/agents/${agentName}/threads`, "POST", { title });
}

export function fetchAgentMessages(agentName: string, threadId: string): Promise<ScoutMessage[]> {
  return apiGet<ScoutMessage[]>(`/api/agents/${agentName}/threads/${threadId}/messages`);
}

export interface AgentTurnHandlers {
  onStart?: () => void;
  onDelta?: (delta: string, index: number) => void;
  onDone?: (payload: { thread_id: string; assistant: string; tool_calls: number }) => void;
  onError?: (detail: string) => void;
}

export async function streamAgentTurn(
  agentName: string,
  threadId: string,
  content: string,
  handlers: AgentTurnHandlers,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`/api/agents/${agentName}/threads/${threadId}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    });
  } catch (err) {
    handlers.onError?.(err instanceof Error ? err.message : "Network error");
    return;
  }
  if (!res.ok) {
    const text = await res.text();
    handlers.onError?.(text || `HTTP ${res.status}`);
    return;
  }
  const reader = res.body?.getReader();
  if (!reader) {
    handlers.onError?.("No response body");
    return;
  }
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    let value: Uint8Array | undefined;
    let done: boolean;
    try {
      ({ done, value } = await reader.read());
    } catch (err) {
      handlers.onError?.(err instanceof Error ? err.message : "Stream error");
      return;
    }
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const { frames, rest } = takeFrames(buffer);
    buffer = rest;
    for (const frame of frames) {
      if (frame.event === "start") {
        handlers.onStart?.();
      } else if (frame.event === "delta") {
        try {
          const data = JSON.parse(frame.data) as { delta: string; index: number };
          handlers.onDelta?.(data.delta, data.index);
        } catch {
          // ignore malformed delta
        }
      } else if (frame.event === "done") {
        try {
          handlers.onDone?.(JSON.parse(frame.data) as { thread_id: string; assistant: string; tool_calls: number });
        } catch {
          // ignore
        }
      } else if (frame.event === "error") {
        try {
          const data = JSON.parse(frame.data) as { detail?: string };
          handlers.onError?.(data.detail ?? frame.data);
        } catch {
          handlers.onError?.(frame.data);
        }
      }
    }
  }
}

export function fetchAgentPrompt(agentName: string): Promise<AgentPrompt> {
  return apiGet<AgentPrompt>(`/api/agents/${agentName}/prompt`);
}

export function saveAgentPrompt(agentName: string, content: string): Promise<AgentPrompt> {
  return apiSend<AgentPrompt>(`/api/agents/${agentName}/prompt`, "PUT", { content });
}
