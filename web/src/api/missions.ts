import { apiGet } from "./client";
import type { PipelineRun } from "./types";

export function fetchRecentMissions(): Promise<PipelineRun[]> {
  return apiGet<PipelineRun[]>("/api/pipeline-runs?limit=5");
}
