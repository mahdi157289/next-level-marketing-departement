import { apiGet } from "./client";
import type { BrainMetric, BrainStatus, WorkerStatus } from "./types";

export function fetchBrainStatus(): Promise<BrainStatus> {
  return apiGet<BrainStatus>("/api/brain/graph/status");
}

export function fetchBrainMetrics(limit = 10): Promise<{ metrics: BrainMetric[] }> {
  return apiGet<{ metrics: BrainMetric[] }>(`/api/brain/metrics?limit=${limit}`);
}

export function fetchWorkerStatus(): Promise<WorkerStatus> {
  return apiGet<WorkerStatus>("/api/brain/worker/status");
}
