import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import * as agentChatApi from "../api/agent-chat";
import * as scoutApi from "../api/scout";
import * as llmApi from "../api/llm";
import ScoutHQ from "./ScoutHQ";

vi.mock("../api/agents", () => ({
  startScout: vi.fn(),
  finishScout: vi.fn(),
}));

vi.mock("../api/agent-chat", () => ({
  fetchAgentThreads: vi.fn(),
  createAgentThread: vi.fn(),
  fetchAgentMessages: vi.fn(),
  streamAgentTurn: vi.fn(),
  fetchAgentPrompt: vi.fn(),
  saveAgentPrompt: vi.fn(),
}));

vi.mock("../api/scout", () => ({
  fetchMissions: vi.fn(),
}));

vi.mock("../api/llm", () => ({
  fetchLlmStatus: vi.fn(),
}));

function renderHQ() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ScoutHQ />
    </QueryClientProvider>,
  );
}

const llmStatus = {
  provider: "OpenRouter",
  base_url: "https://openrouter.ai/api/v1",
  api_key_set: true,
  models: [{ agent: "discovery", model: "google/gemma-4-26b-a4b-it:free" }],
  reachable: true,
  detail: "ok",
  checked_at: "2026-08-09T12:00:00",
};

describe("ScoutHQ", () => {
  it("renders the full-size chat by default", async () => {
    vi.mocked(scoutApi.fetchMissions).mockResolvedValue([]);
    vi.mocked(agentChatApi.fetchAgentThreads).mockResolvedValue([]);
    vi.mocked(llmApi.fetchLlmStatus).mockResolvedValue(llmStatus);

    renderHQ();

    expect(screen.getByText("Select or create a thread to start chatting with the Scout.")).toBeInTheDocument();
    expect(screen.getByText("Edit prompt")).toBeInTheDocument();
    expect(screen.getByText("Scout controls")).toBeInTheDocument();
    expect(await screen.findByText("OpenRouter")).toBeInTheDocument();
  });

  it("opens the prompt editor in a drawer when toggled", async () => {
    vi.mocked(scoutApi.fetchMissions).mockResolvedValue([]);
    vi.mocked(agentChatApi.fetchAgentThreads).mockResolvedValue([]);
    vi.mocked(llmApi.fetchLlmStatus).mockResolvedValue(llmStatus);
    vi.mocked(agentChatApi.fetchAgentPrompt).mockResolvedValue({
      agent_name: "discovery",
      exists: true,
      content: "# Discovery",
      resolved_prompt: "# Discovery",
    });

    renderHQ();

    expect(screen.queryByText("System prompt (agent.md)")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("Edit prompt"));
    expect(await screen.findByText("System prompt (agent.md)")).toBeInTheDocument();
    expect(screen.getByDisplayValue("# Discovery")).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("Close prompt editor"));
    expect(screen.queryByText("System prompt (agent.md)")).not.toBeInTheDocument();
  });

  it("opens the scout controls in a drawer when toggled", async () => {
    vi.mocked(scoutApi.fetchMissions).mockResolvedValue([]);
    vi.mocked(agentChatApi.fetchAgentThreads).mockResolvedValue([]);
    vi.mocked(llmApi.fetchLlmStatus).mockResolvedValue(llmStatus);

    renderHQ();

    expect(screen.queryByText("Start Scout")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("Scout controls"));
    expect(await screen.findByText("Start Scout")).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("Close scout controls"));
    expect(screen.queryByText("Start Scout")).not.toBeInTheDocument();
  });

  it("opens the LLM status drawer when the pill is clicked", async () => {
    vi.mocked(scoutApi.fetchMissions).mockResolvedValue([]);
    vi.mocked(agentChatApi.fetchAgentThreads).mockResolvedValue([]);
    vi.mocked(llmApi.fetchLlmStatus).mockResolvedValue(llmStatus);

    renderHQ();

    expect(screen.queryByText("LLM provider")).not.toBeInTheDocument();
    fireEvent.click(await screen.findByText("OpenRouter"));
    expect(screen.getByText("LLM provider")).toBeInTheDocument();
    expect(screen.getByText("https://openrouter.ai/api/v1")).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("Close LLM status"));
    expect(screen.queryByText("LLM provider")).not.toBeInTheDocument();
  });
});
