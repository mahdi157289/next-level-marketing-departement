import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import * as agentsApi from "../api/agents";
import Tools from "./Tools";

function renderTools() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Tools />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Tools catalog", () => {
  it("renders the tool catalog roster", async () => {
    vi.spyOn(agentsApi, "fetchToolCatalog").mockResolvedValue([
      { id: "web_search", label: "DuckDuckGo web search", agents: ["discovery"] },
      { id: "llm_chat", label: "LiteLLM chat", agents: ["discovery", "head"] },
    ]);
    vi.spyOn(agentsApi, "fetchSkillHealth").mockResolvedValue({
      checked_at: "2026-08-07T00:00:00Z",
      results: [],
    });
    renderTools();
    expect(await screen.findByText("web_search")).toBeInTheDocument();
    expect(screen.getByText("LiteLLM chat")).toBeInTheDocument();
  });

  it("renders green/red/amber lamps per skill", async () => {
    vi.spyOn(agentsApi, "fetchToolCatalog").mockResolvedValue([
      { id: "web_search", label: "DDG", agents: ["discovery"] },
      { id: "meta_ads_search", label: "Meta ads", agents: ["discovery"] },
      { id: "scrape", label: "Playwright", agents: ["discovery"] },
      { id: "google_maps_search", label: "Maps", agents: ["discovery"] },
    ]);
    vi.spyOn(agentsApi, "fetchSkillHealth").mockResolvedValue({
      checked_at: "2026-08-07T00:00:00Z",
      results: [
        { skill_id: "web_search", status: "ok", detail: "2 results", latency_ms: 900 },
        { skill_id: "meta_ads_search", status: "skip", detail: "no key", latency_ms: 2 },
        { skill_id: "scrape", status: "fail", detail: "error", latency_ms: 5000 },
      ],
    });
    const { container } = renderTools();
    await screen.findByText("DDG");
    await vi.waitFor(() => {
      expect(container.querySelector(".lamp.ok")).not.toBeNull();
    });
    expect(container.querySelector(".lamp.skip")).not.toBeNull();
    expect(container.querySelector(".lamp.fail")).not.toBeNull();
    // google_maps has no health result yet -> idle lamp.
    expect(container.querySelector(".lamp.idle")).not.toBeNull();
    expect(container.querySelector(".lamp.ok")?.getAttribute("title")).toContain("Works");
  });
});
