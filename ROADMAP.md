# Traffic Agent 待办事项与路线图

**更新日期**: 2026-04-26
**重点**: 质量详情与 Parquet 导出已就绪；下一优先项为 报表/批量生成/响应式 中按产品排序择一

---

## 当前项目状态

### 已完成

- LangSmith 追踪已接入前端业务生成链路，通过 `session_id` / `thread_id` 可定位单次请求。
- `generate_node` 已在 LangSmith 输出轻量业务摘要，包含生成数量、身份分布、样例记录等调试信息。
- 前端已展示 `Session ID`、LangSmith 查询条件和一键跳转入口。
- 生成链路已支持阶段时间线，展示 RAG、流量生成、质量评估、身份校验的状态、进度和耗时。
- 流式生成错误处理已增强，支持 SSE `error`、非 2xx、断流未完成、取消等场景，并提供“重试上次请求”入口。
- 历史记录已支持本地高级筛选：关键字、行业、阶段、状态、日期范围、最低评分。
- 已扩展金融、医疗、流媒体、社交媒体、游戏服务 5 个行业场景，并将行业特征接入 LLM 提示词。
- 质量评估已从随机评分升级为基于生成记录的格式、业务匹配和多样性评分；`QualityScore` 含各维度 **扣分说明列表**，`complete_session` 将完整 `quality` 以 JSON 写入 `quality_detail`，历史任务详情与导出的 **JSON** `metadata.quality` 一致。
- 数据导出已扩展：与 CSV 同目录写入 `metadata + records` 结构的 **JSON** 与表格式 **Parquet**（`write_traffic_parquet`）；下载支持 `?format=json` 与 `?format=parquet`（`application/vnd.apache.parquet`）；前端提供 **CSV | JSON | Parquet** 分链接。
- 已在 **Chrome 远程调试（9222）+ DevTools MCP** 下按 Skill 跑通 `quick + 2` 全链路：结果区与历史表多格式下载、`generate/stream` 与 `history` 200、控制台无 error 级问题（后续迭代在 UI 出现 Parquet 后复验一次含 Parquet 链接）。
- 已沉淀项目 Cursor Rule 和 `traffic-agent-iteration-validation` Skill，用于后续迭代的测试、全链路验证和提交前路线图同步。
- 已使用 Chrome DevTools MCP 多次完成 `quick + 2 条` 的本地全链路验证。

### 当前技术状态

- 后端：FastAPI + LangGraph + SQLite checkpoint/session persistence + LangSmith tracing + deterministic quality scoring。
- 前端：Vue 3 + Pinia + Vite，已具备任务详情、阶段进度、错误重试、历史筛选。
- 运行约束：本地 Ollama 模型较慢，建议后续全链路测试继续使用 `quick + 2 条`。
- 运行产物：数据库 WAL/SHM、CSV 输出、LangGraph 临时目录应继续作为 runtime artifacts，不进入提交。

### 下一步建议

1. 考虑 **报表类导出**、**批量生成** 中的一项，视数据量与产品优先级。
2. **响应式布局优化** 按移动端使用频率排期。

## 一、全局追踪与监控

### 1.1 引入 LangSmith

**优先级**: 🔴 高
**状态**: ✅ 已完成
**目标**: 实现模型调用的完整追踪链路，便于调试和性能分析

#### 实现方案

```python
# backend/app/core/langsmith_config.py
import os
from langchain_core.tracers import LangChainTracer
from langchain_core.tracers.forward import ForwardTracer

# 配置LangSmith追踪
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGCHAIN_API_KEY")
os.environ["LANGCHAIN_PROJECT"] = "traffic-agent"
os.environ["LANGCHAIN_ENDPOINT"] = os.getenv("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")

# 在graph运行时添加追踪器
from langchain_openai import ChatOllama

def with_tracing(llm: ChatOllama) -> ChatOllama:
    """包装LLM以启用LangSmith追踪"""
    return ChatOllama(
        model=os.getenv("OLLAMA_MODEL"),
        base_url=os.getenv("OLLAMA_BASE_URL"),
        temperature=0.7,
        # 追踪配置
        callbacks=[LangChainTracer(project_name="traffic-agent")],
    )
```

#### 数据模型扩展

```python
# backend/app/models/schemas.py
class TraceEvent(BaseModel):
    event_type: Literal["llm_call", "rag_retrieval", "eval_pass", "retry"]
    timestamp: datetime
    model: str
    input_tokens: int | None
    output_tokens: int | None
    cost: float | None
    trace_id: str  # 全局追踪ID
```

#### 前端集成

```typescript
// frontend/src/api/trafficApi.ts
export interface TraceInfo {
  trace_id: string
  events: TraceEvent[]
  start_time: number
  end_time: number
}

export async function getTraceInfo(traceId: string): Promise<TraceInfo> {
  const res = await fetch(`${API_BASE}/traces/${traceId}`)
  return res.json()
}
```

---

### 1.2 全局唯一请求追踪ID

**优先级**: 🔴 高
**状态**: ✅ 已完成（当前使用 `session_id` + LangGraph `thread_id` 作为关联主键）
**目标**: 为每个生成请求创建全局追踪ID，关联所有日志和模型调用

#### 当前问题
- `session_id` 仅用于数据库和文件存储
- 日志中只有 `session_id`，缺少关联信息
- 无法追踪单个请求的完整生命周期

#### 实现方案

```python
# backend/app/core/trace.py
import uuid
from contextlib import contextmanager

# 请求级别追踪上下文
_request_context = {}

@contextmanager
def request_context(trace_id: str):
    """请求追踪上下文管理器"""
    _request_context["trace_id"] = trace_id
    _request_context["start_time"] = datetime.now()
    try:
        yield
    finally:
        del _request_context["trace_id"]

def get_current_trace_id() -> str | None:
    """获取当前请求的追踪ID"""
    return _request_context.get("trace_id")

def get_request_duration() -> float | None:
    """获取请求耗时"""
    start = _request_context.get("start_time")
    if start:
        return (datetime.now() - start).total_seconds()
    return None
```

#### 日志增强

```python
# backend/app/graph/nodes.py
import logging

logger = logging.getLogger(__name__)

def rag_node(state: GraphState) -> GraphState:
    trace_id = get_current_trace_id()
    logger.info(f"[{trace_id}] RAG阶段开始，industry={state['industry']}")

    # ... 原有逻辑

    logger.info(f"[{trace_id}] RAG阶段完成，检索到{len(state['retrieved_cases'])}个案例")
    return state

def generate_node(state: GraphState) -> GraphState:
    trace_id = get_current_trace_id()
    logger.info(f"[{trace_id}] 生成阶段开始，数量={state['count']}")
    logger.info(f"[{trace_id}] 生成阶段完成，生成{len(state['generated_records'])}条记录")
    return state
```

#### API响应增强

```python
# backend/app/api/routes.py
@router.post("/generate/stream")
async def generate_traffic_stream(payload: TrafficGenerateRequest) -> StreamingResponse:
    trace_id = uuid.uuid4().hex
    logger.info(f"trace_id={trace_id} 收到流式请求")

    async def event_stream() -> AsyncGenerator[str, None]:
        # 传递trace_id给前端
        yield f"event: start\ndata: {{\"session_id\": \"{session_id}\", \"trace_id\": \"{trace_id}\"}}\n\n"

        # 在生成过程中，所有日志都包含trace_id
        async for event in graph.astream_events(...):
            if event_type == "on_chain_start":
                logger.info(f"[{trace_id}] 节点开始: {node}")

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

---

### 1.3 请求可视化面板

**优先级**: 🟡 中
**状态**: ✅ 已完成第一版（阶段时间线 + 任务详情 + LangSmith 跳转）
**目标**: 在前端展示请求追踪的实时状态和统计数据

#### 功能需求

1. **追踪信息卡片**
   - trace_id（可点击复制）
   - 请求时间、耗时
   - 状态：进行中/已完成/失败/已取消

2. **阶段进度时间线**
   - RAG: X 秒
   - 生成: Y 条/秒
   - 评估: Z 次重试
   - 身份校验: X 秒

3. **模型调用统计**
   - LLM 调用次数
   - 总 Token 消耗
   - 预估成本

#### UI 设计

```vue
<!-- frontend/src/components/TracePanel.vue -->
<template>
  <div class="trace-panel">
    <div class="trace-header">
      <span class="trace-id">{{ traceId }}</span>
      <span class="trace-status" :class="statusClass">{{ statusText }}</span>
    </div>

    <div class="time-line">
      <div v-for="stage in stages" :key="stage.name" class="stage-item">
        <div class="stage-icon">{{ stage.icon }}</div>
        <div class="stage-info">
          <div class="stage-name">{{ stage.name }}</div>
          <div class="stage-duration">{{ stage.duration }}</div>
        </div>
        <div class="stage-progress">
          <div class="progress-bar">
            <div class="progress-fill" :style="{ width: stage.progress + '%' }"></div>
          </div>
        </div>
      </div>
    </div>

    <div class="metrics">
      <div class="metric">
        <span class="metric-label">生成数量</span>
        <span class="metric-value">{{ metrics.recordCount }}</span>
      </div>
      <div class="metric">
        <span class="metric-label">Token消耗</span>
        <span class="metric-value">{{ metrics.tokens }}</span>
      </div>
      <div class="metric">
        <span class="metric-label">预估成本</span>
        <span class="metric-value">${{ metrics.cost }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  traceId: string
  status: string
  stages: any[]
  metrics: any
}>()

const statusClass = computed(() => {
  switch(props.status) {
    case 'completed': return 'success'
    case 'failed': return 'error'
    case 'cancelled': return 'warning'
    default: return 'pending'
  }
})

const statusText = computed(() => {
  switch(props.status) {
    case 'completed': return '已完成'
    case 'failed': return '失败'
    case 'cancelled': return '已取消'
    default: return '进行中'
  }
})
</script>
```

---

## 二、前端体验优化

### 2.1 增强的进度可视化

**优先级**: 🔴 高
**状态**: ✅ 已完成

#### 问题分析
- 当前进度条只有百分比，缺少具体的阶段信息
- 阶段完成时没有明确的视觉反馈

#### 改进方案

```typescript
// frontend/src/types/progress.ts
export interface StageProgress {
  stage: 'rag' | 'generate' | 'eval' | 'identity'
  name: string  // 中文显示名
  progress: number  # 0-100
  duration?: number  # 持续时间（秒）
  retry?: number  # 重试次数
  sampleData?: string  # 示例数据预览
}

export interface ProgressEvent {
  type: 'stage_start' | 'stage_update' | 'stage_complete' | 'stage_error' | 'retry'
  data: StageProgress
}
```

```vue
<!-- frontend/src/components/ProgressCard.vue -->
<template>
  <div class="progress-card">
    <div class="progress-header">
      <span class="current-stage">{{ currentStageName }}</span>
      <span class="progress-percent">{{ progress }}%</span>
    </div>

    <div class="progress-bar">
      <div class="progress-fill" :style="{ width: progress + '%' }"></div>
    </div>

    <div class="stage-detail">
      <div class="detail-item" v-if="retryCount > 0">
        <span class="detail-icon">🔄</span>
        <span class="detail-text">已重试 {{ retryCount }} 次</span>
      </div>
      <div class="detail-item" v-if="duration">
        <span class="detail-icon">⏱️</span>
        <span class="detail-text">耗时 {{ duration }} 秒</span>
      </div>
      <div class="detail-item" v-if="estimatedRate">
        <span class="detail-icon">⚡</span>
        <span class="detail-text">预计 {{ estimatedRate }} 条/秒</span>
      </div>
    </div>

    <!-- 阶段信息 -->
    <div class="stage-info" v-if="currentStage">
      <div class="info-row">
        <span class="info-label">当前阶段:</span>
        <span class="info-value">{{ currentStage.name }}</span>
      </div>
      <div class="info-row" v-if="currentStage.retry">
        <span class="info-label">重试次数:</span>
        <span class="info-value">{{ currentStage.retry }}</span>
      </div>
    </div>
  </div>
</template>
```

---

### 2.2 历史记录增强

**优先级**: 🟡 中
**状态**: ✅ 已完成第一版（高级筛选 + 详情视图 + 下载/删除）

#### 新功能

1. **高级筛选**
   - 按行业筛选
   - 按状态筛选
   - 按日期范围筛选
   - 按质量分数筛选

2. **快速操作**
   - 一键下载
   - 一键删除
   - 结果预览（前10条数据）

3. **详情视图**
   - 查看质量评分详情
   - 查看生成数据统计
   - 重新生成（基于历史数据）

```vue
<!-- frontend/src/components/HistoryFilter.vue -->
<template>
  <div class="history-filter">
    <select v-model="filters.industry">
      <option value="">全部行业</option>
      <option v-for="industry in industries" :value="industry">{{ industry }}</option>
    </select>

    <select v-model="filters.status">
      <option value="">全部状态</option>
      <option value="completed">已完成</option>
      <option value="failed">失败</option>
      <option value="cancelled">已取消</option>
    </select>

    <input
      type="date"
      v-model="filters.dateFrom"
      placeholder="开始日期"
    >
    <input
      type="date"
      v-model="filters.dateTo"
      placeholder="结束日期"
    >

    <button @click="applyFilters">筛选</button>
    <button @click="resetFilters">重置</button>
  </div>
</template>
```

---

### 2.3 错误处理与重试

**优先级**: 🟡 中
**状态**: ✅ 已完成第一版（错误卡片 + 失败阶段标记 + 重试上次请求）

#### 当前问题
- 网络错误时没有重试机制
- 后端错误时用户体验不佳

#### 改进方案

```typescript
// frontend/src/utils/retry.ts
export async function retryWithBackoff<T>(
  fn: () => Promise<T>,
  maxRetries: number = 3,
  baseDelay: number = 1000
): Promise<T> {
  let lastError: Error | null = null

  for (let i = 0; i < maxRetries; i++) {
    try {
      return await fn()
    } catch (error) {
      lastError = error as Error
      if (i < maxRetries - 1) {
        const delay = baseDelay * Math.pow(2, i)
        console.log(`重试 ${i + 1}/${maxRetries}, 延迟 ${delay}ms`)
        await new Promise(resolve => setTimeout(resolve, delay))
      }
    }
  }

  throw lastError
}

// 使用示例
async function startGenerate(payload: GeneratePayload) {
  try {
    await retryWithBackoff(() => generateTrafficStream(...))
  } catch (error) {
    if (error.message.includes('timeout')) {
      showToast('请求超时，正在重试...', 'warning')
    } else {
      showToast('请求失败，请稍后重试', 'error')
    }
  }
}
```

---

### 2.4 响应式布局优化

**优先级**: 🟢 低
**状态**: ⏳ 待做

#### 当前问题
- 移动端体验不佳
- 桌面端界面不够紧凑

#### 改进方案

```vue
<!-- 使用CSS Grid实现响应式布局 -->
<style>
.container {
  display: grid;
  grid-template-columns: 1fr 400px;
  gap: 20px;
}

@media (max-width: 768px) {
  .container {
    grid-template-columns: 1fr;
  }
}
</style>
```

---

## 三、业务丰富度提升

### 3.1 扩展行业场景

**优先级**: 🟡 中
**状态**: ✅ 已完成第一版

#### 当前行业
- government
- ecommerce
- short_video
- ride_hailing
- logistics
- delivery
- finance
- healthcare
- media
- social
- gaming
- custom

#### 建议新增

| 行业 | 描述 | 典型流量特征 |
|------|------|-------------|
| finance | 金融交易 | 大量小额转账、高频交易 |
| healthcare | 医疗系统 | PACS图像传输、电子病历 |
| media | 流媒体服务 | CDN请求、P2P分片 |
| social | 社交媒体 | API调用、图片上传 |
| gaming | 游戏服务 | 心跳包、同步数据 |

```python
# backend/app/graph/nodes.py
INDUSTRY_SCENARIOS = {
    # ... 现有行业
    "finance": {
        "name": "金融交易",
        "patterns": {
            "transaction_volume": "高",
            "transaction_frequency": "极高",
            "data_size": "小",
            "response_time": "快"
        },
        "common_urls": ["/api/v1/transaction", "/api/v1/payment"],
        "http_methods": ["POST", "GET"]
    },
    # ...
}
```

---

### 3.2 质量评估增强

**优先级**: 🟡 中
**状态**: ✅ 已完成（确定性评分 + 各维度扣分说明；历史 `quality_detail` 与 JSON 导出一致）

#### 扩展评估维度

1. **业务逻辑深度评估**
   - HTTP状态码与URL逻辑一致性
   - 用户代理与设备类型匹配
   - Referer与来源URL合理性

2. **时间模式分析**
   - 时间间隔分布是否符合行业特征
   - 峰值时间点与行业匹配度
   - 连续请求的规律性

3. **数据完整性检查**
   - 必填字段覆盖率
   - 字段类型一致性
   - 数值范围合理性

```python
# backend/app/services/generator.py
class EnhancedQualityEvaluator:
    """增强的质量评估器"""

    def evaluate_business_logic(self, records: List[TrafficRecord]) -> dict:
        """业务逻辑评估"""
        score = 0
        total = 0

        # 检查URL模式匹配
        for record in records:
            if record.method == "DELETE" and "/trash" not in record.url:
                score += 10
            total += 1

        return {"score": score, "max_score": total * 10}

    def evaluate_time_pattern(self, records: List[TrafficRecord]) -> dict:
        """时间模式评估"""
        timestamps = [r.timestamp for r in records]
        intervals = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]

        avg_interval = sum(intervals) / len(intervals)
        # ... 分析时间分布
```

---

### 3.3 数据导出格式扩展

**优先级**: 🟡 中
**状态**: ✅ 已完成 JSON + Parquet（CSV 仍保留；`GET /download/{session_id}?format=json|parquet`）

#### 当前格式
- CSV（与任务 `file_path` 一致）
- JSON（同会话侧车文件，含 `metadata` 与 `records` 数组）
- Parquet（同会话目录 `traffic_{industry}_{session_id}.parquet`，列与 CSV 对齐；需依赖 `pyarrow`）

#### 建议新增

1. **JSON 格式**（已实现）
   ```json
   {
     "metadata": {
       "session_id": "...",
       "created_at": "2026-04-21T10:00:00Z",
       "industry": "ecommerce",
       "total_records": 100
     },
     "records": [...]
   }
   ```

2. **Parquet 格式**（✅ 已实现，依赖 `pyarrow`）
   - 更好的性能
   - 支持压缩
   - 适合大数据分析

3. **XML 格式**
   - 用于旧系统兼容

4. **汇总报表**
   - PDF/HTML 格式
   - 包含图表和统计

```typescript
// frontend/src/api/exportApi.ts
export async function exportData(
  sessionId: string,
  format: 'csv' | 'json' | 'parquet' | 'pdf'
) {
  const res = await fetch(`${API_BASE}/download/${sessionId}?format=${format}`)
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `traffic_${sessionId}.${format}`
  a.click()
}
```

---

### 3.4 批量生成功能

**优先级**: 🟢 低
**状态**: ⏳ 待做

#### 功能描述
- 用户可以一次创建多个生成任务
- 设置相同的参数或不同参数的批量

```typescript
// frontend/src/types/generate.ts
export interface BatchGenerateRequest {
  tasks: Array<{
    industry: string
    count: number
    stage: Stage
    priority: 'low' | 'normal' | 'high'
  }>
}

export interface BatchTaskStatus {
  taskId: string
  sessionId: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  progress: number
  createdAt: number
}
```

```vue
<!-- frontend/src/components/BatchGenerate.vue -->
<template>
  <div class="batch-panel">
    <div class="batch-list">
      <div v-for="task in tasks" :key="task.id" class="task-item">
        <div class="task-info">
          <span class="task-industry">{{ task.industry }}</span>
          <span class="task-count">{{ task.count }} 条</span>
          <span class="task-priority">{{ task.priority }}</span>
        </div>
        <div class="task-status">
          <span v-if="task.status === 'running'">⏳ 进行中</span>
          <span v-else-if="task.status === 'completed'">✅ 完成</span>
          <span v-else-if="task.status === 'failed'">❌ 失败</span>
        </div>
      </div>
    </div>
    <button @click="startBatch" class="batch-btn">
      {{ isRunning ? '批量生成中...' : '开始批量生成' }}
    </button>
  </div>
</template>
```

---

## 四、技术优化

### 4.1 前端性能优化

**优先级**: 🟡 中

1. **虚拟滚动**
   - 大量历史记录时只渲染可见区域
   - 使用 `vue-virtual-scroller` 或 `vue-virtual-list`

2. **代码分割**
   ```typescript
   // vite.config.ts
   export default defineConfig({
     build: {
       rollupOptions: {
         output: {
           manualChunks: {
             'chart': ['vue-echarts', 'echarts'],
           }
         }
       }
     }
   })
   ```

3. **图片优化**
   - 使用 WebP 格式
   - 响应式图片
   - CDN 加速

---

### 4.2 后端性能优化

**优先级**: 🟡 中

1. **数据库查询优化**
   - 添加索引
   - 分页查询优化

2. **缓存策略**
   - Redis 缓存热门数据
   - 历史记录缓存

3. **异步任务队列**
   - 使用 Celery 或 Dramatiq
   - 大批量生成使用队列

---

## 五、实施优先级

### 第一阶段（2周）

- [x] 全局唯一追踪ID实现（以 `session_id` + `thread_id` 关联）
- [x] LangSmith 集成
- [x] 增强的进度可视化
- [x] 错误处理与重试机制

### 第二阶段（3周）

- [x] 请求可视化面板（第一版）
- [x] 历史记录高级筛选
- [x] 扩展行业场景
- [x] 质量评估增强（第一版）

### 第三阶段（2周）

- [x] 数据导出格式扩展（JSON + Parquet + 下载参数）
- [ ] 批量生成功能
- [ ] 前端性能优化
- [ ] 后端性能优化

---

## 六、风险评估

| 任务 | 风险 | 缓解措施 |
|------|------|---------|
| LangSmith 集成 | 需要外部API密钥 | 使用本地日志模式作为备选 |
| 大批量生成 | 内存占用高 | 实现流式处理和分块写入 |
| 前端复杂度增加 | 维护难度提升 | 组件化设计，清晰的文档 |
| 扩展行业 | 模型适应性 | 先做小范围测试 |

---

## 七、成功指标

### 功能完成度
- [x] 所有追踪功能正常工作
- [x] 前端可视化准确反映状态
- [x] 错误处理覆盖主要场景
- [x] 质量评分基于生成记录而非随机数

### 用户体验
- [x] 请求追踪信息清晰可见
- [x] 错误提示友好明确
- [x] 操作流程顺畅

### 性能指标
- [ ] 页面加载时间 < 2秒
- [x] 生成任务追踪延迟 < 500ms（事件到前端展示）
- [ ] 历史列表渲染流畅（1000+ 条，待数据量扩大后验证）
