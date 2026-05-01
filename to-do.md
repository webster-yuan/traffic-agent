# Traffic Agent 后续拓展路线

> **更新**: 2026-05-01 — 数据质量深化已全部落地，仅保留平台化远期规划。

---

## 1. 数据质量深化（中期） ✅ — 已落地 2026-04-29

- ✅ 字段合法性检测：IP 格式、端口范围、timestamp 合理性
- ✅ 业务一致性检测：POST / PUT 不应缺少 body，DELETE 应返回 204/404
- ✅ 异常标签准确性检测：anomaly 须有异常特征（5xx/高延迟/非常规端口）
- ✅ Pandera 集成：声明式 schema 替代手工 (condition, error_message) 元组，规则自文档化

---

## 2. 平台化演进（远期 — 需 Docker）

### 2.1 环境升级路径

```
Windows 10 + Ollama（当前）
    → Windows 11 + Docker Desktop
        → docker-compose: PostgreSQL + Redis + MinIO + app
            → Celery 任务队列 + Prometheus + Grafana
```

### 2.2 核心数据库迁移

- SQLite → PostgreSQL（持久化 + 并发读写）
- 引入 SQLAlchemy ORM（替换原始 SQL）

### 2.3 异步任务队列

- 当前 `asyncio.create_task` → Celery + Redis
- 支持任务持久化、失败重试、优先级

### 2.4 多模型对比 + 回归评估

- 同一场景用 Ollama / 本地模型 / 云端 API 生成，对比质量
- LangSmith Dataset + Evaluator 做回归测试

### 2.5 模板 + Prompt 管理

- 常用行业/场景/异常模式保存为模板
- Prompt 版本化管理，支持 A/B 测试


