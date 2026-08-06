import { describe, expect, it } from "vitest";
import { parseSseFrames, takeFrames } from "./sse";

describe("parseSseFrames", () => {
  it("parses event + data frames", () => {
    const raw = "event: start\ndata: {}\n\nevent: delta\ndata: {\"delta\":\"hi\"}\n\n";
    const frames = parseSseFrames(raw);
    expect(frames).toEqual([
      { event: "start", data: "{}" },
      { event: "delta", data: "{\"delta\":\"hi\"}" },
    ]);
  });
});

describe("takeFrames", () => {
  it("returns complete frames and keeps the partial tail", () => {
    const { frames, rest } = takeFrames("event: start\ndata: {}\n\nevent: delta\ndata: {\"d");
    expect(frames).toEqual([{ event: "start", data: "{}" }]);
    expect(rest).toBe("event: delta\ndata: {\"d");
  });
});
