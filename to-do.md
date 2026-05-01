# Traffic Agent 后续拓展路线

> **更新**: 2026-04-29 — 已完成项移至末尾清单，仅保留可执行的增强建议。

---

## 1. 前端增强（优先）

### 1.1 虚拟滚动 🟡

历史列表全量渲染，记录多后性能下降。引入 `vue-virtual-scroller`。

---

## 2. 后端增强（紧随其后）

### 2.1 RAG 阶段升级 🔴

当前 RAG 是硬编码字典 + `mock_case`。改为加载行业示例 JSON 文件作为 few-shot 提示词，让 LLM 生成更贴合行业特征。

**方案**:
- 为每个行业维护 `data/examples/{industry}.json`，包含 3-5 条典型流量记录
- RAG 节点读取对应文件，写入 `retrieved_cases`
- LLM prompt 中动态注入行业示例

### 2.2 industry 枚举校验 🟡

`TrafficGenerateRequest.industry` 接受任意字符串 → 改为 `Literal` 枚举，前端下拉也联动。

### 2.3 异步 LLM 调用 + 超时 🟡

`generate_records_by_llm()` 使用同步 `llm.invoke()` → 改为 `await llm.ainvoke()` + `asyncio.wait_for(timeout=...)`。当前 Ollama 本地调用不需此优化，但为未来远程 API 做准备。

---

## 3. 数据质量深化（中期）

- 字段合法性检测：IP 格式、端口范围、timestamp 合理性
- 业务一致性检测：POST / 不应该返回空 body，DELETE 应返回特定状态码
- 异常标签准确性检测：fake/anomaly 是否符合其特征描述
- Great Expectations / Pandera 集成：结构化数据质量校验流水线

---

## 4. 平台化演进（远期 — 需 Docker）

### 4.1 环境升级路径

```
Windows 10 + Ollama（当前）
    → Windows 11 + Docker Desktop
        → docker-compose: PostgreSQL + Redis + MinIO + app
            → Celery 任务队列 + Prometheus + Grafana
```

### 4.2 核心数据库迁移

- SQLite → PostgreSQL（持久化 + 并发读写）
- 引入 SQLAlchemy ORM（替换原始 SQL）

### 4.3 异步任务队列

- 当前 `asyncio.create_task` → Celery + Redis
- 支持任务持久化、失败重试、优先级

### 4.4 多模型对比 + 回归评估

- 同一场景用 Ollama / 本地模型 / 云端 API 生成，对比质量
- LangSmith Dataset + Evaluator 做回归测试

### 4.5 模板 + Prompt 管理

- 常用行业/场景/异常模式保存为模板
- Prompt 版本化管理，支持 A/B 测试

---

## 5. 已实现项（备忘）

以下功能已完成，不再列入待办：

| 功能 | 日期 |
|------|------|
| LangGraph 四阶段流水线 | 2026-04 |
| LangSmith Trace 集成 | 2026-04 |
| 阶段时间线 + SSE 流式进度 | 2026-04 |
| 历史高级筛选（7 维度） | 2026-04 |
| 11 行业 + 场景自动推断 | 2026-04 |
| 三维度质量评分 + 扣分说明 | 2026-04 |
| CSV / JSON / Parquet 导出 | 2026-04 |
| HTML 报表 + ECharts 图表 | 2026-04-29 |
| 批量生成（10 任务 + 2s 轮询） | 2026-04-29 |
| Vite 代码分割 | 2026-04-29 |
| asyncio.Semaphore(3) 并发控制 | 2026-04 |
| 任务取消 + 错误重试 | 2026-04 |
| threading.local() 数据库连接 | 2026-04 |
| 定期文件清理 (30 天) | 2026-04 |
| pytest 测试覆盖（14 个） | 2026-04 |
