# Traffic Agent

基于 LLM 的网络流量数据生成和分析系统，用于安全研究和机器学习训练。

## 项目简介

Traffic Agent 是一个全栈 AI 应用，结合了 LangGraph、FastAPI 和 Vue.js 3，使用大语言模型生成高质量的模拟网络流量数据。系统采用多阶段流水线架构（RAG → 生成 → 评估 → 身份校验），提供实时流式响应和精确的数据控制。

## 核心特性

- 🤖 **AI 驱动**: 使用 Qwen2.5 7B 模型生成逼真的流量数据
- 🔄 **多阶段流水线**: RAG → 生成 → 评估 → 身份校验四阶段处理
- 📊 **质量评分**: 自动评估数据格式、业务逻辑和多样性
- 🚀 **实时流式**: SSE 流式传输进度和结果
- 📈 **多模式支持**: quick/standard/full 三种生成模式
- 🗄️ **持久化存储**: SQLite 数据库 + CSV 文件导出
- 🧪 **测试覆盖**: 包含 API、并发、取消、数据库等测试

## 技术栈

### 后端
- **框架**: FastAPI + Python 3.11+
- **AI 引擎**: Ollama (Qwen2.5 7B) + LangChain
- **工作流**: LangGraph (状态图 + 条件边)
- **数据库**: SQLite (aiosqlite 异步)
- **验证**: Pydantic
- **测试**: Pytest

### 前端
- **框架**: Vue.js 3 + TypeScript + Vite
- **状态管理**: Pinia
- **组件**: TypeScript + Composition API
- **测试**: Vitest

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+
- Ollama (用于 AI 模型)

### 安装步骤

1. 克隆项目
```bash
git clone <repository-url>
cd traffic-agent
```

2. 启动 Ollama 并拉取模型
```bash
# Windows
ollama serve

# 拉取模型（新终端）
ollama pull qwen2.5:7b-instruct-q4_K_M
```

3. 安装后端依赖
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

pip install -r requirements.txt
```

4. 安装前端依赖
```bash
cd frontend
npm install
```

5. 启动后端服务
```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

6. 启动前端服务（新终端）
```bash
cd frontend
npm run dev
```

访问 [http://localhost:5173](http://localhost:5173) 使用 Web 界面。

## API 文档

启动后端服务后访问：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### 主要端点

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | /generate | 生成流量数据（流式响应） |
| GET | /sessions | 获取会话列表 |
| GET | /sessions/{id} | 获取会话详情 |
| DELETE | /generate/{session_id} | 取消生成 |
| GET | /download/{session_id} | 下载 CSV 文件 |
| GET | /health | 健康检查 |

### 请求示例

```bash
curl -X POST "http://localhost:8000/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "industry": "ecommerce",
    "count": 100,
    "stage": "standard"
  }'
```

## 项目结构

```
traffic-agent/
├── backend/                     # 后端服务
│   ├── app/
│   │   ├── api/
│   │   │   └── routes.py       # API 路由和流式处理
│   │   ├── core/
│   │   │   └── config.py       # 配置管理
│   │   ├── db/
│   │   │   └── database.py     # SQLite 数据库操作
│   │   ├── graph/
│   │   │   ├── state.py        # 图状态定义
│   │   │   ├── workflow.py     # LangGraph 工作流定义
│   │   │   └── nodes.py        # 处理节点
│   │   ├── models/
│   │   │   └── schemas.py      # Pydantic 数据模型
│   │   ├── services/
│   │   │   ├── generator.py    # 核心生成逻辑
│   │   │   ├── graph_runner.py # 图运行器
│   │   │   ├── langchain_service.py
│   │   │   └── session_service.py
│   │   └── main.py             # FastAPI 应用入口
│   ├── tests/                  # 测试文件
│   │   ├── conftest.py
│   │   ├── test_routes.py
│   │   ├── test_graph_runner.py
│   │   ├── test_concurrency.py
│   │   ├── test_cancellation.py
│   │   ├── test_database.py
│   │   └── test_llm_timeout.py
│   ├── data/                   # 数据目录
│   │   └── outputs/            # 生成的 CSV 文件
│   ├── cleanup.py              # 清理脚本
│   ├── cleanup_schedule.py     # 定时清理
│   └── requirements.txt
├── frontend/                    # 前端应用
│   ├── src/
│   │   ├── api/                # API 客户端
│   │   ├── components/         # Vue 组件
│   │   ├── stores/             # Pinia 状态管理
│   │   ├── App.vue
│   │   ├── main.ts
│   │   └── style.css
│   ├── package.json
│   ├── vitest.config.ts
│   ├── tsconfig.json
│   └── vite.config.ts
├── docs/                        # 文档
│   ├── 开发设计文档_v1.0.md
│   ├── 流量字段枚举.md
│   └── 项目需求文档_v1.0.md
└── README.md
```

## 工作流架构

### 多阶段处理流水线

```
START
  ↓
[rag] ← 场景推断（Mock 实现）
  ↓
[generate] ← LLM 生成流量数据
  ↓
[eval] ← 质量评分（格式+业务+多样性）
  ↓
  ├─ 检查失败 → retry → generate
  └─ 检查通过 → identity
       ↓
      [identity] ← 身份校验（full 模式）
       ↓
      END
```

### 质量评分标准

| 维度 | 权重 | 说明 |
|------|------|------|
| 格式评分 | 30% | JSON 格式、字段完整性、类型正确性 |
| 业务评分 | 40% | URL 逻辑、HTTP 方法匹配、状态码一致性 |
| 多样性评分 | 30% | IP 分布、时间间隔、数据变异性 |

### 生成模式

| 模式 | RAG | 身份校验 | 生成数量 |
|------|-----|----------|----------|
| quick | ❌ | ❌ | 50 条 |
| standard | ❌ | ❌ | 100 条 |
| full | ❌ | ✅ | 100 条 |

## 数据模型

### TrafficRecord

```typescript
{
  id: string,
  method: "GET" | "POST" | "PUT" | "DELETE" | "PATCH",
  url: string,
  status_code: number,
  timestamp: Date,
  src_ip: string,
  src_port: number,
  dst_ip: string,
  dst_port: number,
  header: Record<string, string>,
  req_body: Record<string, any> | null,
  resp_body: Record<string, any> | null,
  rtt: number | null,
  duration: number | null,
  user_agent: string | null,
  referer: string | null,
  identity_label: "real" | "fake" | "anomaly"
}
```

## 开发指南

### 运行测试

```bash
# 后端测试
cd backend
pytest -v

# 前端测试
cd frontend
npm test
```

### LangGraph CLI 调试

后端可直接在终端启动 LangGraph CLI，用于本地开发和调试图执行。LangSmith 上报由 LangChain/LangGraph 根据环境变量自动处理：

```bash
cd backend
langgraph dev --host 127.0.0.1 --port 2024 --config langgraph.json
```

如需自动上传到 LangSmith，请在 `backend/.env` 中配置 `LANGSMITH_API_KEY`、`LANGCHAIN_TRACING_V2=true` 和 `LANGSMITH_PROJECT`。

### 代码规范

- Python: 遵循 PEP 8 规范
- TypeScript: 使用 ESLint + Prettier
- 提交消息: 使用 Conventional Commits 格式

### 环境变量配置

```env
# 应用配置
APP_NAME=Traffic Agent
APP_VERSION=1.0.0

# 数据库配置
DATABASE_URL=sqlite:///./data.db
CHECKPOINT_DB_PATH=./.langgraph/checkpoint.sqlite

# AI 模型配置
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b-instruct-q4_K_M

# API 配置
API_HOST=0.0.0.0
API_PORT=8000

# LLM 超时配置
LLM_TIMEOUT=120
```

### 定时清理

```bash
# 手动清理旧数据
python backend/cleanup.py

# 设置定时清理（24小时）
python backend/cleanup_schedule.py
```

## 已知问题与修复

- [x] SQLite 线程安全问题（使用 aiosqlite + 连接池）
- [x] 并发限制过严（使用 Semaphore 并发池）
- [x] 流式响应取消功能（条件边实现）
- [x] API 文档缺失（已补充）

详细问题分析和修复方案请参考 [PROJECT_ANALYSIS.md](PROJECT_ANALYSIS.md)。

## 部署

### Docker 部署

```bash
# 构建镜像
docker build -t traffic-agent .

# 运行容器
docker run -p 8000:8000 -p 5173:5173 traffic-agent
```

### 生产环境部署

```bash
# 后端
cd backend
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --access-logfile - \
  --error-logfile -

# 前端构建
cd frontend
npm run build
```

## 许可证

MIT License

## 贡献指南

1. Fork 项目
2. 创建功能分支
3. 提交更改
4. 推送到分支
5. 创建 Pull Request

## 联系方式

- 项目主页: https://github.com/webster-yuan/traffic-agent
- 问题反馈: https://github.com/webster-yuan/traffic-agent/issues
