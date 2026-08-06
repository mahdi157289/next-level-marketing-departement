import { apiGet } from "./client";
import type { AgentRun } from "./types";

export function fetchRuns(): Promise<AgentRun[]> {
  return apiGet<AgentRun[]>("/api/agent-runs?limit=100");
}

export function fetchRun(id: string): Promise<AgentRun> {
  return apiGet<AgentRun>(`/api/agent-runs/${id}`);
}
