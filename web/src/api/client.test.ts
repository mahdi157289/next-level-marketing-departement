import { afterEach, describe, expect, it, vi } from "vitest";
import { apiGet } from "./client";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("apiGet", () => {
  it("returns parsed json on 200", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: "ok" }),
    }));
    const out = await apiGet<{ status: string }>("/api/health");
    expect(out.status).toBe("ok");
  });

  it("throws ApiError with detail on non-ok", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ detail: "not found" }),
      statusText: "Not Found",
    }));
    await expect(apiGet("/api/leads/x")).rejects.toMatchObject({
      status: 404,
      message: "not found",
    });
  });
});
