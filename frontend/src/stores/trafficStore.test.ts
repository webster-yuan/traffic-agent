import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import type { HistoryFilters, HistoryItem } from "../api/trafficApi";

vi.mock("../api/trafficApi", () => ({
  generateTrafficStream: vi.fn(),
  listHistory: vi.fn().mockResolvedValue({ items: [] }),
  cancelGenerate: vi.fn().mockResolvedValue({ success: true }),
  deleteHistory: vi.fn().mockResolvedValue({ success: true }),
  downloadUrl: (sessionId: string, format: 'csv' | 'json' | 'parquet' = 'csv') => {
    if (format === 'json') return `http://localhost/${sessionId}?format=json`
    if (format === 'parquet') return `http://localhost/${sessionId}?format=parquet`
    return `http://localhost/${sessionId}`
  },
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
    quality_detail: null,
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
    expect(store.inferScenario("finance")).toBe("交易高峰");
    expect(store.inferScenario("healthcare")).toBe("门诊就诊时段");
    expect(store.inferScenario("media")).toBe("晚间播放高峰");
    expect(store.inferScenario("social")).toBe("内容互动高峰");
    expect(store.inferScenario("gaming")).toBe("在线对战时段");
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

  it("refreshHistory should pass filters to listHistory API", async () => {
    const { listHistory } = await import("../api/trafficApi");
    const mockedListHistory = vi.mocked(listHistory);
    mockedListHistory.mockResolvedValue({
      total: 1,
      page: 1,
      page_size: 20,
      total_pages: 1,
      items: [
        historyItem({ session_id: "ride_ok", industry: "ride_hailing", quality_score: 91 }),
      ],
    });

    const store = useTrafficStore();
    store.historyFilters.industry = "ride_hailing";
    store.historyFilters.minQuality = "90";

    await store.refreshHistory();

    expect(mockedListHistory).toHaveBeenCalledWith(1, 20, {
      keyword: undefined,
      industry: "ride_hailing",
      stage: undefined,
      status: undefined,
      dateFrom: undefined,
      dateTo: undefined,
      minQuality: "90",
    });
    expect(store.history).toHaveLength(1);
    expect(store.history[0].session_id).toBe("ride_ok");
    expect(store.historyTotal).toBe(1);
  });

  it("resetHistoryFilters should clear filters and refresh", async () => {
    const { listHistory } = await import("../api/trafficApi");
    const mockedListHistory = vi.mocked(listHistory);
    mockedListHistory.mockResolvedValue({
      total: 2,
      page: 1,
      page_size: 20,
      total_pages: 1,
      items: [
        historyItem({ session_id: "ride_ok", industry: "ride_hailing" }),
        historyItem({ session_id: "delivery_failed", industry: "delivery", status: "failed" }),
      ],
    });

    const store = useTrafficStore();
    store.historyFilters.industry = "ride_hailing";
    store.historyFilters.keyword = "llm";

    await store.resetHistoryFilters();

    const expectedFilters: Partial<HistoryFilters> = {
      keyword: undefined,
      industry: undefined,
      stage: undefined,
      status: undefined,
      dateFrom: undefined,
      dateTo: undefined,
      minQuality: undefined,
    };
    expect(mockedListHistory).toHaveBeenCalledWith(1, 20, expectedFilters);
    expect(store.historyFilters.industry).toBe("");
    expect(store.historyFilters.keyword).toBe("");
    expect(store.history).toHaveLength(2);
  });
});
