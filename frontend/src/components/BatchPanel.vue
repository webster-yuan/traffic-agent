<script setup lang="ts">
import { ref, computed } from 'vue'
import { useTrafficStore } from '../stores/trafficStore'
import type { Stage } from '../api/trafficApi'

const store = useTrafficStore()
const batchItems = ref<Array<{ industry: string; count: number; stage: Stage }>>([])
const batchIndustry = ref('ride_hailing')
const batchStage = ref<Stage>('quick')
const batchCount = ref(2)

const hasFailedTasks = computed(() =>
  store.batchTasks.some((t) => t.status === 'failed')
)

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
</script>

<template>
  <section class="panel">
    <h2>批量生成</h2>
    <p class="desc">添加多个任务，一次性批量生成。任务按顺序执行，每2秒刷新状态。</p>

    <div class="batch-form">
      <div class="form-grid">
        <label>
          行业
          <select v-model="batchIndustry">
            <option v-for="item in store.industries" :key="item.key" :value="item.key">
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
      <button
        v-if="hasFailedTasks && !store.batchRunning"
        class="retry-btn"
        @click="store.retryFailedBatchTasks()"
      >
        🔄 重试失败任务
      </button>
    </div>
  </section>
</template>
