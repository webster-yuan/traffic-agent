<script setup lang="ts">
import { ref } from 'vue'
import { useTrafficStore } from '../stores/trafficStore'
import type { Stage } from '../api/trafficApi'
import { industryOptions } from '../constants'

const store = useTrafficStore()
const industry = ref('ride_hailing')
const stage = ref<Stage>('standard')
const count = ref(100)

async function onSubmit() {
  await store.startGenerate({
    industry: industry.value,
    count: count.value,
    stage: stage.value,
  })
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
</script>

<template>
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
</template>
