import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import * as agentsApi from "../api/agents";
import * as runsApi from "../api/runs";
import * as agentChatApi from "../api/agent-chat";
import * as llmApi from "../api/llm";
import type { AgentRun, PipelineRun } from "../api/types";
import HeadHQ from "./HeadHQ";

vi.mock("../api/agents", () => ({
  dispatchAgent: vi.fn(),
}));

vi.mock("../api/agent-chat", () => ({
  fetchAgentThreads: vi.fn(),
  createAgentThread: vi.fn(),
  fetchAgentMessages: vi.fn(),
  streamAgentTurn: vi.fn(),
  fetchAgentPrompt: vi.fn(),
  saveAgentPrompt: vi.fn(),
}));

vi.mock("../api/runs", () => ({
  fetchAgentRuns: vi.fn(),
  fetchPipelineRun: vi.fn(),
  fetchPipelineRuns: vi.fn(),
}));

vi.mock("../api/llm", () => ({
  fetchLlmStatus: vi.fn(),
}));

const pipelineRun: PipelineRun = {
  id: "r-1",
  trigger: "agent:head",
  seed_query: "find agencies",
  status: "success",
  started_at: "2026-08-08T00:00:00",
  finished_at: "2026-08-08T00:00:03",
  meta: { mode: "dispatch" },
};

const headRun: AgentRun = {
  id: "ar-1",
  pipeline_run_id: "r-1",
  agent_name: "head",
  model: "local",
  status: "success",
  input_summary: "find agencies",
  output_summary: "seed: find agencies",
  output_json: {
    seed_query: "find agencies",
    max_search_results: 8,
    tools: ["web_search", "llm_chat"],
    skill_gaps: ["meta_ads"],
    tool_reasons: { web_search: "broad coverage of the local market" },
    insights: "Prioritize logistics players with weak sites.",
    rationale: "Best coverage of local market.",
  },
  apis_consumed: null,
  records_processed: 0,
  error_message: null,
  started_at: "2026-08-08T00:00:00",
  finished_at: "2026-08-08T00:00:03",
};

const llmStatus = {
  provider: "OpenRouter",
  base_url: "https://openrouter.ai/api/v1",
  api_key_set: true,
  models: [{ agent: "head", model: "google/gemma-4-26b-a4b-it:free" }],
  reachable: true,
  detail: "ok",
  checked_at: "2026-08-09T12:00:00",
};

function renderHQ() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <HeadHQ />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("HeadHQ", () => {
  it("renders the full-size chat by default with toolbar buttons", async () => {
    vi.mocked(runsApi.fetchAgentRuns).mockResolvedValue([]);
    vi.mocked(runsApi.fetchPipelineRuns).mockResolvedValue([]);
    vi.mocked(agentChatApi.fetchAgentThreads).mockResolvedValue([]);
    vi.mocked(llmApi.fetchLlmStatus).mockResolvedValue(llmStatus);

    renderHQ();

    expect(screen.getByText("Select or create a thread to start chatting with the Head.")).toBeInTheDocument();
    expect(screen.getByText("Plan console")).toBeInTheDocument();
    expect(screen.getByText("Edit prompt")).toBeInTheDocument();
    expect(screen.getByText("Recent runs")).toBeInTheDocument();
    expect(await screen.findByText("OpenRouter")).toBeInTheDocument();
  });

  it("dispatches a goal and flashes from the plan console panel", async () => {
    vi.mocked(runsApi.fetchAgentRuns).mockResolvedValue([]);
    vi.mocked(runsApi.fetchPipelineRuns).mockResolvedValue([]);
    vi.mocked(runsApi.fetchPipelineRun).mockResolvedValue(pipelineRun);
    vi.mocked(agentsApi.dispatchAgent).mockResolvedValue(pipelineRun);
    vi.mocked(llmApi.fetchLlmStatus).mockResolvedValue(llmStatus);

    renderHQ();
    fireEvent.click(screen.getByText("Plan console"));
    fireEvent.change(screen.getByPlaceholderText(/Goal/), {
      target: { value: "find plumbers" },
    });
    fireEvent.click(screen.getByText("Make plan"));

    await waitFor(() =>
      expect(agentsApi.dispatchAgent).toHaveBeenCalledWith("head", { seed_query: "find plumbers" }),
    );
    expect(await screen.findByText(/Head dispatched/)).toBeInTheDocument();
  });

  it("renders a completed plan's output_json inside the plan console", async () => {
    vi.mocked(runsApi.fetchAgentRuns).mockResolvedValue([headRun]);
    vi.mocked(runsApi.fetchPipelineRuns).mockResolvedValue([]);
    vi.mocked(runsApi.fetchPipelineRun).mockResolvedValue(pipelineRun);
    vi.mocked(agentsApi.dispatchAgent).mockResolvedValue(pipelineRun);
    vi.mocked(llmApi.fetchLlmStatus).mockResolvedValue(llmStatus);

    renderHQ();
    fireEvent.click(screen.getByText("Plan console"));
    fireEvent.change(screen.getByPlaceholderText(/Goal/), {
      target: { value: "find agencies" },
    });
    fireEvent.click(screen.getByText("Make plan"));

    expect(await screen.findByText("Best coverage of local market.")).toBeInTheDocument();
    expect(screen.getAllByText("web_search, llm_chat").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("meta_ads")).toBeInTheDocument();
    const budgetLabel = screen.getByText("Search budget:");
    expect(budgetLabel.parentElement?.textContent).toMatch(/8/);
    expect(screen.getByText(/Prioritize logistics players with weak sites/)).toBeInTheDocument();
    expect(screen.getByText("web_search: broad coverage of the local market")).toBeInTheDocument();
  });

  it("shows the empty state for history in the recent runs panel", async () => {
    vi.mocked(runsApi.fetchAgentRuns).mockResolvedValue([]);
    vi.mocked(runsApi.fetchPipelineRuns).mockResolvedValue([]);
    vi.mocked(llmApi.fetchLlmStatus).mockResolvedValue(llmStatus);

    renderHQ();
    fireEvent.click(screen.getByText("Recent runs"));
    expect(await screen.findByText("No head runs yet.")).toBeInTheDocument();
    expect(screen.getByText("No pipeline runs yet.")).toBeInTheDocument();
  });

  it("renders a chat thread list for the head agent", async () => {
    vi.mocked(runsApi.fetchAgentRuns).mockResolvedValue([]);
    vi.mocked(runsApi.fetchPipelineRuns).mockResolvedValue([]);
    vi.mocked(llmApi.fetchLlmStatus).mockResolvedValue(llmStatus);
    vi.mocked(agentChatApi.fetchAgentThreads).mockResolvedValue([
      { id: "t1", title: "planning", created_at: null, updated_at: null },
    ]);
    vi.mocked(agentChatApi.fetchAgentMessages).mockResolvedValue([]);

    renderHQ();

    expect(await screen.findByText("planning")).toBeInTheDocument();

    fireEvent.click(screen.getByText("planning"));
    expect(screen.getByPlaceholderText("Message the Head…")).toBeInTheDocument();
  });

  it("opens the system prompt editor in a drawer and saves", async () => {
    vi.mocked(runsApi.fetchAgentRuns).mockResolvedValue([]);
    vi.mocked(runsApi.fetchPipelineRuns).mockResolvedValue([]);
    vi.mocked(llmApi.fetchLlmStatus).mockResolvedValue(llmStatus);
    vi.mocked(agentChatApi.fetchAgentThreads).mockResolvedValue([]);
    vi.mocked(agentChatApi.fetchAgentPrompt).mockResolvedValue({
      agent_name: "head",
      exists: true,
      content: "# Head",
      resolved_prompt: "# Head",
    });
    vi.mocked(agentChatApi.saveAgentPrompt).mockResolvedValue({
      agent_name: "head",
      exists: true,
      content: "# Head v2",
      resolved_prompt: "# Head v2",
    });

    renderHQ();

    expect(screen.queryByText("System prompt (agent.md)")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("Edit prompt"));

    expect(await screen.findByText("System prompt (agent.md)")).toBeInTheDocument();
    const textarea = screen.getByDisplayValue("# Head");
    fireEvent.change(textarea, { target: { value: "# Head v2" } });
    fireEvent.click(screen.getByText("Save prompt"));

    await waitFor(() =>
      expect(agentChatApi.saveAgentPrompt).toHaveBeenCalledWith("head", "# Head v2"),
    );
    expect(await screen.findByText("Prompt saved.")).toBeInTheDocument();
  });

  it("opens the LLM status drawer when the pill is clicked", async () => {
    vi.mocked(runsApi.fetchAgentRuns).mockResolvedValue([]);
    vi.mocked(runsApi.fetchPipelineRuns).mockResolvedValue([]);
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
