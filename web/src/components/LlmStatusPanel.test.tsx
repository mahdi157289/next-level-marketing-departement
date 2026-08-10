import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import * as llmApi from "../api/llm";
import { LlmStatusPanel } from "./LlmStatusPanel";

vi.mock("../api/llm", () => ({
  fetchLlmStatus: vi.fn(),
}));

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <LlmStatusPanel onClose={() => {}} />
    </QueryClientProvider>,
  );
}

describe("LlmStatusPanel", () => {
  it("renders provider, base URL, key state, models, and reachability", async () => {
    vi.mocked(llmApi.fetchLlmStatus).mockResolvedValue({
      provider: "OpenRouter",
      base_url: "https://openrouter.ai/api/v1",
      api_key_set: true,
      models: [
        { agent: "discovery", model: "google/gemma-4-26b-a4b-it:free" },
        { agent: "head", model: "google/gemma-4-26b-a4b-it:free" },
      ],
      reachable: true,
      detail: "ok via chat probe",
      checked_at: "2026-08-09T12:00:00",
    });

    renderPanel();

    expect(await screen.findByText("OpenRouter")).toBeInTheDocument();
    expect(screen.getByText("https://openrouter.ai/api/v1")).toBeInTheDocument();
    expect(screen.getByText("Set")).toBeInTheDocument();
    expect(screen.getByText("Yes")).toBeInTheDocument();
    expect(screen.getByText("discovery")).toBeInTheDocument();
    expect(screen.getAllByText("google/gemma-4-26b-a4b-it:free").length).toBe(2);
    expect(screen.getByText("ok via chat probe")).toBeInTheDocument();
  });

  it("shows Not set / No when key missing and provider unreachable", async () => {
    vi.mocked(llmApi.fetchLlmStatus).mockResolvedValue({
      provider: "LM Studio (local)",
      base_url: "http://127.0.0.1:1234/v1",
      api_key_set: false,
      models: [],
      reachable: false,
      detail: "connection refused",
      checked_at: "2026-08-09T12:00:00",
    });

    renderPanel();

    expect(await screen.findByText("LM Studio (local)")).toBeInTheDocument();
    expect(screen.getByText("Not set")).toBeInTheDocument();
    expect(screen.getAllByText("No").length).toBeGreaterThan(0);
    expect(screen.getByText("connection refused")).toBeInTheDocument();
    expect(screen.getByText("No model aliases configured.")).toBeInTheDocument();
  });

  it("refetches when Refresh is clicked", async () => {
    vi.mocked(llmApi.fetchLlmStatus).mockResolvedValue({
      provider: "OpenRouter",
      base_url: "https://openrouter.ai/api/v1",
      api_key_set: true,
      models: [],
      reachable: true,
      detail: "ok",
      checked_at: "2026-08-09T12:00:00",
    });

    renderPanel();
    await screen.findByText("OpenRouter");

    fireEvent.click(screen.getByText("Refresh"));
    expect(llmApi.fetchLlmStatus).toHaveBeenCalled();
  });
});
