import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import Dashboard from "./Dashboard";
import * as statsApi from "../api/stats";
import * as missionsApi from "../api/missions";

function renderDashboard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Dashboard />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Dashboard", () => {
  it("renders KPI cards and recent missions", async () => {
    vi.spyOn(statsApi, "fetchStats").mockResolvedValue({
      leads_total: 6,
      leads_by_status: { raw: 6 },
      leads_avg_score: 3.5,
      runs_today: 35,
      run_success_rate: 5.0,
      recent_runs: [],
      scout_active: false,
      scout_last_seed: null,
    });
    vi.spyOn(missionsApi, "fetchRecentMissions").mockResolvedValue([
      { id: "r1", trigger: "api", seed_query: "agencies", status: "success", started_at: "2026-08-05T00:00:00", finished_at: null, meta: null },
    ]);

    renderDashboard();

    expect(await screen.findByText("Leads")).toBeInTheDocument();
    expect(await screen.findByText("6")).toBeInTheDocument();
    expect(screen.getByText("Avg score")).toBeInTheDocument();
    expect(await screen.findByText("3.5")).toBeInTheDocument();
    expect(screen.getByText("Runs today")).toBeInTheDocument();
    expect(await screen.findByText("35")).toBeInTheDocument();
    expect(screen.getByText("Success rate")).toBeInTheDocument();
    expect(await screen.findByText("5%")).toBeInTheDocument();
    expect(await screen.findByText("agencies")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Scout HQ" })).toBeInTheDocument();
  });
});
