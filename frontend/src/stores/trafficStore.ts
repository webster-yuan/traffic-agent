import { defineStore } from 'pinia'
import {
  cancelGenerate,
  deleteHistory,
  downloadUrl,
  generateTrafficStream,
  langsmithTraceUrl,
  listHistory,
  type GeneratePayload,
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

type HistoryFilters = {
  keyword: string
  industry: string
  stage: string
  status: string
  dateFrom: string
  dateTo: string
  minQuality: string
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

function dayStart(value: string) {
  return new Date(`${value}T00:00:00`).getTime()
}

function dayEnd(value: string) {
  return new Date(`${value}T23:59:59.999`).getTime()
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
    historyFilters: createHistoryFilters(),
    abortController: null as AbortController | null,
  }),
  getters: {
    filteredHistory(state) {
      const keyword = state.historyFilters.keyword.trim().toLowerCase()
      const minQuality = Number(state.historyFilters.minQuality)
      const hasMinQuality = state.historyFilters.minQuality !== '' && !Number.isNaN(minQuality)
      const fromTime = state.historyFilters.dateFrom ? dayStart(state.historyFilters.dateFrom) : null
      const toTime = state.historyFilters.dateTo ? dayEnd(state.historyFilters.dateTo) : null

      return state.history.filter((item) => {
        if (state.historyFilters.industry && item.industry !== state.historyFilters.industry) return false
        if (state.historyFilters.stage && item.stage !== state.historyFilters.stage) return false
        if (state.historyFilters.status && item.status !== state.historyFilters.status) return false
        if (hasMinQuality && (item.quality_score === null || item.quality_score < minQuality)) return false

        const itemTime = new Date(item.updated_at || item.created_at).getTime()
        if (fromTime !== null && itemTime < fromTime) return false
        if (toTime !== null && itemTime > toTime) return false

        if (keyword) {
          const haystack = [
            item.session_id,
            item.industry,
            item.scenario,
            item.stage,
            item.status,
            item.error_message || '',
          ].join(' ').toLowerCase()
          if (!haystack.includes(keyword)) return false
        }

        return true
      })
    },
  },
  actions: {
    inferScenario(industry: string) {
      return INDUSTRY_SCENARIO[industry] || '自定义场景'
    },
    async refreshHistory() {
      const data = await listHistory(1, 20)
      this.history = data.items
    },
    resetStageSteps() {
      this.stageSteps = createStageSteps()
    },
    resetHistoryFilters() {
      this.historyFilters = createHistoryFilters()
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
  },
})
