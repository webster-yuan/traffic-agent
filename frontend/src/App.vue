<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useTrafficStore } from './stores/trafficStore'
import type { Stage } from './api/trafficApi'

const store = useTrafficStore()
const industry = ref('ride_hailing')
const stage = ref<Stage>('standard')
const count = ref(100)

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
            <td>{{ item.record_count }}</td>
            <td>{{ item.quality_score ?? '-' }}</td>
            <td class="row-actions">
              <a :href="store.fileUrl(item.session_id)" target="_blank" rel="noreferrer">下载</a>
              <button class="danger ghost" @click="store.removeHistory(item.session_id)">删除</button>
            </td>
          </tr>
          <tr v-if="store.history.length === 0">
            <td colspan="6">暂无记录</td>
          </tr>
        </tbody>
      </table>
    </section>
  </main>
</template>
