import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import * as agentsApi from "../api/agents";
import * as agentChatApi from "../api/agent-chat";
import AgentsDetail from "./AgentsDetail";

vi.mock("../api/agents", () => ({
  fetchAgent: vi.fn(),
  fetchProviders: vi.fn(),
  updateAgent: vi.fn(),
  deleteProviderKey: vi.fn(),
  upsertProviderKey: vi.fn(),
  startScout: vi.fn(),
  finishScout: vi.fn(),
}));

vi.mock("../api/agent-chat", () => ({
  fetchAgentThreads: vi.fn(),
  createAgentThread: vi.fn(),
  fetchAgentMessages: vi.fn(),
  fetchAgentPrompt: vi.fn(),
  saveAgentPrompt: vi.fn(),
}));

function renderDetail(name: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }} initialEntries={[`/agents/${name}`]}>
        <Routes>
          <Route path="/agents/:name" element={<AgentsDetail />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AgentsDetail", () => {
  it("renders chat + prompt editor for head", async () => {
    vi.mocked(agentsApi.fetchAgent).mockResolvedValue({
      agent_name: "head",
      display_name: "Head",
      mission_prompt: "m",
      enabled_tools: ["llm_chat"],
      model: null,
      default_seed_query: null,
      updated_at: null,
      available_tools: [],
    });
    vi.mocked(agentsApi.fetchProviders).mockResolvedValue([]);
    vi.mocked(agentChatApi.fetchAgentThreads).mockResolvedValue([
      { id: "t1", title: "planning", created_at: null, updated_at: null },
    ]);
    vi.mocked(agentChatApi.fetchAgentMessages).mockResolvedValue([]);
    vi.mocked(agentChatApi.fetchAgentPrompt).mockResolvedValue({
      agent_name: "head",
      exists: true,
      content: "# Head",
      resolved_prompt: "# Head",
    });

    renderDetail("head");

    expect(await screen.findByText("Head")).toBeInTheDocument();
    expect(await screen.findByText("System prompt (agent.md)")).toBeInTheDocument();

    fireEvent.click(await screen.findByText("planning"));
    expect(screen.getByPlaceholderText("Message the Head…")).toBeInTheDocument();
  });

  it("shows the prompt editor for discovery", async () => {
    vi.mocked(agentsApi.fetchAgent).mockResolvedValue({
      agent_name: "discovery",
      display_name: "Discovery (Scout)",
      mission_prompt: "m",
      enabled_tools: ["llm_chat"],
      model: null,
      default_seed_query: "digital marketing agencies Tunisia",
      updated_at: null,
      available_tools: [],
    });
    vi.mocked(agentsApi.fetchProviders).mockResolvedValue([]);
    vi.mocked(agentChatApi.fetchAgentPrompt).mockResolvedValue({
      agent_name: "discovery",
      exists: true,
      content: "# Discovery",
      resolved_prompt: "# Discovery",
    });

    renderDetail("discovery");

    expect(await screen.findByText("Discovery (Scout)")).toBeInTheDocument();
    expect(await screen.findByText("System prompt (agent.md)")).toBeInTheDocument();
    expect(screen.getByDisplayValue("# Discovery")).toBeInTheDocument();
  });

  it("renders chat + prompt editor + provider keys for qualifier (roster-only)", async () => {
    vi.mocked(agentsApi.fetchAgent).mockResolvedValue({
      agent_name: "qualifier",
      display_name: "Qualifier",
      mission_prompt: null,
      enabled_tools: ["llm_chat"],
      model: null,
      default_seed_query: null,
      updated_at: null,
      available_tools: [
        {
          id: "llm_chat",
          label: "LiteLLM / LM Studio chat",
          agents: ["discovery", "head", "qualifier"],
        },
      ],
    });
    vi.mocked(agentsApi.fetchProviders).mockResolvedValue([]);
    vi.mocked(agentChatApi.fetchAgentThreads).mockResolvedValue([
      { id: "t1", title: "scoring", created_at: null, updated_at: null },
    ]);
    vi.mocked(agentChatApi.fetchAgentMessages).mockResolvedValue([]);
    vi.mocked(agentChatApi.fetchAgentPrompt).mockResolvedValue({
      agent_name: "qualifier",
      exists: false,
      content: "",
      resolved_prompt: "",
    });

    renderDetail("qualifier");

    expect(await screen.findByText("Qualifier")).toBeInTheDocument();
    expect(await screen.findByText("System prompt (agent.md)")).toBeInTheDocument();
    expect(
      screen.getByText("Provider API keys (hashed fingerprint shown)"),
    ).toBeInTheDocument();

    fireEvent.click(await screen.findByText("scoring"));
    expect(screen.getByPlaceholderText("Message the Qualifier…")).toBeInTheDocument();
  });
});
