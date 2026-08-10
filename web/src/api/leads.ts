import { apiGet, apiSend } from "./client";
import type { EnrichLeadsOut, Lead, LeadDetail } from "./types";

export function fetchLeads(status?: string): Promise<Lead[]> {
  const q = status ? `&status=${encodeURIComponent(status)}` : "";
  return apiGet<Lead[]>(`/api/leads?limit=100${q}`);
}

export function fetchLead(id: string): Promise<LeadDetail> {
  return apiGet<LeadDetail>(`/api/leads/${id}`);
}

export function updateLead(id: string, patch: Record<string, unknown>): Promise<Lead> {
  return apiSend<Lead>(`/api/leads/${id}`, "PATCH", patch);
}

export function enrichLeads(leadIds: string[] = []): Promise<EnrichLeadsOut> {
  const body = leadIds.length ? { lead_ids: leadIds } : { limit: 200 };
  return apiSend<EnrichLeadsOut>(`/api/leads/enrich`, "POST", body);
}
