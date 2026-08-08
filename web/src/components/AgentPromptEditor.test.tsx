import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import * as agentChatApi from "../api/agent-chat";
import { AgentPromptEditor } from "./AgentPromptEditor";

vi.mock("../api/agent-chat", () => ({
  fetchAgentPrompt: vi.fn(),
  saveAgentPrompt: vi.fn(),
}));

function renderEditor() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AgentPromptEditor agentName="head" />
    </QueryClientProvider>,
  );
}

describe("AgentPromptEditor", () => {
  it("loads and shows the prompt", async () => {
    vi.mocked(agentChatApi.fetchAgentPrompt).mockResolvedValue({
      agent_name: "head",
      exists: true,
      content: "# Head Be decisive.",
      resolved_prompt: "# Head Be decisive.",
    });
    renderEditor();
    expect(await screen.findByDisplayValue("# Head Be decisive.")).toBeInTheDocument();
  });

  it("saves edits and flashes", async () => {
    vi.mocked(agentChatApi.fetchAgentPrompt).mockResolvedValue({
      agent_name: "head",
      exists: true,
      content: "old",
      resolved_prompt: "old",
    });
    vi.mocked(agentChatApi.saveAgentPrompt).mockResolvedValue({
      agent_name: "head",
      exists: true,
      content: "new",
      resolved_prompt: "new",
    });
    renderEditor();
    const ta = await screen.findByDisplayValue("old");
    fireEvent.change(ta, { target: { value: "new" } });
    fireEvent.click(screen.getByText("Save prompt"));
    await waitFor(() =>
      expect(agentChatApi.saveAgentPrompt).toHaveBeenCalledWith("head", "new"),
    );
    expect(await screen.findByText("Prompt saved.")).toBeInTheDocument();
  });
});
