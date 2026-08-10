import { apiDelete, apiGet, apiSend } from "./client";
import type {
  AgentProfile,
  AgentSecretOut,
  DiscoveryFinishOut,
  DiscoveryStartOut,
  PipelineRun,
  ProviderInfo,
  SkillHealthResponse,
} from "./types";

export function fetchAgents(): Promise<AgentProfile[]> {
  return apiGet<AgentProfile[]>("/api/agents");
}

export function fetchAgent(name: string): Promise<AgentProfile> {
  return apiGet<AgentProfile>(`/api/agents/${name}`);
}

export function updateAgent(name: string, patch: Record<string, unknown>): Promise<AgentProfile> {
  return apiSend<AgentProfile>(`/api/agents/${name}`, "PATCH", patch);
}

export function startScout(seedQuery: string, maxSearchResults: number | null): Promise<DiscoveryStartOut> {
  return apiSend<DiscoveryStartOut>("/api/agents/discovery/start", "POST", {
    seed_query: seedQuery,
    ...(maxSearchResults != null ? { max_search_results: maxSearchResults } : {}),
  });
}

export function finishScout(): Promise<DiscoveryFinishOut> {
  return apiSend<DiscoveryFinishOut>("/api/agents/discovery/finish", "POST");
}

export interface ToolCatalogItem {
  id: string;
  label: string;
  agents: string[];
}

export function fetchToolCatalog(): Promise<ToolCatalogItem[]> {
  return apiGet<ToolCatalogItem[]>("/api/agents/tools");
}

export function fetchSkillHealth(): Promise<SkillHealthResponse> {
  return apiSend<SkillHealthResponse>("/api/agents/tools/health", "POST");
}

export function fetchProviders(agentName: string): Promise<ProviderInfo[]> {
  return apiGet<ProviderInfo[]>(`/api/agents/${agentName}/providers`);
}

export interface ProviderKeyForm {
  kind: string;
  name: string;
  value: string;
}

export function upsertProviderKey(agentName: string, body: ProviderKeyForm): Promise<AgentSecretOut> {
  return apiSend<AgentSecretOut>(`/api/agents/${agentName}/secrets`, "POST", {
    kind: body.kind,
    name: body.name,
    value: body.value,
  });
}

export function deleteProviderKey(agentName: string, kind: string): Promise<void> {
  return apiDelete<void>(`/api/agents/${agentName}/secrets/${kind}`);
}

export function dispatchAgent(
  agentName: string,
  body: { seed_query?: string; mission?: string },
): Promise<PipelineRun> {
  return apiSend<PipelineRun>(`/api/agents/${agentName}/dispatch`, "POST", body);
}
