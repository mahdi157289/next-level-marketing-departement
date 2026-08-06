import { afterEach, describe, expect, it, vi } from "vitest";
import { streamScoutTurn } from "./scout";

afterEach(() => {
  vi.unstubAllGlobals();
});

function mockReaderStream(chunks: Uint8Array[], failAfter = Infinity): ReadableStream<Uint8Array> {
  return new ReadableStream<Uint8Array>({
    async pull(controller) {
      if (failAfter <= 0) {
        controller.error(new Error("boom"));
        return;
      }
      failAfter--;
      if (chunks.length === 0) {
        controller.close();
        return;
      }
      controller.enqueue(chunks.shift()!);
    },
  });
}

function handlerSpies() {
  const onStart = vi.fn();
  const onDelta = vi.fn();
  const onDone = vi.fn();
  const onError = vi.fn();
  return { onStart, onDelta, onDone, onError };
}

describe("streamScoutTurn error paths", () => {
  it("reports HTTP status when response body is empty on non-ok", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      text: async () => "",
    }));
    const h = handlerSpies();
    await streamScoutTurn("t1", "hi", h);
    expect(h.onError).toHaveBeenCalledWith("HTTP 500");
    expect(h.onStart).not.toHaveBeenCalled();
  });

  it("reports response body text on non-ok", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      text: async () => "validation failed",
    }));
    const h = handlerSpies();
    await streamScoutTurn("t1", "hi", h);
    expect(h.onError).toHaveBeenCalledWith("validation failed");
  });

  it("reports no-response-body when stream is missing", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      body: null,
    }));
    const h = handlerSpies();
    await streamScoutTurn("t1", "hi", h);
    expect(h.onError).toHaveBeenCalledWith("No response body");
  });

  it("reports a rejected fetch as an error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network down")));
    const h = handlerSpies();
    await streamScoutTurn("t1", "hi", h);
    expect(h.onError).toHaveBeenCalledWith("network down");
  });

  it("reports a stream read failure as an error", async () => {
    const body = mockReaderStream([], 0);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, body }));
    const h = handlerSpies();
    await streamScoutTurn("t1", "hi", h);
    expect(h.onError).toHaveBeenCalledWith("boom");
  });
});
