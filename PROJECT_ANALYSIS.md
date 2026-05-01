# Traffic Agent 项目代码分析报告

**分析日期**: 2026-04-29
**分析范围**: 完整后端 (`backend/app/`) 和前端 (`frontend/src/`) 代码
**环境上下文**: Windows 10 + Ollama (qwen2.5:7b) 本地部署

> ⚠️ 本报告**已排除**因开发环境（Win10 + 低配模型）导致的性能/并发问题，仅聚焦代码层面的架构和功能缺陷。环境类问题在 ROADMAP.md 中单独标记。

---

## 一、项目概览

### 1.1 核心架构

```
用户浏览器 (Vue 3 + Pinia + Vite)
    │  SSE Stream / REST API
    ▼
FastAPI (uvicorn, port 8000)
    │
    ├── routes.py         API 端点（生成/历史/下载/报表/批量）
    ├── session_service   SQLite CRUD
    ├── generator.py      LLM 调用 + CSV/JSON/Parquet 写入
    ├── report_service    HTML 报表（含 ECharts 图表）
    │
    ▼
LangGraph 工作流（nodes.py + workflow.py）
    │
    ├── rag_node        场景推断 + 案例检索
    ├── generate_node   LLM 流量生成
    ├── eval_node       三维度质量评分（格式/业务/多样性）
    └── identity_node   身份校验（full 模式）
        │
        ▼
LangSmith Tracing (traceable 装饰器)
SQLite (traffic_sessions / batch_sessions / batch_tasks)
```

### 1.2 技术栈

| 层 | 技术 | 用途 |
|----|------|------|
| Web 框架 | FastAPI | REST API + SSE 流式 |
| AI 编排 | LangGraph | 四阶段 DAG 流水线 |
| AI 模型 | Ollama (qwen2.5:7b) | 流量数据生成 |
| 数据库 | SQLite (threading.local) | 会话/批次持久化 |
| 前端框架 | Vue 3 + Pinia + Vite | SPA 控制台 |
| 可视化 | ECharts 5.6 | 报表雷达图/饼图/柱状图 |
| 可观测 | LangSmith | LLM 调用追踪 |
| 数据格式 | CSV + JSON + Parquet (Snappy) | 多格式导出 |

---

## 二、前端代码分析

### 2.1 架构概览

```
frontend/src/
├── App.vue               单文件 SPA（生成 + 批量 + 历史 三个 Section）
├── main.ts               Vue 挂载入口
├── api/trafficApi.ts     所有 API 调用 + SSE 流式解析
├── stores/trafficStore.ts Pinia store（状态 + 历史筛选 + 批量子弹）
└── style.css             全局样式（CSS Grid 布局）
```

**特点**:
- 无路由，单页面三面板
- 无组件拆分（所有 UI 在 App.vue 模板中）
- Store 承担全部业务逻辑（生成、历史、批量、筛选）

### 2.2 问题清单

#### 🔴 P0 — 响应式布局缺失

**位置**: `App.vue` + `style.css`

桌面端使用 CSS Grid 双栏布局 (`.container { grid-template-columns: 1fr 400px }`)，无任何 `@media` 断点。在视口 < 768px 时出现水平滚动条，内容溢出。

**建议**: 添加 `@media (max-width: 768px)` 规则，切换为 `grid-template-columns: 1fr`。

#### 🔴 P0 — 历史记录无分页

**位置**: `stores/trafficStore.ts:151-153`

```typescript
async refreshHistory() {
    const data = await listHistory(1, 20)  // 固定 page=1
    this.history = data.items
}
```

后端返回 `total_pages` 字段，但前端完全没用。超过 20 条历史记录无法查看。

**建议**: History Section 底部加分页按钮，传递 `page` 参数。

#### 🔴 P0 — 历史筛选纯前端，无后端过滤

**位置**: `stores/trafficStore.ts:114-145`

`filteredHistory` getter 在客户端对已加载的 20 条做多维度过滤。后端 `/history` 接口不支持筛选参数（仅 page/page_size）。如果未来前端暴露分页，需要同时给后端加筛选 query params。

**建议**: 后端 `/history` 增加 `industry`/`status`/`stage`/`keyword`/`date_from`/`date_to`/`min_quality` 参数。

#### 🟡 P1 — 无组件拆分

**位置**: `App.vue` 整个文件 394 行。

所有 UI（生成表单、批量面板、历史表格、任务详情卡片）在一个文件中。修改一个面板需要在大模板中定位。

**建议**: 拆为独立组件：
- `GeneratePanel.vue`
- `BatchPanel.vue`
- `HistoryTable.vue`
- `TaskDetailCard.vue`

#### 🟡 P1 — 历史列表无虚拟滚动

**位置**: `App.vue:304-326`

`v-for` 直接渲染全部 `filteredHistory`，无虚拟滚动。当前数据量 (< 100 条) 无感，但记录增长后性能下降。

**建议**: 引入 `vue-virtual-scroller` 或 `@tanstack/vue-virtual`。

#### 🟢 P2 — 报表链接体验可改进

**位置**: `App.vue:386-388`

```html
<a :href="store.reportUrl(...)" target="_blank">📊 导出 HTML 报告</a>
```

- 无 PDF 导出入口，用户需手动 Ctrl+P
- 链接在详情卡片底部，不够显眼

**建议**: 
- 历史表格加"报表"列，直接可点击
- 后端加 `?format=pdf` 参数

#### 🟢 P2 — UI 导航扁平

生成/批量/历史三个 Section 堆叠，需滚动。小屏下尤其不友好。

**建议**: 顶部加 Tab 切换或左侧 Sidebar。

---

## 三、后端代码分析

### 3.1 架构概览

```
backend/app/
├── main.py               FastAPI app 创建 + CORS
├── api/routes.py          所有 API 端点（508 行）
├── core/
│   ├── config.py          Settings (pydantic BaseModel)
│   └── state.py           取消状态管理（内存 set）
├── db/database.py         SQLite threading.local 连接 + init_db
├── graph/
│   ├── state.py           GraphState TypedDict
│   ├── nodes.py           rag/generate/eval/identity 四节点（168 行）
│   └── workflow.py        图构建 + lru_cache 编译（50 行）
├── models/schemas.py      Pydantic 数据模型（111 行）
└── services/
    ├── generator.py        LLM 调用 + 质量评分 + CSV/JSON/Parquet（623 行）
    ├── session_service.py  会话 CRUD + 批量任务（303 行）
    ├── report_service.py   HTML 报表 + ECharts（~280 行）
    ├── graph_runner.py     Graph 执行封装
    ├── langchain_service.py LLM hint 构建
    └── tracing_config.py  LangSmith 配置
```

### 3.2 问题清单

#### 🔴 P0 — RAG 阶段是 Mock 实现

**位置**: `backend/app/graph/nodes.py:84-97`

```python
def rag_node(state: GraphState) -> GraphState:
    state["scenario"] = infer_scenario(state["industry"])
    state["retrieved_cases"] = [
        {"industry": state["industry"], "scenario": state["scenario"], "content": "mock_case"}
    ]
```

**问题**: `infer_scenario()` 是硬编码字典映射（`industry → "通勤高峰"` 等），`retrieved_cases` 是写死的 `"mock_case"`。没有真正的知识库检索，LLM 生成依赖 prompt 中仅 2 条电商硬编码示例（`_get_examples()`），跨行业泛化能力弱。

**影响**: 除电商外的行业，LLM 生成的 URL 和请求体往往不符合行业特征。

**修复方案**:
```python
# 方案 A（轻量，推荐先做）
import json
from pathlib import Path

EXAMPLES_DIR = Path("data/examples")

def rag_node(state: GraphState) -> GraphState:
    state["scenario"] = infer_scenario(state["industry"])
    
    # 加载行业示例文件
    example_file = EXAMPLES_DIR / f"{state['industry']}.json"
    if example_file.exists():
        examples = json.loads(example_file.read_text())
        state["retrieved_cases"] = [
            {"type": "few_shot", "content": ex} for ex in examples[:5]
        ]
    else:
        state["retrieved_cases"] = [
            {"type": "fallback", "content": "mock_case"}
        ]
    return state
```

#### 🔴 P0 — industry 字段无输入校验

**位置**: `backend/app/models/schemas.py:22-23`

```python
class TrafficGenerateRequest(BaseModel):
    industry: str = Field(..., min_length=1, max_length=64)
```

**问题**: 接受任意字符串。`"asdf"` 通过校验但 `infer_scenario()` 返回 `"自定义场景"`，`_industry_context()` 返回 `"自定义业务接口"`，`_industry_paths()` 返回空列表 → 评分全零，生成质量极差。

**修复**:
```python
from typing import Literal

VALID_INDUSTRIES = Literal[
    "government", "ecommerce", "short_video", "ride_hailing",
    "logistics", "delivery", "finance", "healthcare",
    "media", "social", "gaming", "custom",
]

class TrafficGenerateRequest(BaseModel):
    industry: VALID_INDUSTRIES = Field(...)
```

#### 🟡 P1 — /history 端点无服务端筛选

**位置**: `backend/app/api/routes.py:349-362`

```python
@router.get("/history")
async def get_history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    total, items = list_history(page, page_size)
```

**问题**: 仅支持分页，无任何筛选参数。前端所有筛选逻辑在 store 中做客户端过滤。未来需要加 `industry`/`status`/`stage`/`keyword` 等 query params。

#### 🟡 P1 — LLM 调用为同步阻塞

**位置**: `backend/app/services/generator.py:238`

```python
response = llm.invoke(f"{system_prompt}\n\n请生成流量数据")
```

**问题**: `ChatOllama.invoke()` 是同步调用。在 LangGraph 节点内直接阻塞事件循环，期间无法响应其他请求。当前 Ollama 本地部署无此问题，但生产环境或换远程 API 时需改为 `await llm.ainvoke()`。

#### 🟡 P1 — /generate (sync) 端点冗余

**位置**: `backend/app/api/routes.py:55-108`

同步 `/generate` 端点直接调用 `run_generation_graph()` 阻塞返回。前端默认走 `/generate/stream` 流式端点获取 SSE 进度。同步端点仅保留兼容，但代码量不小（60 行），与流式端点有大段重复。

**建议**: 标记 deprecated 或提取公共逻辑到 service 层。

#### 🟡 P1 — 取消操作无法中断 LLM 调用

**位置**: `backend/app/graph/nodes.py:23-26` + `backend/app/services/generator.py:238`

```python
def _check_cancelled(session_id: str) -> None:
    if is_cancelled(session_id):
        raise RuntimeError("Task cancelled by user")
```

**问题**: `_check_cancelled()` 在每个节点开始时检查，但 LLM 调用 `llm.invoke()` 在 `generate_node` 内部执行，期间无法响应取消。用户点击取消后需等待当前 LLM 调用返回（10-60 秒）。

**影响**: 用户体验差，但受限于 LangGraph + 同步 LLM 调用的架构约束，当前无法根本解决。

#### 🟢 P2 — 无 API 鉴权

**位置**: `backend/app/main.py:9-15`

```python
app.add_middleware(CORSMiddleware, allow_origins=["*"], ...)
```

纯本地开发场景无风险，但无任何 token/key 验证。公网部署时需加。

#### 🟢 P2 — `on_event("startup")` 已 deprecated

**位置**: `backend/app/main.py:19`

```python
@app.on_event("startup")
def on_startup() -> None:
    init_db()
```

FastAPI 推荐使用 lifespan context manager。当前仍可工作但有 deprecation warning。

**修复**:
```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(lifespan=lifespan)
```

---

## 四、已解决的过往问题

| 问题 | 原状态 | 当前状态 |
|------|--------|---------|
| SQLite `check_same_thread=False` 线程不安全 | 全局单连接 | ✅ `threading.local()` 每线程独立连接 |
| `asyncio.Lock()` 全局互斥 | 单并发锁 | ✅ `Semaphore(3)` 三并发池 |
| 取消只设标记不检查 | 无法中断 | ✅ 每个节点入口 `_check_cancelled()` |
| CSV header/body 内嵌 JSON 不规范 | 大 CSV 问题 | ✅ 并行写入 JSON + Parquet 侧车文件 |
| 质量评分随机 | 无意义评分 | ✅ 三维度确定性评分 + 扣分说明 |
| 前端无错误处理 | 静默失败 | ✅ 错误卡片 + 重试按钮 + SSE error 事件 |
| 无测试 | 0% 覆盖率 | ✅ 14 个 pytest 覆盖核心模块 |
| 无报表 | 只能下载 CSV | ✅ HTML + ECharts 四图表 |

---

## 五、建议优先修复顺序

### 第一批：快赢（1-2 天）

1. **industry 枚举校验** — 改动 1 行 + 前端联动，立竿见影防呆
2. **历史分页** — 前端加分页按钮，后端接口已就绪

### 第二批：高价值（3-5 天）

3. **RAG 升级** — 11 个行业各 3-5 条示例 JSON，生成质量明显提升
4. **响应式布局** — 加 @media 断点，移动端可用
5. **/history 后端筛选** — 加 query params，支持大规模历史

### 第三批：体验打磨（1-2 周）

6. **Tab 导航** — 三 Section 拆 Tab，改善信息密度
7. **组件拆分** — App.vue 拆 4 个子组件
8. **on_event → lifespan** — 消除 deprecation warning

### 不急于处理

- 虚拟滚动（当前数据量 < 100 条无必要）
- API 鉴权（纯本地开发无风险）
- 异步 LLM 调用（Ollama 本地无网络延迟）
- 取消立即中断（受架构约束，短期无解）
