import { afterEach, describe, expect, it, vi } from "vitest";
import { dispatchAgent } from "./agents";
import { fetchAgentRuns, fetchPipelineRun, fetchPipelineRuns } from "./runs";
import type { AgentRun, PipelineRun } from "./types";

afterEach(() => {
  vi.unstubAllGlobals();
});

function jsonResponse(body: unknown) {
  return {
    ok: true,
    status: 200,
    json: async () => body,
  };
}

const run: PipelineRun = {
  id: "r-1",
  trigger: "agent:head",
  seed_query: "find plumbers",
  status: "running",
  started_at: "2026-08-08T00:00:00",
  finished_at: null,
  meta: null,
};

describe("dispatchAgent", () => {
  it("POSTs to the agent dispatch endpoint with the body", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(run));
    vi.stubGlobal("fetch", fetchMock);

    const out = await dispatchAgent("head", { seed_query: "find plumbers" });

    expect(out.id).toBe("r-1");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/agents/head/dispatch",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ seed_query: "find plumbers" }),
      }),
    );
  });
});

describe("fetchAgentRuns", () => {
  it("builds agent_name + limit params", async () => {
    const runs: AgentRun[] = [
      {
        id: "ar-1",
        pipeline_run_id: "r-1",
        agent_name: "head",
        model: null,
        status: "success",
        input_summary: null,
        output_summary: null,
        output_json: null,
        apis_consumed: null,
        records_processed: null,
        error_message: null,
        started_at: null,
        finished_at: null,
      },
    ];
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(runs));
    vi.stubGlobal("fetch", fetchMock);

    const out = await fetchAgentRuns("head", undefined, 20);

    expect(out).toHaveLength(1);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/agent-runs?agent_name=head&limit=20",
      expect.anything(),
    );
  });
});

describe("fetchPipelineRun", () => {
  it("GETs the pipeline run by id", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(run));
    vi.stubGlobal("fetch", fetchMock);

    const out = await fetchPipelineRun("r-1");

    expect(out.id).toBe("r-1");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/pipeline-runs/r-1",
      expect.anything(),
    );
  });
});

describe("fetchPipelineRuns", () => {
  it("sets the limit param", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([run]));
    vi.stubGlobal("fetch", fetchMock);

    const out = await fetchPipelineRuns(20);

    expect(out).toHaveLength(1);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/pipeline-runs?limit=20",
      expect.anything(),
    );
  });
});
