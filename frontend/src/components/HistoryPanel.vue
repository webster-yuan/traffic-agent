<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useTrafficStore } from '../stores/trafficStore'
import { industryOptions, statusOptions } from '../constants'

const store = useTrafficStore()
const selectedSessionId = ref('')

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
    <p class="meta">已显示 {{ store.filteredHistory.length }} / {{ store.history.length }} 条历史记录 · 第 {{ store.historyPage }} / {{ store.historyTotalPages }} 页</p>
    <div v-if="store.historyTotalPages > 1" class="pagination">
      <button :disabled="store.historyPage <= 1" @click="store.goHistoryPage(store.historyPage - 1)">
        ← 上一页
      </button>
      <span class="page-info">第 {{ store.historyPage }} 页 / 共 {{ store.historyTotalPages }} 页</span>
      <button :disabled="store.historyPage >= store.historyTotalPages" @click="store.goHistoryPage(store.historyPage + 1)">
        下一页 →
      </button>
    </div>
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
</template>
