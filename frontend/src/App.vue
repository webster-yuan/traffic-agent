<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useTrafficStore } from './stores/trafficStore'
import type { Stage } from './api/trafficApi'

const store = useTrafficStore()
const industry = ref('ride_hailing')
const stage = ref<Stage>('standard')
const count = ref(100)
const selectedSessionId = ref('')

const industryOptions = [
  { value: 'government', label: '政府机关' },
  { value: 'ecommerce', label: '电商物流' },
  { value: 'short_video', label: '短视频' },
  { value: 'ride_hailing', label: '网约车' },
  { value: 'logistics', label: '货运物流' },
  { value: 'delivery', label: '即时配送' },
  { value: 'finance', label: '金融交易' },
  { value: 'healthcare', label: '医疗系统' },
  { value: 'media', label: '流媒体' },
  { value: 'social', label: '社交媒体' },
  { value: 'gaming', label: '游戏服务' },
  { value: 'custom', label: '自定义' },
]

const statusOptions = [
  { value: 'processing', label: '处理中' },
  { value: 'completed', label: '已完成' },
  { value: 'failed', label: '失败' },
  { value: 'cancelled', label: '已取消' },
]

async function onSubmit() {
  await store.startGenerate({
    industry: industry.value,
    count: count.value,
    stage: stage.value,
  })
}

const selectedTask = computed(() =>
  store.history.find((item) => item.session_id === selectedSessionId.value) || null
)

// batch state
const batchItems = ref<Array<{ industry: string; count: number; stage: Stage }>>([])
const batchIndustry = ref('ride_hailing')
const batchStage = ref<Stage>('quick')
const batchCount = ref(2)

function addBatchItem() {
  if (batchItems.value.length >= 10) return
  batchItems.value.push({
    industry: batchIndustry.value,
    count: batchCount.value,
    stage: batchStage.value,
  })
}

function removeBatchItem(index: number) {
  batchItems.value.splice(index, 1)
}

async function startBatch() {
  if (batchItems.value.length === 0) return
  await store.startBatchGenerate([...batchItems.value])
}

function batchStatusClass(status: string) {
  if (status === 'completed') return 'completed'
  if (status === 'processing') return 'processing'
  if (status === 'failed') return 'failed'
  return 'pending'
}

function batchStatusText(status: string) {
  if (status === 'completed') return '已完成'
  if (status === 'processing') return '处理中'
  if (status === 'failed') return '失败'
  if (status === 'cancelled') return '已取消'
  return '等待中'
}

function selectTask(sessionId: string) {
  selectedSessionId.value = selectedSessionId.value === sessionId ? '' : sessionId
}

function formatDuration(ms?: number) {
  if (ms === undefined) return '-'
  if (ms < 1000) return `${ms} ms`
  return `${(ms / 1000).toFixed(1)} s`
}

function stageStatusText(status: string) {
  if (status === 'completed') return '已完成'
  if (status === 'running') return '进行中'
  if (status === 'failed') return '失败'
  return '等待中'
}

onMounted(async () => {
  await store.refreshHistory()
})
</script>

<template>
  <main class="container">
    <section class="panel">
      <h1>Traffic Agent 控制台</h1>
      <p class="desc">主Agent协调前后端：当前运行单并发、最多重试3次并返回最新结果。</p>

      <div class="form-grid">
        <label>
          行业
          <select v-model="industry">
            <option v-for="item in industryOptions" :key="item.value" :value="item.value">
              {{ item.label }}
            </option>
          </select>
        </label>
        <label>
          阶段
          <select v-model="stage">
            <option value="quick">快速</option>
            <option value="standard">标准</option>
            <option value="full">完整</option>
          </select>
        </label>
        <label>
          数量
          <input v-model.number="count" type="number" min="1" max="10000" />
        </label>
      </div>
      <p>场景自动推断：{{ store.inferScenario(industry) }}</p>

      <div class="actions">
        <button :disabled="store.running" @click="onSubmit">开始生成</button>
        <button :disabled="!store.running" class="danger" @click="store.stopCurrent">取消任务</button>
      </div>

      <div class="progress">
        <div class="bar" :style="{ width: `${store.progress}%` }"></div>
      </div>
      <p v-if="store.sessionId" class="meta">Session ID：{{ store.sessionId }}</p>
      <p>{{ store.progressText }}</p>
      <div v-if="store.errorMessage" class="error-card">
        <strong>生成失败</strong>
        <p>{{ store.errorMessage }}</p>
        <button :disabled="store.running" class="ghost neutral" @click="store.retryLastGenerate">
          重试上次请求
        </button>
      </div>
      <div class="stage-timeline">
        <div
          v-for="step in store.stageSteps"
          :key="step.stage"
          class="stage-step"
          :class="step.status"
        >
          <div class="stage-dot"></div>
          <div class="stage-copy">
            <strong>{{ step.name }}</strong>
            <span>{{ stageStatusText(step.status) }}</span>
            <small>
              进度 {{ step.progress }}%
              <template v-if="step.elapsedMs !== undefined"> · 耗时 {{ formatDuration(step.elapsedMs) }}</template>
              <template v-if="step.retry"> · 重试 {{ step.retry }} 次</template>
            </small>
          </div>
        </div>
      </div>
      <p v-if="store.downloadPath" class="result download-links">
        下载：
        <a :href="store.fileUrl(store.sessionId, 'csv')" target="_blank" rel="noreferrer">CSV</a>
        <span class="download-sep">|</span>
        <a :href="store.fileUrl(store.sessionId, 'json')" target="_blank" rel="noreferrer">JSON</a>
        <span class="download-sep">|</span>
        <a :href="store.fileUrl(store.sessionId, 'parquet')" target="_blank" rel="noreferrer">Parquet</a>
        <span class="meta-inline">{{ store.downloadPath }}</span>
      </p>
      <p v-else class="result">{{ store.resultMessage }}</p>
    </section>

    <section class="panel">
      <h2>批量生成</h2>
      <p class="desc">添加多个任务，一次性批量生成。任务按顺序执行，每2秒刷新状态。</p>

      <div class="batch-form">
        <div class="form-grid">
          <label>
            行业
            <select v-model="batchIndustry">
              <option v-for="item in industryOptions" :key="item.value" :value="item.value">
                {{ item.label }}
              </option>
            </select>
          </label>
          <label>
            阶段
            <select v-model="batchStage">
              <option value="quick">快速</option>
              <option value="standard">标准</option>
              <option value="full">完整</option>
            </select>
          </label>
          <label>
            数量
            <input v-model.number="batchCount" type="number" min="1" max="10000" />
          </label>
        </div>
        <button class="ghost neutral" :disabled="batchItems.length >= 10" @click="addBatchItem">
          添加任务 ({{ batchItems.length }}/10)
        </button>
      </div>

      <ul v-if="batchItems.length > 0" class="batch-list">
        <li v-for="(item, idx) in batchItems" :key="idx" class="batch-item">
          <span>{{ item.industry }} · {{ item.stage }} · {{ item.count }} 条</span>
          <button class="ghost danger" :disabled="store.batchRunning || store.running" @click="removeBatchItem(idx)">移除</button>
        </li>
      </ul>

      <div class="actions" v-if="batchItems.length > 0 && !store.batchRunning">
        <button :disabled="store.running" @click="startBatch">开始批量生成</button>
        <button class="ghost neutral" @click="batchItems = []">清空列表</button>
      </div>

      <div v-if="store.batchRunning || store.batchTasks.length > 0" class="batch-progress">
        <h3>批次 {{ store.batchId }}</h3>
        <div v-for="task in store.batchTasks" :key="task.index" class="batch-task-row" :class="batchStatusClass(task.status)">
          <span class="batch-task-index">#{{ task.index + 1 }}</span>
          <span class="batch-task-info">{{ task.industry }} · {{ task.stage }} · {{ task.count }} 条</span>
          <span class="batch-task-status">{{ batchStatusText(task.status) }}</span>
          <div class="batch-task-bar"><div class="batch-task-fill" :style="{ width: `${task.progress}%` }"></div></div>
          <span v-if="task.session_id" class="batch-task-sid">{{ task.session_id }}</span>
          <span v-if="task.error_message" class="batch-task-error">{{ task.error_message }}</span>
        </div>
        <button v-if="!store.batchRunning && store.batchTasks.length > 0" class="ghost neutral" @click="store.resetBatch()">关闭</button>
      </div>
    </section>

    <section class="panel">
      <h2>历史记录</h2>
      <div class="history-filter">
        <label>
          关键字
          <input v-model="store.historyFilters.keyword" type="search" placeholder="Session / 场景 / 错误" />
        </label>
        <label>
          行业
          <select v-model="store.historyFilters.industry">
            <option value="">全部行业</option>
            <option v-for="item in industryOptions" :key="item.value" :value="item.value">
              {{ item.label }}
            </option>
          </select>
        </label>
        <label>
          阶段
          <select v-model="store.historyFilters.stage">
            <option value="">全部阶段</option>
            <option value="quick">快速</option>
            <option value="standard">标准</option>
            <option value="full">完整</option>
          </select>
        </label>
        <label>
          状态
          <select v-model="store.historyFilters.status">
            <option value="">全部状态</option>
            <option v-for="item in statusOptions" :key="item.value" :value="item.value">
              {{ item.label }}
            </option>
          </select>
        </label>
        <label>
          开始日期
          <input v-model="store.historyFilters.dateFrom" type="date" />
        </label>
        <label>
          结束日期
          <input v-model="store.historyFilters.dateTo" type="date" />
        </label>
        <label>
          最低评分
          <input v-model="store.historyFilters.minQuality" type="number" min="0" max="100" placeholder="如 80" />
        </label>
        <button class="ghost neutral" @click="store.resetHistoryFilters">重置筛选</button>
      </div>
      <p class="meta">已显示 {{ store.filteredHistory.length }} / {{ store.history.length }} 条历史记录</p>
      <table>
        <thead>
          <tr>
            <th>Session</th>
            <th>行业</th>
            <th>阶段</th>
            <th>状态</th>
            <th>数量</th>
            <th>评分</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in store.filteredHistory" :key="item.session_id">
            <td>{{ item.session_id }}</td>
            <td>{{ item.industry }}</td>
            <td>{{ item.stage }}</td>
            <td>{{ item.status }}</td>
            <td>{{ item.record_count }}/{{ item.requested_count }}</td>
            <td>{{ item.quality_score ?? '-' }}</td>
            <td class="row-actions">
              <button class="ghost neutral" @click="selectTask(item.session_id)">详情</button>
              <a :href="store.fileUrl(item.session_id, 'csv')" target="_blank" rel="noreferrer">CSV</a>
              <span class="download-sep">|</span>
              <a :href="store.fileUrl(item.session_id, 'json')" target="_blank" rel="noreferrer">JSON</a>
              <span class="download-sep">|</span>
              <a :href="store.fileUrl(item.session_id, 'parquet')" target="_blank" rel="noreferrer">Parquet</a>
              <button class="danger ghost" @click="store.removeHistory(item.session_id)">删除</button>
            </td>
          </tr>
          <tr v-if="store.filteredHistory.length === 0">
            <td colspan="7">暂无匹配记录</td>
          </tr>
        </tbody>
      </table>

      <div v-if="selectedTask" class="detail-card">
        <h3>任务详情</h3>
        <dl>
          <dt>Session ID</dt>
          <dd>{{ selectedTask.session_id }}</dd>
          <dt>状态</dt>
          <dd>{{ selectedTask.status }}</dd>
          <dt>Trace Thread</dt>
          <dd>{{ selectedTask.trace_thread_id || '-' }}</dd>
          <dt>请求/生成数量</dt>
          <dd>{{ selectedTask.requested_count }} / {{ selectedTask.record_count }}</dd>
          <dt>开始时间</dt>
          <dd>{{ selectedTask.started_at || '-' }}</dd>
          <dt>完成时间</dt>
          <dd>{{ selectedTask.completed_at || '-' }}</dd>
          <dt>错误信息</dt>
          <dd>{{ selectedTask.error_message || '-' }}</dd>
        </dl>
        <div v-if="selectedTask.quality_detail" class="quality-detail">
          <h4>质量评估（与 JSON <code>metadata.quality</code> 一致）</h4>
          <p class="meta">
            综合 {{ selectedTask.quality_detail.total_score }} 分 · 格式
            {{ selectedTask.quality_detail.format_score }} · 业务 {{ selectedTask.quality_detail.business_score }} · 多样性
            {{ selectedTask.quality_detail.diversity_score }}
            · {{ selectedTask.quality_detail.passed ? '通过' : '未通过' }}（阈值 ≥70）
          </p>
          <div class="quality-col">
            <strong>格式维度</strong>
            <ul>
              <li v-for="(n, i) in selectedTask.quality_detail.format_notes" :key="'f' + i">{{ n }}</li>
            </ul>
          </div>
          <div class="quality-col">
            <strong>业务维度</strong>
            <ul>
              <li v-for="(n, i) in selectedTask.quality_detail.business_notes" :key="'b' + i">{{ n }}</li>
            </ul>
          </div>
          <div class="quality-col">
            <strong>多样性维度</strong>
            <ul>
              <li v-for="(n, i) in selectedTask.quality_detail.diversity_notes" :key="'d' + i">{{ n }}</li>
            </ul>
          </div>
        </div>
        <p class="meta">
          LangSmith 查询条件：
          <code>metadata.session_id:{{ selectedTask.session_id }}</code>
        </p>
        <p v-if="store.traceUrl(selectedTask.session_id)" class="result">
          <a :href="store.traceUrl(selectedTask.session_id)" target="_blank" rel="noreferrer">
            打开 LangSmith Trace
          </a>
        </p>
        <p v-else class="meta">
          如需一键跳转，请配置前端环境变量 VITE_LANGSMITH_PROJECT_URL。
        </p>
        <p class="result">
          <a :href="store.reportUrl(selectedTask.session_id)" target="_blank" rel="noreferrer">
            📊 导出 HTML 报告
          </a>
        </p>
      </div>
    </section>
  </main>
</template>
