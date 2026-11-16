import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, errorMessage, request } from "./client";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("request", () => {
  it("returns undefined for 204 responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(null, { status: 204 })),
    );

    await expect(
      request<void>("/resource", { method: "DELETE" }),
    ).resolves.toBeUndefined();
  });

  it("parses structured API errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: { code: "DUPLICATE_FILE", message: "资料集中已存在内容相同的文件" },
          }),
          { status: 409, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    await expect(request("/documents")).rejects.toMatchObject({
      status: 409,
      code: "DUPLICATE_FILE",
      message: "资料集中已存在内容相同的文件",
    });
  });

  it("maps network failures to a readable message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("failed")));

    const error = await request("/documents").catch((value: unknown) => value);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe("NETWORK_ERROR");
    expect(errorMessage(error)).toContain("网络异常");
  });
});
