import { apiGet } from "./client";
import type { LlmStatus } from "./types";

export function fetchLlmStatus(): Promise<LlmStatus> {
  return apiGet<LlmStatus>("/api/llm/status");
}
