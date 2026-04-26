import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import type { HistoryItem } from "../api/trafficApi";

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

function historyItem(overrides: Partial<HistoryItem>): HistoryItem {
  return {
    session_id: "sess_001",
    industry: "ride_hailing",
    scenario: "通勤高峰",
    stage: "quick",
    status: "completed",
    requested_count: 2,
    record_count: 2,
    quality_score: 88,
    trace_thread_id: "traffic_sess_001",
    error_message: null,
    started_at: null,
    completed_at: null,
    created_at: "2026-04-26T10:00:00Z",
    updated_at: "2026-04-26T10:01:00Z",
    ...overrides,
  };
}

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

  it("filteredHistory should apply history filters", () => {
    const store = useTrafficStore();
    store.history = [
      historyItem({ session_id: "ride_ok", industry: "ride_hailing", quality_score: 91 }),
      historyItem({
        session_id: "delivery_failed",
        industry: "delivery",
        status: "failed",
        quality_score: null,
        error_message: "LLM failed",
      }),
    ];

    store.historyFilters.industry = "ride_hailing";
    store.historyFilters.minQuality = "90";

    expect(store.filteredHistory.map((item) => item.session_id)).toEqual(["ride_ok"]);

    store.resetHistoryFilters();
    store.historyFilters.keyword = "llm";

    expect(store.filteredHistory.map((item) => item.session_id)).toEqual(["delivery_failed"]);
  });
});
