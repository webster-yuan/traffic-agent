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
  resumeGeneration,
  startBatch,
  type ApprovalRequired,
  type BatchTaskItem,
  type BatchTaskStatus,
  type GeneratePayload,
  type HistoryFilters,
  type HistoryItem,
  type StageComplete,
  type StageProgress,
  type Thought,
  type ThoughtDecision,
  type GenerateProgress,
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

const STAGE_ORDER = ['rag', 'generate', 'eval', 'identity', 'approval']

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
    // P3.2 Agent thought process
    thoughts: [] as { id: number; text: string; ts: number }[],
    thoughtSeq: 0,
    // batch state
    batchId: '',
    batchTasks: [] as BatchTaskStatus[],
    batchRunning: false,
    // P2.2 Human-in-the-Loop: approval state
    approvalData: null as ApprovalRequired | null,
    approvalWaiting: false,
    approvalResult: null as string | null,
    approvalError: '',
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
      this.thoughts = []
      this.thoughtSeq = 0
      this.approvalData = null
      this.approvalWaiting = false
      this.approvalError = ''
      this.abortController?.abort()
      this.abortController = new AbortController()

      const addThought = (text: string) => {
        this.thoughtSeq++
        this.thoughts.push({ id: this.thoughtSeq, text, ts: Date.now() })
        // Keep at most 30 recent thoughts
        if (this.thoughts.length > 30) this.thoughts.shift()
      }

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
        (thought: Thought) => {
          addThought(`💭 ${thought.message}`)
        },
        (decision: ThoughtDecision) => {
          addThought(`🧠 ${decision.decision}`)
        },
        (_data: { node: string; content: string }) => {
          // thought_token: too chatty, skip for now
        },
        (progress: GenerateProgress) => {
          const icon = progress.phase === 'parse'
            ? `📊`
            : progress.phase === 'llm_call'
              ? '🤖'
              : progress.phase === 'llm_done'
                ? '✅'
                : '📝'
          addThought(`${icon} ${progress.message}`)
        },
        (approvalData: ApprovalRequired) => {
          // HITL: graph paused, waiting for human approval
          this.approvalData = approvalData
          this.approvalWaiting = true
          this.running = false
          this.progressText = '等待人工审核...'
          this.markStageStart({ stage: 'approval', name: '人工审核', progress: 95 })
          this.abortController = null
          addThought(`👤 等待人工审核 — ${approvalData.record_count} 条记录，质量分数 ${approvalData.quality_score}`)
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
      this.approvalWaiting = false
    },
    async approveGeneration() {
      if (!this.sessionId || !this.approvalWaiting) return
      this.approvalWaiting = false
      this.running = true
      this.approvalError = ''
      this.markStageComplete({ stage: 'approval', status: 'success', progress: 95 })
      try {
        const result = await resumeGeneration(this.sessionId, 'approve')
        if (result.success) {
          this.progress = 100
          this.progressText = '审核通过，生成完成'
          this.downloadPath = result.download_url ?? ''
          this.resultMessage = `下载链接: ${result.download_url}`
          this.running = false
          this.approvalData = null
          this.refreshHistory()
        } else if (result.status === 'pending_approval' && result.interrupt) {
          // Re-approval needed (re-generate → re-eval → re-approval)
          this.approvalData = result.interrupt
          this.approvalWaiting = true
          this.running = false
          this.progressText = '等待重新审核...'
          this.markStageStart({ stage: 'approval', name: '人工审核', progress: 95 })
          // Add thought about re-approval
          this.thoughtSeq++
          this.thoughts.push({
            id: this.thoughtSeq,
            text: `👤 重新生成完成，等待再次审核 — ${result.interrupt.record_count} 条记录`,
            ts: Date.now(),
          })
        } else {
          this.errorMessage = result.message ?? '审核失败'
          this.running = false
        }
      } catch (e: unknown) {
        this.approvalError = e instanceof Error ? e.message : String(e)
        this.running = false
      }
    },
    async rejectGeneration(hint: string) {
      if (!this.sessionId || !this.approvalWaiting) return
      this.approvalWaiting = false
      this.running = true
      this.approvalError = ''
      try {
        const result = await resumeGeneration(this.sessionId, 'reject', hint)
        if (result.success) {
          this.progress = 100
          this.progressText = '审核驳回，但生成完成'
          this.running = false
          this.approvalData = null
          this.refreshHistory()
        } else if (result.status === 'pending_approval' && result.interrupt) {
          // Re-approval needed
          this.approvalData = result.interrupt
          this.approvalWaiting = true
          this.running = false
          this.progressText = '等待重新审核...'
          this.markStageStart({ stage: 'approval', name: '人工审核', progress: 95 })
          this.thoughtSeq++
          this.thoughts.push({
            id: this.thoughtSeq,
            text: `👤 重新生成完成，等待再次审核 — ${result.interrupt.record_count} 条记录`,
            ts: Date.now(),
          })
        } else {
          this.errorMessage = result.message ?? '驳回失败'
          this.running = false
        }
      } catch (e: unknown) {
        this.approvalError = e instanceof Error ? e.message : String(e)
        this.running = false
      }
    },
    dismissApproval() {
      this.approvalData = null
      this.approvalWaiting = false
      this.approvalError = ''
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
