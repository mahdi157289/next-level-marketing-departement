import { apiGet, apiSend } from "./client";
import type { Lead, LeadDetail } from "./types";

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
