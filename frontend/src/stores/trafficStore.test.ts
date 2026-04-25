import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

vi.mock("../api/trafficApi", () => ({
  generateTrafficStream: vi.fn((_payload, onStart, _onStageStart, onStageComplete, onFinalize, onComplete, _onError) => {
    onStart("sess_123")
    onStageComplete({ stage: "generate", status: "success" })
    onFinalize({ download_url: "/download/sess_123" })
    onComplete({ success: true })
  }),
  listHistory: vi.fn().mockResolvedValue({ items: [] }),
  cancelGenerate: vi.fn().mockResolvedValue({ success: true }),
  deleteHistory: vi.fn().mockResolvedValue({ success: true }),
  downloadUrl: (sessionId: string) => `http://localhost/${sessionId}`,
}));

import { useTrafficStore } from "./trafficStore";

describe("trafficStore", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("startGenerate should update result and sessionId", async () => {
    const store = useTrafficStore();
    await store.startGenerate({
      industry: "ride_hailing",
      count: 2,
      stage: "standard",
    });

    expect(store.sessionId).toBe("sess_123");
    expect(store.progress).toBe(100);
    expect(store.running).toBe(false);
  });

  it("inferScenario should return mapped scenario", () => {
    const store = useTrafficStore();
    expect(store.inferScenario("ride_hailing")).toBe("通勤高峰");
  });
});
