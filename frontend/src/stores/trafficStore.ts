import { defineStore } from 'pinia'
import {
  cancelGenerate,
  deleteHistory,
  downloadUrl,
  generateTrafficStream,
  listHistory,
  type GeneratePayload,
  type HistoryItem,
} from '../api/trafficApi'

const INDUSTRY_SCENARIO: Record<string, string> = {
  government: '工作日办公时间',
  ecommerce: '全天候配送',
  short_video: '内容创作时段',
  ride_hailing: '通勤高峰',
  logistics: '夜间运输',
  delivery: '饭点高峰',
  custom: '自定义场景',
}

const STAGE_NAME: Record<string, string> = {
  rag: 'RAG检索',
  generate: '流量生成',
  eval: '质量评估',
  identity: '身份校验',
}

export const useTrafficStore = defineStore('traffic', {
  state: () => ({
    running: false,
    sessionId: '',
    progressText: '等待开始',
    progress: 0,
    resultMessage: '',
    downloadPath: '',
    history: [] as HistoryItem[],
    abortController: null as AbortController | null,
  }),
  actions: {
    inferScenario(industry: string) {
      return INDUSTRY_SCENARIO[industry] || '自定义场景'
    },
    async refreshHistory() {
      const data = await listHistory(1, 20)
      this.history = data.items
    },
    async startGenerate(payload: GeneratePayload) {
      this.running = true
      this.progress = 0
      this.progressText = '正在连接...'
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
          this.progressText = `正在${STAGE_NAME[event.stage] || event.stage}...`
        },
        (event) => {
          this.progress = 90
          this.progressText = `${STAGE_NAME[event.stage] || event.stage}完成`
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
          this.progressText = `错误: ${error}`
          this.running = false
          this.abortController = null
        },
        this.abortController.signal
      )
    },
    async stopCurrent() {
      this.abortController?.abort()
      if (this.sessionId) {
        await cancelGenerate(this.sessionId)
      }
      this.running = false
      this.progressText = '任务已取消'
      this.abortController = null
    },
    async removeHistory(sessionId: string) {
      await deleteHistory(sessionId)
      await this.refreshHistory()
    },
    fileUrl(sessionId: string) {
      return downloadUrl(sessionId)
    },
  },
})
