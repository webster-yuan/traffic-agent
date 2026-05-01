# Traffic Agent

基于 LLM 的网络流量数据生成和分析系统，用于安全研究和机器学习训练。

## 项目简介

Traffic Agent 是一个全栈 AI 应用，结合 LangGraph、FastAPI 和 Vue 3，使用本地大语言模型（Ollama + Qwen2.5 7B）生成高质量的模拟网络流量数据。系统采用四阶段流水线（RAG → 生成 → 评估 → 身份校验），支持 SSE 流式进度、ECharts 可视化报表、批量生成、7 维度历史筛选、CSV/JSON/Parquet 多格式导出。

## 核心特性

- **AI 驱动**: Ollama + Qwen2.5 7B 本地模型，异步调用 + asyncio.wait_for 超时保护
- **RAG 增强**: 12 个行业静态示例 JSON 注入 LLM system prompt，提升生成质量
- **四阶段流水线**: RAG（场景推断 + 示例检索）→ 生成（异步 LLM）→ 评估（三维度评分）→ 身份校验
- **质量评分**: 格式（30%）+ 业务（40%）+ 多样性（30%），附带扣分说明，未通过自动重试
- **ECharts 报表**: HTML 报表含雷达图（质量评分）、饼图（身份分布）、柱状图（HTTP 方法/状态码）
- **批量生成**: 最多 10 任务并发，asyncio.Semaphore(3) 并发控制，2 秒轮询进度
- **历史管理**: 7 维度服务端筛选（关键字/行业/阶段/状态/日期/评分），分页 + CSS 虚拟滚动
- **多格式导出**: CSV / JSON（含 metadata + records）/ Parquet 侧车文件
- **SSE 流式**: 实时推送四阶段进度，阶段时间线可视化，支持取消 + 错误重试
- **可观测性**: LangSmith Trace 集成 + session_id/thread_id 关联

## 技术栈

### 后端
- **框架**: FastAPI + Python 3.11+
- **AI 引擎**: Ollama (Qwen2.5 7B) + LangChain + LangChain-Ollama
- **工作流**: LangGraph (StateGraph + 条件边 + 异步节点)
- **可观测性**: LangSmith trace + metadata 关联
- **数据库**: SQLite (aiosqlite 异步 + threading.local 连接池)
- **验证**: Pydantic (Industry Literal 枚举校验)
- **图表**: ECharts (HTML 报表内嵌)
- **测试**: Pytest (45 个测试用例)

### 前端
- **框架**: Vue 3 + TypeScript + Vite 8 (代码分割)
- **状态管理**: Pinia (3 stores)
- **组件**: Composition API + 3 个 Panel 组件 (Generate / Batch / History)
- **测试**: Vitest (7 个测试用例)

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+
- Ollama (用于本地 AI 模型)

### 安装步骤

1. 克隆项目
```bash
git clone <repository-url>
cd traffic-agent
```

2. 启动 Ollama 并拉取模型
```bash
ollama serve
# 新终端
ollama pull qwen2.5:7b-instruct-q4_K_M
```

3. 安装后端依赖
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

4. 安装前端依赖
```bash
cd frontend
npm install
```

5. 启动后端
```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

6. 启动前端（新终端）
```bash
cd frontend
npm run dev
```

访问 http://localhost:5173 使用 Web 界面。

## API 端点

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | /api/v1/traffic/generate | 生成流量数据（同步） |
| POST | /api/v1/traffic/generate/stream | 生成流量数据（SSE 流式） |
| DELETE | /api/v1/traffic/generate/{session_id} | 取消生成 |
| GET | /api/v1/traffic/history | 历史记录（7 维度筛选 + 分页） |
| DELETE | /api/v1/traffic/history/{session_id} | 删除历史记录 |
| GET | /api/v1/traffic/download/{session_id} | 下载结果（csv/json/parquet） |
| GET | /api/v1/traffic/report/{session_id} | HTML 报告（ECharts 图表） |
| POST | /api/v1/traffic/batch | 批量生成（最多 10 任务） |
| GET | /api/v1/traffic/batch/{batch_id} | 批量任务状态 |
| GET | /health | 健康检查 |

### 请求示例

```bash
# SSE 流式生成（推荐）
curl -X POST "http://localhost:8000/api/v1/traffic/generate/stream" \
  -H "Content-Type: application/json" \
  -d '{"industry": "ecommerce", "count": 5, "stage": "quick"}'

# 历史筛选
curl "http://localhost:8000/api/v1/traffic/history?industry=ecommerce&status=completed&page=1&page_size=20"

# 下载 JSON（含 metadata + records）
curl "http://localhost:8000/api/v1/traffic/download/{session_id}?format=json"
```

## 项目结构

```
traffic-agent/
├── backend/
│   ├── app/
│   │   ├── api/routes.py              # API 路由（生成/历史/下载/报表/批量）
│   │   ├── core/
│   │   │   ├── config.py              # 配置管理
│   │   │   └── state.py               # 取消状态管理
│   │   ├── db/database.py             # SQLite (threading.local 连接池)
│   │   ├── graph/
│   │   │   ├── state.py               # GraphState 类型定义
│   │   │   ├── workflow.py            # LangGraph 工作流编译
│   │   │   └── nodes.py               # 4 个处理节点 (rag/generate/eval/identity)
│   │   ├── models/schemas.py          # Pydantic 数据模型 (Industry Literal 枚举)
│   │   ├── services/
│   │   │   ├── generator.py           # LLM 生成 + 质量评分 + CSV/JSON/Parquet 写入
│   │   │   ├── graph_runner.py        # 图执行器 (同步/异步)
│   │   │   ├── report_service.py      # HTML 报表生成 (ECharts 图表)
│   │   │   ├── session_service.py     # 会话 CRUD + 7 维度筛选 + 批量任务
│   │   │   ├── langchain_service.py   # LLM hint 构建
│   │   │   └── tracing_config.py      # LangSmith 追踪配置
│   │   └── main.py                    # FastAPI 应用入口
│   ├── tests/                         # 45 个 pytest 测试
│   ├── data/
│   │   ├── examples/                  # 12 个行业示例 JSON (RAG 静态资源)
│   │   └── outputs/                   # 生成的 CSV/JSON/Parquet
│   ├── cleanup.py
│   ├── cleanup_schedule.py
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/trafficApi.ts          # API 客户端
│   │   ├── components/
│   │   │   ├── GeneratePanel.vue      # 单任务生成面板
│   │   │   ├── BatchPanel.vue         # 批量生成面板
│   │   │   └── HistoryPanel.vue       # 历史记录面板 (虚拟滚动)
│   │   ├── stores/                    # Pinia stores (trafficStore + batchStore)
│   │   ├── App.vue                    # Tab 导航主框架
│   │   ├── main.ts
│   │   └── style.css                  # 全局样式 (含虚拟滚动 CSS)
│   ├── package.json
│   └── vite.config.ts                 # Vite 8 + 代码分割
└── docs/
    ├── 开发设计文档_v1.0.md
    ├── 流量字段枚举.md
    └── 项目需求文档_v1.0.md
```

## 工作流架构

### 四阶段流水线

```
START
  ↓
[rag] ← 场景推断 + 静态 JSON 示例检索
  ↓
[generate] ← 异步 LLM 生成 (ainvoke + asyncio.wait_for 超时)
  ↓
[eval] ← 三维度质量评分 (格式 30% + 业务 40% + 多样性 30%)
  ↓
  ├─ 未通过 → retry → [generate] (最多重试 N 次)
  └─ 通过 → [identity] ← 身份校验 (仅 full 模式)
              ↓
             END
```

### 质量评分标准

| 维度 | 权重 | 检测内容 |
|------|------|----------|
| 格式评分 | 30% | JSON 结构、字段完整性、类型正确性、必填字段 |
| 业务评分 | 40% | URL 行业匹配、HTTP 方法合理性、状态码一致性 |
| 多样性评分 | 30% | IP 分布、时间间隔、User-Agent 多样性、URL 路径变化 |

### 生成模式

| 模式 | RAG | 身份校验 | 默认数量 |
|------|-----|----------|----------|
| quick | 静态 JSON 示例 | - | 5 条 |
| standard | 静态 JSON 示例 | - | 10 条 |
| full | 静态 JSON 示例 | mock | 10 条 |

## 开发指南

### 运行测试

```bash
# 后端 (45 个测试)
cd backend
pytest -v

# 前端 (7 个测试)
cd frontend
npm test
```

### 环境变量

```env
# Ollama 配置
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b-instruct-q4_K_M

# LLM 超时 (秒)
LLM_TIMEOUT=300

# LangSmith 追踪 (可选)
LANGCHAIN_TRACING_V2=true
LANGSMITH_API_KEY=your_api_key
LANGSMITH_PROJECT=traffic-agent

# 质量评估配置
MAX_RETRY_COUNT=3
QUALITY_PASS_THRESHOLD=70
```

### 定时清理

```bash
python backend/cleanup.py           # 手动清理 30 天前数据
python backend/cleanup_schedule.py  # 设置定时清理
```

## 已知限制

- 取消操作不能立即中断正在进行中的 LLM 调用（需等 LLM 返回后才检查取消标记）
- LLM 生成速度受本地 Ollama 模型限制（2-5s/条）
- 无 Docker 化部署（当前 Windows 10 环境限制）
- 无 API 鉴权（纯本地开发，CORS allow_origins=["*"]）

## 许可证

MIT License
