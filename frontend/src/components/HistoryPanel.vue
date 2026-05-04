<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useTrafficStore } from '../stores/trafficStore'
import { statusOptions } from '../constants'
import { replayTraffic, type ReplayFromNode } from '../api/trafficApi'

const store = useTrafficStore()
const selectedSessionId = ref('')

// Replay state
const replayOpen = ref(false)
const replayFromNode = ref<ReplayFromNode>('generate')
const replayHint = ref('')
const replayLoading = ref(false)
const replayError = ref('')
const replaySuccess = ref('')

const selectedTask = computed(() =>
  store.history.find((item) => item.session_id === selectedSessionId.value) || null
)

function selectTask(sessionId: string) {
  if (selectedSessionId.value === sessionId) {
    selectedSessionId.value = ''
    replayOpen.value = false
    replayError.value = ''
    replaySuccess.value = ''
  } else {
    selectedSessionId.value = sessionId
    replayOpen.value = false
    replayError.value = ''
    replaySuccess.value = ''
  }
}

function toggleReplay() {
  replayOpen.value = !replayOpen.value
  replayError.value = ''
  replaySuccess.value = ''
  replayFromNode.value = 'generate'
  replayHint.value = ''
}

async function doReplay() {
  if (!selectedTask.value) return
  replayLoading.value = true
  replayError.value = ''
  replaySuccess.value = ''
  try {
    const result = await replayTraffic({
      session_id: selectedTask.value.session_id,
      from_node: replayFromNode.value,
      hint_override: replayHint.value || undefined,
    })
    replaySuccess.value = `重放完成！新 Session: ${result.session_id}，共 ${result.total_count} 条记录`
    replayOpen.value = false
    await store.refreshHistory()
  } catch (e: unknown) {
    replayError.value = e instanceof Error ? e.message : String(e)
  } finally {
    replayLoading.value = false
  }
}

function onFilterChange() {
  store.refreshHistory(1)
}

onMounted(async () => {
  await store.refreshHistory()
})
</script>

<template>
  <section class="panel">
    <h2>历史记录</h2>
    <div class="history-filter">
      <label>
        关键字
        <input v-model="store.historyFilters.keyword" type="search" placeholder="Session / 场景 / 错误" @change="onFilterChange" />
      </label>
      <label>
        行业
        <select v-model="store.historyFilters.industry" @change="onFilterChange">
          <option value="">全部行业</option>
          <option v-for="item in store.industries" :key="item.key" :value="item.key">
            {{ item.label }}
          </option>
        </select>
      </label>
      <label>
        阶段
        <select v-model="store.historyFilters.stage" @change="onFilterChange">
          <option value="">全部阶段</option>
          <option value="quick">快速</option>
          <option value="standard">标准</option>
          <option value="full">完整</option>
        </select>
      </label>
      <label>
        状态
        <select v-model="store.historyFilters.status" @change="onFilterChange">
          <option value="">全部状态</option>
          <option v-for="item in statusOptions" :key="item.value" :value="item.value">
            {{ item.label }}
          </option>
        </select>
      </label>
      <label>
        开始日期
        <input v-model="store.historyFilters.dateFrom" type="date" @change="onFilterChange" />
      </label>
      <label>
        结束日期
        <input v-model="store.historyFilters.dateTo" type="date" @change="onFilterChange" />
      </label>
      <label>
        最低评分
        <input v-model="store.historyFilters.minQuality" type="number" min="0" max="100" placeholder="如 80" @change="onFilterChange" />
      </label>
      <button class="ghost neutral" @click="store.resetHistoryFilters">重置筛选</button>
    </div>
    <p class="meta">共 {{ store.historyTotal }} 条 · 第 {{ store.historyPage }} / {{ store.historyTotalPages }} 页</p>
    <div v-if="store.historyTotalPages > 1" class="pagination">
      <button :disabled="store.historyPage <= 1" @click="store.goHistoryPage(store.historyPage - 1)">
        ← 上一页
      </button>
      <span class="page-info">第 {{ store.historyPage }} 页 / 共 {{ store.historyTotalPages }} 页</span>
      <button :disabled="store.historyPage >= store.historyTotalPages" @click="store.goHistoryPage(store.historyPage + 1)">
        下一页 →
      </button>
    </div>
    <div class="history-table-wrap">
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
            <a :href="store.fileUrl(item.session_id, 'csv')" target="_blank" rel="noreferrer">CSV</a>
            <span class="download-sep">|</span>
            <a :href="store.fileUrl(item.session_id, 'json')" target="_blank" rel="noreferrer">JSON</a>
            <span class="download-sep">|</span>
            <a :href="store.fileUrl(item.session_id, 'parquet')" target="_blank" rel="noreferrer">Parquet</a>
            <button class="danger ghost" @click="store.removeHistory(item.session_id)">删除</button>
          </td>
        </tr>
        <tr v-if="store.history.length === 0">
          <td colspan="7">暂无匹配记录</td>
        </tr>
      </tbody>
    </table>
    </div>

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
      <p class="result" v-if="selectedTask.status === 'completed'">
        <button class="ghost" @click="toggleReplay">🔄 重放此任务</button>
      </p>
      <div v-if="replayOpen" class="replay-panel">
        <label>
          从节点重放：
          <select v-model="replayFromNode">
            <option value="rag">RAG检索后（重新生成）</option>
            <option value="generate">生成后（重新评估）</option>
            <option value="eval">评估后（重新身份校验）</option>
          </select>
        </label>
        <label>
          自定义提示（可选）：
          <input v-model="replayHint" type="text" placeholder="如：请多生成POST请求" />
        </label>
        <div class="replay-actions">
          <button :disabled="replayLoading" @click="doReplay">
            {{ replayLoading ? '执行中...' : '执行重放' }}
          </button>
          <button class="ghost neutral" @click="replayOpen = false">取消</button>
        </div>
        <p v-if="replayError" class="replay-error">{{ replayError }}</p>
        <p v-if="replaySuccess" class="replay-success">{{ replaySuccess }}</p>
      </div>
    </div>
  </section>
</template>
