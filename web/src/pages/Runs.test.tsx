import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import Runs from "./Runs";
import * as runsApi from "../api/runs";

function renderRuns() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Runs />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Runs", () => {
  it("renders agent runs", async () => {
    vi.spyOn(runsApi, "fetchRuns").mockResolvedValue([
      { id: "ar1", pipeline_run_id: "p1", agent_name: "discovery", model: "m", status: "success", input_summary: "seed", output_summary: null, output_json: null, apis_consumed: null, records_processed: 4, error_message: null, started_at: "2026-08-05T00:00:00", finished_at: "2026-08-05T00:00:02" },
    ]);
    renderRuns();
    expect(await screen.findByText("discovery")).toBeInTheDocument();
    expect(screen.getByText("success")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
  });
});
