import { apiGet, apiSend } from "./client";
import type { AgentProfile, DiscoveryFinishOut, DiscoveryStartOut } from "./types";

export function fetchAgents(): Promise<AgentProfile[]> {
  return apiGet<AgentProfile[]>("/api/agents");
}

export function fetchAgent(name: string): Promise<AgentProfile> {
  return apiGet<AgentProfile>(`/api/agents/${name}`);
}

export function updateAgent(name: string, patch: Record<string, unknown>): Promise<AgentProfile> {
  return apiSend<AgentProfile>(`/api/agents/${name}`, "PATCH", patch);
}

export function startScout(seedQuery: string, maxSearchResults: number): Promise<DiscoveryStartOut> {
  return apiSend<DiscoveryStartOut>("/api/agents/discovery/start", "POST", {
    seed_query: seedQuery,
    max_search_results: maxSearchResults,
  });
}

export function finishScout(): Promise<DiscoveryFinishOut> {
  return apiSend<DiscoveryFinishOut>("/api/agents/discovery/finish", "POST");
}
