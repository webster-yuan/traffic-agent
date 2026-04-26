import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

vi.mock("../api/trafficApi", () => ({
  generateTrafficStream: vi.fn(),
  listHistory: vi.fn().mockResolvedValue({ items: [] }),
  cancelGenerate: vi.fn().mockResolvedValue({ success: true }),
  deleteHistory: vi.fn().mockResolvedValue({ success: true }),
  downloadUrl: (sessionId: string) => `http://localhost/${sessionId}`,
  langsmithTraceUrl: (sessionId: string) => `http://langsmith/${sessionId}`,
}));

import { generateTrafficStream } from "../api/trafficApi";
import { useTrafficStore } from "./trafficStore";

const mockGenerateTrafficStream = vi.mocked(generateTrafficStream);

describe("trafficStore", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    mockGenerateTrafficStream.mockReset();
    mockGenerateTrafficStream.mockImplementation(
      (_payload, onStart, onStageStart, _onStageProgress, onStageComplete, onFinalize, onComplete) => {
        onStart("sess_123")
        onStageStart({ stage: "generate", progress: 45 })
        onStageComplete({ stage: "generate", status: "success", progress: 60, elapsed_ms: 1200 })
        onFinalize({ download_url: "/download/sess_123" })
        onComplete({ success: true })
      }
    );
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
    expect(store.stageSteps.find((step) => step.stage === "generate")?.elapsedMs).toBe(1200);
  });

  it("inferScenario should return mapped scenario", () => {
    const store = useTrafficStore();
    expect(store.inferScenario("ride_hailing")).toBe("通勤高峰");
  });

  it("retryLastGenerate should rerun the last failed payload", async () => {
    mockGenerateTrafficStream.mockImplementationOnce(
      (_payload, onStart, onStageStart, _onStageProgress, _onStageComplete, _onFinalize, _onComplete, onError) => {
        onStart("sess_failed")
        onStageStart({ stage: "generate", progress: 45 })
        onError("LLM failed")
      }
    );

    const store = useTrafficStore();
    await store.startGenerate({
      industry: "ride_hailing",
      count: 2,
      stage: "standard",
    });

    expect(store.errorMessage).toBe("LLM failed");
    expect(store.stageSteps.find((step) => step.stage === "generate")?.status).toBe("failed");

    await store.retryLastGenerate();

    expect(mockGenerateTrafficStream).toHaveBeenCalledTimes(2);
    expect(store.errorMessage).toBe("");
    expect(store.progress).toBe(100);
  });
});
