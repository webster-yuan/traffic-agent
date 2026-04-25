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
      () => {}
    );

    expect(fetch).toHaveBeenCalledTimes(1);
  });
});
