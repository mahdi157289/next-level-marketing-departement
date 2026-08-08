import { apiGet } from "./client";
import type { AgentRun, PipelineRun } from "./types";

export function fetchRuns(): Promise<AgentRun[]> {
  return apiGet<AgentRun[]>("/api/agent-runs?limit=100");
}

export function fetchRun(id: string): Promise<AgentRun> {
  return apiGet<AgentRun>(`/api/agent-runs/${id}`);
}

export function fetchAgentRuns(
  agentName?: string,
  pipelineRunId?: string,
  limit = 20,
): Promise<AgentRun[]> {
  const params = new URLSearchParams();
  if (agentName) params.set("agent_name", agentName);
  if (pipelineRunId) params.set("pipeline_run_id", pipelineRunId);
  params.set("limit", String(limit));
  return apiGet<AgentRun[]>(`/api/agent-runs?${params.toString()}`);
}

export function fetchPipelineRun(id: string): Promise<PipelineRun> {
  return apiGet<PipelineRun>(`/api/pipeline-runs/${id}`);
}

export function fetchPipelineRuns(limit = 50): Promise<PipelineRun[]> {
  return apiGet<PipelineRun[]>(`/api/pipeline-runs?limit=${limit}`);
}
