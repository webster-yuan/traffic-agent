<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useTrafficStore } from '../stores/trafficStore'
import type { Stage } from '../api/trafficApi'

const store = useTrafficStore()
const industry = ref('ride_hailing')
const stage = ref<Stage>('standard')
const count = ref(100)
const rejectHint = ref('')

onMounted(() => {
  store.loadModelInfo()
})

const totalTokenUsage = computed(() => {
  const usages = store.tokenUsages
  if (usages.length === 0) return null
  return {
    calls: usages.length,
    prompt_tokens: usages.reduce((s, u) => s + u.prompt_tokens, 0),
    completion_tokens: usages.reduce((s, u) => s + u.completion_tokens, 0),
    total_tokens: usages.reduce((s, u) => s + u.total_tokens, 0),
    total_duration_ms: usages.reduce((s, u) => s + u.duration_ms, 0),
    avg_tokens_per_second: usages.length > 0
      ? Math.round(usages.reduce((s, u) => s + u.tokens_per_second, 0) / usages.length)
      : 0,
  }
})

function formatTokenCount(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(n)
}

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
    <h1>
      Traffic Agent 控制台
      <span v-if="store.modelInfo" class="model-badge" :title="`Provider: ${store.modelInfo.provider} | Context: ${store.modelInfo.context_window} tokens`">
        🤖 {{ store.modelInfo.model_name }}
      </span>
    </h1>
    <p class="desc">主Agent协调前后端：当前运行单并发、最多重试3次并返回最新结果。</p>

    <div class="form-grid">
      <label>
        行业
        <select v-model="industry">
          <option v-for="item in store.industries" :key="item.key" :value="item.key">
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

    <!-- P2.2 Human-in-the-Loop: Approval Panel -->
    <div v-if="store.approvalData && store.approvalWaiting" class="approval-card">
      <div class="approval-header">
        <span>👤 人工审核</span>
        <span class="approval-badge">等待中</span>
      </div>
      <div class="approval-summary">
        <div class="approval-stat">
          <strong>{{ store.approvalData.record_count }}</strong>
          <span>总记录</span>
        </div>
        <div class="approval-stat">
          <strong>{{ store.approvalData.real_count }}</strong>
          <span>真实流量</span>
        </div>
        <div class="approval-stat">
          <strong>{{ store.approvalData.fake_count }}</strong>
          <span>脚本流量</span>
        </div>
        <div class="approval-stat">
          <strong>{{ store.approvalData.anomaly_count }}</strong>
          <span>异常流量</span>
        </div>
        <div class="approval-stat">
          <strong>{{ store.approvalData.quality_score.toFixed(1) }}</strong>
          <span>质量分数</span>
        </div>
      </div>
      <div v-if="store.approvalData.sample_records.length" class="approval-samples">
        <div class="sample-title">样例记录 (前 {{ store.approvalData.sample_records.length }} 条)</div>
        <div
          v-for="(rec, idx) in store.approvalData.sample_records"
          :key="idx"
          class="sample-row"
        >
          <code>{{ rec.method }} {{ rec.status_code }}</code>
          <span class="sample-url">{{ rec.url }}</span>
          <span class="sample-label" :class="rec.identity_label">{{ rec.identity_label }}</span>
        </div>
      </div>
      <div class="approval-actions">
        <label class="reject-hint-label">
          驳回原因（可选）
          <input
            v-model="rejectHint"
            type="text"
            placeholder="例如：业务类型不匹配、数据格式有误..."
            class="reject-hint-input"
          />
        </label>
        <div class="approval-buttons">
          <button class="approve-btn" @click="store.approveGeneration()">
            ✅ 通过
          </button>
          <button
            class="reject-btn"
            @click="store.rejectGeneration(rejectHint); rejectHint = ''"
          >
            ❌ 驳回（重新生成）
          </button>
        </div>
      </div>
      <div v-if="store.approvalError" class="approval-error">
        {{ store.approvalError }}
      </div>
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

    <!-- P3.2 Agent Thought Process -->
    <div v-if="store.thoughts.length > 0" class="thought-log">
      <div class="thought-header">Agent 思考过程</div>
      <div class="thought-list" ref="thoughtListRef">
        <div
          v-for="t in store.thoughts"
          :key="t.id"
          class="thought-line"
        >{{ t.text }}</div>
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

    <!-- Token Usage Stats -->
    <div v-if="totalTokenUsage && !store.running" class="token-stats">
      <div class="token-header">📊 Token 消耗统计</div>
      <div class="token-grid">
        <div class="token-item">
          <strong>{{ totalTokenUsage.calls }}</strong>
          <span>LLM 调用</span>
        </div>
        <div class="token-item">
          <strong>{{ formatTokenCount(totalTokenUsage.prompt_tokens) }}</strong>
          <span>输入 Tokens</span>
        </div>
        <div class="token-item">
          <strong>{{ formatTokenCount(totalTokenUsage.completion_tokens) }}</strong>
          <span>输出 Tokens</span>
        </div>
        <div class="token-item">
          <strong>{{ formatTokenCount(totalTokenUsage.total_tokens) }}</strong>
          <span>总计 Tokens</span>
        </div>
        <div class="token-item">
          <strong>{{ (totalTokenUsage.total_duration_ms / 1000).toFixed(1) }}s</strong>
          <span>LLM 总耗时</span>
        </div>
        <div class="token-item">
          <strong>{{ totalTokenUsage.avg_tokens_per_second }} t/s</strong>
          <span>生成速度</span>
        </div>
      </div>
    </div>
  </section>
</template>
