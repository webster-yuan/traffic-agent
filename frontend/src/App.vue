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
  { value: 'custom', label: '自定义' },
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

function selectTask(sessionId: string) {
  selectedSessionId.value = selectedSessionId.value === sessionId ? '' : sessionId
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
      <p v-if="store.downloadPath" class="result">
        下载链接：
        <a :href="store.fileUrl(store.sessionId)" target="_blank" rel="noreferrer">
          {{ store.downloadPath }}
        </a>
      </p>
      <p v-else class="result">{{ store.resultMessage }}</p>
    </section>

    <section class="panel">
      <h2>历史记录</h2>
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
          <tr v-for="item in store.history" :key="item.session_id">
            <td>{{ item.session_id }}</td>
            <td>{{ item.industry }}</td>
            <td>{{ item.stage }}</td>
            <td>{{ item.status }}</td>
            <td>{{ item.record_count }}/{{ item.requested_count }}</td>
            <td>{{ item.quality_score ?? '-' }}</td>
            <td class="row-actions">
              <button class="ghost neutral" @click="selectTask(item.session_id)">详情</button>
              <a :href="store.fileUrl(item.session_id)" target="_blank" rel="noreferrer">下载</a>
              <button class="danger ghost" @click="store.removeHistory(item.session_id)">删除</button>
            </td>
          </tr>
          <tr v-if="store.history.length === 0">
            <td colspan="7">暂无记录</td>
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
      </div>
    </section>
  </main>
</template>
