import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchAgentPrompt, fetchAgentThreads, saveAgentPrompt, streamAgentTurn } from "./agent-chat";

afterEach(() => {
  vi.unstubAllGlobals();
});

function jsonResponse(body: unknown) {
  return { ok: true, status: 200, json: async () => body };
}

describe("agent-chat api", () => {
  it("fetchAgentThreads hits the agent-scoped URL", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([]));
    vi.stubGlobal("fetch", fetchMock);
    await fetchAgentThreads("head");
    expect(fetchMock).toHaveBeenCalledWith("/api/agents/head/threads?limit=50", expect.anything());
  });

  it("fetchAgentPrompt GETs the prompt file", async () => {
    const prompt = { agent_name: "head", exists: true, content: "# x", resolved_prompt: "# x" };
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(prompt));
    vi.stubGlobal("fetch", fetchMock);
    await fetchAgentPrompt("head");
    expect(fetchMock).toHaveBeenCalledWith("/api/agents/head/prompt", expect.anything());
  });

  it("saveAgentPrompt PUTs the content", async () => {
    const prompt = { agent_name: "head", exists: true, content: "x", resolved_prompt: "x" };
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(prompt));
    vi.stubGlobal("fetch", fetchMock);
    const out = await saveAgentPrompt("head", "x");
    expect(out.content).toBe("x");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/agents/head/prompt",
      expect.objectContaining({ method: "PUT", body: JSON.stringify({ content: "x" }) }),
    );
  });

  it("streamAgentTurn POSTs to the agent-scoped URL", async () => {
    const onDone = vi.fn();
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode("event: start\ndata: {}\n\n"));
        controller.enqueue(new TextEncoder().encode("event: done\ndata: {\"thread_id\":\"t1\",\"assistant\":\"hi\",\"tool_calls\":0}\n\n"));
        controller.close();
      },
    });
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, body });
    vi.stubGlobal("fetch", fetchMock);
    await streamAgentTurn("head", "t1", "hello", { onDone });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/agents/head/threads/t1/messages",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ content: "hello" }) }),
    );
    expect(onDone).toHaveBeenCalledWith({ thread_id: "t1", assistant: "hi", tool_calls: 0 });
  });
});
