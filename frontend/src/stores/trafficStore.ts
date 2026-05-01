import { defineStore } from 'pinia'
import {
  cancelGenerate,
  deleteHistory,
  downloadUrl,
  generateTrafficStream,
  getBatchStatus,
  langsmithTraceUrl,
  listHistory,
  reportUrl,
  startBatch,
  type BatchTaskItem,
  type BatchTaskStatus,
  type GeneratePayload,
  type HistoryFilters,
  type HistoryItem,
  type StageComplete,
  type StageProgress,
} from '../api/trafficApi'

const INDUSTRY_SCENARIO: Record<string, string> = {
  government: '工作日办公时间',
  ecommerce: '全天候配送',
  short_video: '内容创作时段',
  ride_hailing: '通勤高峰',
  logistics: '夜间运输',
  delivery: '饭点高峰',
  finance: '交易高峰',
  healthcare: '门诊就诊时段',
  media: '晚间播放高峰',
  social: '内容互动高峰',
  gaming: '在线对战时段',
  custom: '自定义场景',
}

const STAGE_NAME: Record<string, string> = {
  rag: 'RAG检索',
  generate: '流量生成',
  eval: '质量评估',
  identity: '身份校验',
}

type StageStatus = 'pending' | 'running' | 'completed' | 'failed'

type StageStep = {
  stage: string
  name: string
  status: StageStatus
  progress: number
  elapsedMs?: number
  retry?: number
}

const STAGE_ORDER = ['rag', 'generate', 'eval', 'identity']

function createStageSteps(): StageStep[] {
  return STAGE_ORDER.map((stage) => ({
    stage,
    name: STAGE_NAME[stage],
    status: 'pending',
    progress: 0,
  }))
}

function createHistoryFilters(): HistoryFilters {
  return {
    keyword: '',
    industry: '',
    stage: '',
    status: '',
    dateFrom: '',
    dateTo: '',
    minQuality: '',
  }
}

export const useTrafficStore = defineStore('traffic', {
  state: () => ({
    running: false,
    sessionId: '',
    progressText: '等待开始',
    progress: 0,
    stageSteps: createStageSteps(),
    errorMessage: '',
    lastPayload: null as GeneratePayload | null,
    resultMessage: '',
    downloadPath: '',
    history: [] as HistoryItem[],
    historyPage: 1,
    historyTotalPages: 1,
    historyTotal: 0,
    historyFilters: createHistoryFilters(),
    abortController: null as AbortController | null,
    // batch state
    batchId: '',
    batchTasks: [] as BatchTaskStatus[],
    batchRunning: false,
  }),
  getters: {
  },
  actions: {
    inferScenario(industry: string) {
      return INDUSTRY_SCENARIO[industry] || '自定义场景'
    },
    async refreshHistory(page?: number) {
      const p = page ?? this.historyPage
      const filters = this.historyFilters
      const data = await listHistory(p, 20, {
        keyword: filters.keyword || undefined,
        industry: filters.industry || undefined,
        stage: filters.stage || undefined,
        status: filters.status || undefined,
        dateFrom: filters.dateFrom || undefined,
        dateTo: filters.dateTo || undefined,
        minQuality: filters.minQuality || undefined,
      })
      this.history = data.items
      this.historyPage = data.page
      this.historyTotalPages = data.total_pages
      this.historyTotal = data.total
    },
    async goHistoryPage(page: number) {
      if (page < 1 || page > this.historyTotalPages) return
      await this.refreshHistory(page)
    },
    resetStageSteps() {
      this.stageSteps = createStageSteps()
    },
    resetHistoryFilters() {
      this.historyFilters = createHistoryFilters()
      this.refreshHistory(1)
    },
    markStageStart(event: StageProgress) {
      const step = this.stageSteps.find((item) => item.stage === event.stage)
      if (!step) return
      step.status = 'running'
      step.progress = event.progress ?? step.progress
      this.progress = Math.max(this.progress, event.progress ?? this.progress)
      this.progressText = `正在${step.name}...`
    },
    markStageProgress(event: StageProgress) {
      const step = this.stageSteps.find((item) => item.stage === event.stage)
      if (!step) return
      step.retry = event.retry
      step.progress = event.progress ?? step.progress
      this.progress = Math.max(this.progress, event.progress ?? this.progress)
      this.progressText = `${step.name}进行中${event.retry ? `，已重试 ${event.retry} 次` : ''}`
    },
    markStageComplete(event: StageComplete) {
      const step = this.stageSteps.find((item) => item.stage === event.stage)
      if (!step) return
      step.status = 'completed'
      step.progress = event.progress ?? 100
      step.elapsedMs = event.elapsed_ms ?? undefined
      this.progress = Math.max(this.progress, event.progress ?? this.progress)
      this.progressText = `${step.name}完成`
    },
    markRunningStageFailed() {
      const step =
        this.stageSteps.find((item) => item.status === 'running') ||
        this.stageSteps.find((item) => item.status === 'pending')
      if (step) step.status = 'failed'
    },
    async startGenerate(payload: GeneratePayload) {
      this.running = true
      this.sessionId = ''
      this.progress = 0
      this.progressText = '正在连接...'
      this.resetStageSteps()
      this.errorMessage = ''
      this.lastPayload = { ...payload }
      this.resultMessage = ''
      this.downloadPath = ''
      this.abortController?.abort()
      this.abortController = new AbortController()

      generateTrafficStream(
        payload,
        (sessionId) => {
          this.sessionId = sessionId
          this.progress = 10
          this.progressText = '已连接，开始生成'
        },
        (event) => {
          this.markStageStart(event)
        },
        (event) => {
          this.markStageProgress(event)
        },
        (event) => {
          this.markStageComplete(event)
        },
        (event) => {
          this.progress = 95
          this.progressText = '正在生成下载链接...'
          this.downloadPath = event.download_url
          this.resultMessage = `下载链接: ${event.download_url}`
        },
        () => {
          this.progress = 100
          this.progressText = '生成完成'
          this.running = false
          this.abortController = null
          this.refreshHistory()
        },
        (error) => {
          this.errorMessage = error
          this.progressText = error === '任务已取消' ? '任务已取消' : `错误: ${error}`
          if (error !== '任务已取消') this.markRunningStageFailed()
          this.running = false
          this.abortController = null
          this.refreshHistory()
        },
        this.abortController.signal
      )
    },
    async retryLastGenerate() {
      if (!this.lastPayload || this.running) return
      await this.startGenerate(this.lastPayload)
    },
    async stopCurrent() {
      this.abortController?.abort()
      if (this.sessionId) {
        await cancelGenerate(this.sessionId)
      }
      this.running = false
      this.progressText = '任务已取消'
      this.errorMessage = ''
      this.abortController = null
    },
    async removeHistory(sessionId: string) {
      await deleteHistory(sessionId)
      await this.refreshHistory()
    },
    fileUrl(sessionId: string, format: 'csv' | 'json' | 'parquet' = 'csv') {
      return downloadUrl(sessionId, format)
    },
    traceUrl(sessionId: string) {
      return langsmithTraceUrl(sessionId)
    },
    reportUrl(sessionId: string) {
      return reportUrl(sessionId)
    },
    // ---- batch actions ----
    async startBatchGenerate(tasks: BatchTaskItem[]) {
      this.batchRunning = true
      this.batchTasks = tasks.map((t, i) => ({
        index: i,
        industry: t.industry,
        stage: t.stage,
        count: t.count,
        session_id: '',
        status: 'pending',
        progress: 0,
        error_message: null,
      }))
      const result = await startBatch(tasks)
      this.batchId = result.batch_id
      this._pollBatch()
    },
    async _pollBatch() {
      if (!this.batchId || !this.batchRunning) return
      try {
        const status = await getBatchStatus(this.batchId)
        this.batchTasks = status.tasks
        if (status.finished) {
          this.batchRunning = false
          await this.refreshHistory()
        } else {
          setTimeout(() => this._pollBatch(), 2000)
        }
      } catch {
        this.batchRunning = false
      }
    },
    resetBatch() {
      this.batchId = ''
      this.batchTasks = []
      this.batchRunning = false
    },
  },
})
