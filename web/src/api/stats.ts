import { apiGet } from "./client";
import type { Stats } from "./types";

export function fetchStats(): Promise<Stats> {
  return apiGet<Stats>("/api/stats");
}
