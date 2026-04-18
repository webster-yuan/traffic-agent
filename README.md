# Traffic Agent

一个基于AI的流量数据生成和分析系统，用于生成真实的和伪造的网络流量数据，用于安全研究和机器学习训练。

## 项目描述

Traffic Agent 是一个全栈应用，使用前沿的AI技术生成高质量的网络流量模拟数据。该项目结合了多种先进的AI模型和技术栈，提供完整的流量数据生成、管理和分析功能。

## 技术栈

- **AI引擎**: Opencode + GLM-4.5-Flash + Ollama + qwen2.5:7b-instruct-q4_K_M
- **后端框架**: FastAPI + Python 3.11+
- **前端框架**: Vue.js 3 + TypeScript + Vite
- **数据库**: SQLite (支持扩展到PostgreSQL)
- **机器学习**: LangChain + LangGraph + Pydantic
- **容器化**: Docker (可配置)
- **测试**: Pytest + Vitest

## 功能特性

- 🚀 **智能数据生成**: 使用AI模型生成真实的和伪造的网络流量数据
- 📊 **数据分析**: 提供详细的数据分析和可视化功能
- 🔒 **安全研究**: 支持网络安全研究和威胁检测
- 🎯 **精确控制**: 精确控制生成数据的类型和特征
- 🔄 **实时处理**: 支持实时数据生成和处理
- 📈 **可扩展**: 模块化设计，易于扩展和维护

## 项目结构

```
traffic-agent/
├── backend/                 # 后端服务
│   ├── app/               # 应用核心代码
│   │   ├── api/           # API路由
│   │   ├── core/          # 核心配置
│   │   ├── db/            # 数据库模型
│   │   ├── models/        # 数据模型
│   │   └── services/      # 业务逻辑
│   ├── data/              # 数据文件
│   │   └── outputs/       # 输出数据
│   └── tests/             # 测试文件
├── frontend/              # 前端应用
│   ├── src/               # 源代码
│   └── public/            # 静态资源
├── docs/                  # 文档
└── .env                  # 环境变量
```

## 安装说明

### 环境要求

- Python 3.11+
- Node.js 18+
- npm 或 yarn
- Ollama (用于AI模型)

### 后端安装

1. 进入后端目录
```bash
cd backend
```

2. 创建虚拟环境
```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# 或者在Windows上
.venv\Scripts\activate
```

3. 安装依赖
```bash
pip install -r requirements.txt
```

4. 配置环境变量
```bash
cp .env.example .env
# 编辑 .env 文件，配置必要的环境变量
```

### 前端安装

1. 进入前端目录
```bash
cd frontend
```

2. 安装依赖
```bash
npm install
```

## 使用方法

### 启动后端服务

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 启动前端服务

```bash
cd frontend
npm run dev
```

### 生成数据

通过API接口生成数据：

```bash
curl -X POST "http://localhost:8000/generate" \
  -H "Content-Type: application/json" \
  -d '{"type": "real", "count": 10}'
```

### 数据分析

访问前端界面进行数据可视化和分析：
```
http://localhost:5173
```

## API文档

启动后端服务后，访问以下地址查看API文档：
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### 主要API端点

- `GET /health` - 健康检查
- `POST /generate` - 生成流量数据
- `GET /data/{id}` - 获取指定数据
- `GET /data/list` - 获取数据列表
- `DELETE /data/{id}` - 删除数据

## 配置说明

### 环境变量

```env
# 应用配置
APP_NAME=Traffic Agent
APP_VERSION=1.0.0

# 数据库配置
DATABASE_URL=sqlite:///./data.db

# AI模型配置
OLLAMA_HOST=http://localhost:11434
MODEL_NAME=qwen2.5:7b-instruct-q4_K_M

# API配置
API_HOST=0.0.0.0
API_PORT=8000
```

## 开发指南

### 代码规范

- Python: 遵循PEP 8规范
- TypeScript: 使用ESLint + Prettier
- 提交消息: 使用Conventional Commits格式

### 测试

```bash
# 后端测试
cd backend
pytest

# 前端测试
cd frontend
npm test
```

## 部署

### Docker部署

```bash
# 构建镜像
docker build -t traffic-agent .

# 运行容器
docker run -p 8000:8000 -p 5173:5173 traffic-agent
```

### 生产环境部署

1. 配置生产环境变量
2. 构建前端项目: `npm run build`
3. 使用Gunicorn运行后端: `gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker`

## 许可证

MIT License

## 贡献指南

1. Fork 项目
2. 创建功能分支
3. 提交更改
4. 推送到分支
5. 创建 Pull Request

## 联系方式

- 项目主页: https://github.com/your-username/traffic-agent
- 问题反馈: https://github.com/your-username/traffic-agent/issues

## 致谢

感谢以下开源项目和AI模型的支持：
- FastAPI团队
- Vue.js团队
- Ollama团队
- GLM-4.5-Flash模型
- qwen2.5:7b-instruct-q4_K_M模型