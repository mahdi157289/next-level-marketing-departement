import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import * as agentChatApi from "../api/agent-chat";
import * as scoutApi from "../api/scout";
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

function renderHQ() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ScoutHQ />
    </QueryClientProvider>,
  );
}

describe("ScoutHQ", () => {
  it("renders the chat and the system prompt editor", async () => {
    vi.mocked(scoutApi.fetchMissions).mockResolvedValue([]);
    vi.mocked(agentChatApi.fetchAgentThreads).mockResolvedValue([]);
    vi.mocked(agentChatApi.fetchAgentPrompt).mockResolvedValue({
      agent_name: "discovery",
      exists: true,
      content: "# Discovery",
      resolved_prompt: "# Discovery",
    });

    renderHQ();

    expect(screen.getByText("Start Scout")).toBeInTheDocument();
    expect(await screen.findByText("System prompt (agent.md)")).toBeInTheDocument();
    expect(screen.getByDisplayValue("# Discovery")).toBeInTheDocument();
  });
});
