import { apiGet, apiSend } from "./client";
import { takeFrames } from "./sse";
import type { PipelineRun, ScoutMessage, ScoutThread } from "./types";

export function fetchThreads(): Promise<ScoutThread[]> {
  return apiGet<ScoutThread[]>("/api/scout/threads?limit=50");
}

export function createThread(title?: string): Promise<ScoutThread> {
  return apiSend<ScoutThread>("/api/scout/threads", "POST", { title });
}

export function fetchMessages(threadId: string): Promise<ScoutMessage[]> {
  return apiGet<ScoutMessage[]>(`/api/scout/threads/${threadId}/messages`);
}

export function fetchMissions(): Promise<PipelineRun[]> {
  return apiGet<PipelineRun[]>("/api/pipeline-runs?limit=20");
}

export interface ScoutTurnHandlers {
  onStart?: () => void;
  onDelta?: (delta: string, index: number) => void;
  onDone?: (payload: { thread_id: string; assistant: string; tool_calls: number }) => void;
  onError?: (detail: string) => void;
}

export async function streamScoutTurn(
  threadId: string,
  content: string,
  handlers: ScoutTurnHandlers,
): Promise<void> {
  const res = await fetch(`/api/scout/threads/${threadId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
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
    const { done, value } = await reader.read();
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
