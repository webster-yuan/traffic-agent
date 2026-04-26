import { afterEach, describe, expect, it, vi } from "vitest";

import { generateTrafficStream } from "./trafficApi";

describe("trafficApi", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("generateTrafficStream should call correct endpoint", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        body: {
          getReader: () => ({
            read: () => Promise.resolve({ done: true, value: undefined }),
          }),
        },
      }),
    );

    generateTrafficStream(
      { industry: "ride_hailing", count: 10, stage: "standard" },
      () => {},
      () => {},
      () => {},
      () => {},
      () => {},
      () => {},
      () => {}
    );

    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("generateTrafficStream should surface server error events", async () => {
    const encoder = new TextEncoder();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        body: {
          getReader: () => {
            const read = vi
              .fn()
              .mockResolvedValueOnce({
                done: false,
                value: encoder.encode('event: error\ndata: {"message":"LLM failed"}\n\n'),
              })
              .mockResolvedValueOnce({ done: true, value: undefined });
            return { read };
          },
        },
      }),
    );

    const error = new Promise<string>((resolve) => {
      generateTrafficStream(
        { industry: "ride_hailing", count: 10, stage: "standard" },
        () => {},
        () => {},
        () => {},
        () => {},
        () => {},
        () => {},
        resolve
      );
    });

    await expect(error).resolves.toBe("LLM failed");
  });
});
