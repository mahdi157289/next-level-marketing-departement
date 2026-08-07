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
    renderTools();
    expect(await screen.findByText("web_search")).toBeInTheDocument();
    expect(screen.getByText("LiteLLM chat")).toBeInTheDocument();
  });
});
