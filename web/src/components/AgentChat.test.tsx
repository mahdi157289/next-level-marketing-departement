import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import * as agentChatApi from "../api/agent-chat";
import { AgentChat } from "./AgentChat";

vi.mock("../api/agent-chat", () => ({
  fetchAgentThreads: vi.fn(),
  createAgentThread: vi.fn(),
  fetchAgentMessages: vi.fn(),
  streamAgentTurn: vi.fn(),
}));

function renderChat() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AgentChat agentName="head" label="Head" />
    </QueryClientProvider>,
  );
}

describe("AgentChat", () => {
  it("lists threads for the agent", async () => {
    vi.mocked(agentChatApi.fetchAgentThreads).mockResolvedValue([
      { id: "t1", title: "planning", created_at: null, updated_at: null },
    ]);
    renderChat();
    expect(await screen.findByText("planning")).toBeInTheDocument();
  });

  it("sends a message via streamAgentTurn", async () => {
    vi.mocked(agentChatApi.fetchAgentThreads).mockResolvedValue([
      { id: "t1", title: "planning", created_at: null, updated_at: null },
    ]);
    const msgs: Array<Record<string, unknown>> = [];
    vi.mocked(agentChatApi.fetchAgentMessages).mockImplementation(async () => [...msgs]);
    vi.mocked(agentChatApi.streamAgentTurn).mockImplementation(async (_name, _tid, _c, handlers) => {
      msgs.push({
        id: "m2",
        thread_id: "t1",
        role: "assistant",
        content: "hello",
        tool_name: null,
        tool_args: null,
        tool_result: null,
        created_at: null,
      });
      handlers.onStart?.();
      handlers.onDelta?.("hello", 0);
      handlers.onDone?.({ thread_id: "t1", assistant: "hello", tool_calls: 0 });
    });
    renderChat();

    const pill = await screen.findByText("planning");
    fireEvent.click(pill);

    await waitFor(() => expect(agentChatApi.fetchAgentMessages).toHaveBeenCalledTimes(1));
    await new Promise((r) => setTimeout(r, 0));

    const input = screen.getByPlaceholderText("Message the Head…");
    fireEvent.change(input, { target: { value: "plan next quarter" } });
    fireEvent.click(screen.getByText("Send"));

    await waitFor(() =>
      expect(agentChatApi.streamAgentTurn).toHaveBeenCalledWith(
        "head",
        "t1",
        "plan next quarter",
        expect.anything(),
      ),
    );
    expect(await screen.findByText("hello")).toBeInTheDocument();
  });
});
