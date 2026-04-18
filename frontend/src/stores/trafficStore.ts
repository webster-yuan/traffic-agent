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

export const useTrafficStore = defineStore('traffic', {
  state: () => ({
    running: false,
    sessionId: '',
    progressText: '等待开始',
    progress: 0,
    resultMessage: '',
    history: [] as HistoryItem[],
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

      generateTrafficStream(
        payload,
        (sessionId) => {
          this.sessionId = sessionId
          this.progress = 10
          this.progressText = '已连接，开始生成'
        },
        (event) => {
          const stageMap: Record<string, string> = {
            rag: 'RAG检索',
            generate: '流量生成',
            eval: '质量评估',
            identity: '身份校验',
          }
          this.progressText = `正在${stageMap[event.stage] || event.stage}...`
        },
        (event) => {
          this.progress = 90
          this.progressText = '阶段完成'
        },
        (event) => {
          this.progress = 95
          this.progressText = '正在生成下载链接...'
          this.resultMessage = `下载链接: /api/v1/traffic/download/${this.sessionId}`
        },
        () => {
          this.progress = 100
          this.progressText = '生成完成'
          this.running = false
          this.refreshHistory()
        },
        (error) => {
          this.progressText = `错误: ${error}`
          this.running = false
        }
      )
    },
    async stopCurrent() {
      if (!this.sessionId) return
      await cancelGenerate(this.sessionId)
      this.running = false
      this.progressText = '任务已取消'
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
