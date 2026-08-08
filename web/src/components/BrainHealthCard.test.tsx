import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import BrainHealthCard from "./BrainHealthCard";
import * as brainApi from "../api/brain";

vi.mock("../api/brain", () => ({
  fetchBrainStatus: vi.fn(),
  fetchBrainMetrics: vi.fn(),
  fetchWorkerStatus: vi.fn(),
}));

function renderCard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <BrainHealthCard />
    </QueryClientProvider>,
  );
}

describe("BrainHealthCard", () => {
  it("renders lamps, telemetry, and recent brain requests", async () => {
    vi.mocked(brainApi.fetchBrainStatus).mockResolvedValue({
      available: true,
      vertices: 12,
      edges: 20,
    });
    vi.mocked(brainApi.fetchWorkerStatus).mockResolvedValue({
      active: 1,
      max_workers: 3,
      queued: 2,
    });
    vi.mocked(brainApi.fetchBrainMetrics).mockResolvedValue({
      metrics: [
        {
          id: "m1",
          agent_name: "head",
          domain: "saas",
          query: "what we offer",
          query_hash: "h1",
          latency_ms: 120,
          cache_hit: true,
          vector_hits: 0,
          graph_hits: 0,
          created_at: "2026-08-08T00:00:00",
        },
        {
          id: "m2",
          agent_name: "scout",
          domain: null,
          query: "new leads",
          query_hash: "h2",
          latency_ms: 340,
          cache_hit: false,
          vector_hits: 3,
          graph_hits: 1,
          created_at: null,
        },
      ],
    });

    renderCard();

    expect(await screen.findByText("Brain health")).toBeInTheDocument();
    expect(await screen.findByText(/Cache hit: 50%/)).toBeInTheDocument();
    expect(screen.getByText(/Avg latency: 230ms/)).toBeInTheDocument();
    expect(screen.getByText(/Workers: 1\/3/)).toBeInTheDocument();
    expect(screen.getByText(/Queued: 2/)).toBeInTheDocument();

    expect(screen.getByText("head")).toBeInTheDocument();
    expect(screen.getByText("scout")).toBeInTheDocument();
    expect(screen.getByText("what we offer")).toBeInTheDocument();
    expect(screen.getByText("cache")).toBeInTheDocument();
    expect(screen.getByText("graph×1")).toBeInTheDocument();
  });

  it("shows placeholder when there is no activity", async () => {
    vi.mocked(brainApi.fetchBrainStatus).mockResolvedValue({
      available: false,
      vertices: 0,
      edges: 0,
    });
    vi.mocked(brainApi.fetchWorkerStatus).mockResolvedValue({
      active: 0,
      max_workers: 3,
      queued: 0,
    });
    vi.mocked(brainApi.fetchBrainMetrics).mockResolvedValue({ metrics: [] });

    renderCard();

    expect(await screen.findByText("No brain activity yet.")).toBeInTheDocument();
    expect(screen.getByText(/Cache hit: —/)).toBeInTheDocument();
  });
});
