import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useScoutChat } from "./useScoutChat";

function sseStream(frames: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const f of frames) controller.enqueue(encoder.encode(f));
      controller.close();
    },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useScoutChat", () => {
  it("streams deltas then calls onTurnDone", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      body: sseStream([
        "event: start\ndata: {}\n\n",
        "event: delta\ndata: {\"delta\":\"Hel\"}\n\n",
        "event: delta\ndata: {\"delta\":\"lo\"}\n\n",
        "event: done\ndata: {\"thread_id\":\"t1\",\"assistant\":\"Hello\",\"tool_calls\":2}\n\n",
      ]),
    }));
    const onTurnDone = vi.fn();
    const { result } = renderHook(() => useScoutChat("t1", onTurnDone));

    act(() => {
      void result.current.send("hi");
    });

    await waitFor(() => expect(result.current.assistantText).toBe("Hello"));
    expect(result.current.toolCalls).toBe(2);
    expect(onTurnDone).toHaveBeenCalledTimes(1);
    expect(result.current.streaming).toBe(false);
  });

  it("surfaces an error event", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      body: sseStream([
        "event: start\ndata: {}\n\n",
        "event: error\ndata: {\"detail\":\"engine blew up\"}\n\n",
      ]),
    }));
    const { result } = renderHook(() => useScoutChat("t1"));

    act(() => {
      void result.current.send("hi");
    });

    await waitFor(() => expect(result.current.error).toBe("engine blew up"));
  });
});
