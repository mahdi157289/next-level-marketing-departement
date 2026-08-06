import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import Agents from "./Agents";
import * as agentsApi from "../api/agents";

function renderAgents() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Agents />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Agents", () => {
  it("renders the agent roster", async () => {
    vi.spyOn(agentsApi, "fetchAgents").mockResolvedValue([
      { agent_name: "discovery", display_name: "Discovery (Scout)", mission_prompt: "p", enabled_tools: ["web_search"], model: null, default_seed_query: "agencies", updated_at: null, available_tools: [] },
    ]);
    renderAgents();
    expect(await screen.findByText("Discovery (Scout)")).toBeInTheDocument();
    expect(screen.getByText("agencies")).toBeInTheDocument();
  });
});
