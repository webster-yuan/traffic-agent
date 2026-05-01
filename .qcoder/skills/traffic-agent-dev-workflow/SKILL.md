---
name: traffic-agent-dev-workflow
description: |
  Traffic Agent 项目的标准开发工作流：先读文档和代码理解现状，按 karpathy-guidelines 实现（思考先行、简洁优先、外科手术式变更、目标驱动），编写自测代码并在自测通过后才启动前后端做全链路 Chrome 验证，通过后更新文档，获得用户批准后按 git-workflow 提交。适用于所有 Traffic Agent 的功能开发和 bug 修复。
---

# Traffic Agent 开发工作流

## 核心约束

- **回复语言**：始终用中文回复用户。
- **生成数量**：每次生成流量个数 ≤ 5，因为本地 Ollama 模型性能有限。
- **后端启动**：必须在虚拟环境 `.venv` 中启动。
- **不主动推送**：提交后等用户指示再推送。

## 标准流程

按以下步骤执行，每步完成后再进入下一步：

### 1. 阅读理解

阅读项目文档和代码，理解当前状态：
- `to-do.md` — 待办事项和切入点建议
- `ROADMAP.md` — 路线图和阶段状态
- `PROJECT_ANALYSIS.md` — 已知问题列表
- 相关源码文件（`backend/app/`、`frontend/src/`）

### 2. 按 karpathy-guidelines 实现

遵循四条核心原则：

- **思考先行**：先陈述假设，不确定就问。有多种理解时列出来，不自己默默选。
- **简洁优先**：最少代码解决问题，不做过度抽象，不写"以备将来"的代码。
- **外科手术式变更**：只改必须改的，不顺手重构无关代码，不清理已有死代码。
- **目标驱动**：定义可验证的成功标准，循环直到验证通过。

### 3. 自测先行

写完实现代码后，**立即编写自测代码**，然后运行测试：

```bash
cd backend
.\.venv\Scripts\python.exe -m pytest tests\test_xxx.py -v --tb=short
```

自测必须全部通过才能进入下一步。如果失败，修复后重新运行直到通过。

### 4. 全链路 Chrome 验证

自测通过后，启动前后端进行全链路测试：

```bash
# 启动后端（后台运行）
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# 启动前端（后台运行）
cd frontend
npx vite --host 127.0.0.1 --port 5173
```

使用 Browser Agent 进行 Chrome 全链路测试，验证：
- 页面正常加载，新功能 UI 可见
- 操作流程完整（添加 → 执行 → 完成 → 查看结果）
- 无控制台错误
- 历史记录正确更新

如果发现问题，修复代码后重新验证。

### 5. 清理进程和中间文件

全链路测试通过后，**必须**做两件事：

**5.1 终止前后端进程：**

> ⚠️ uvicorn `--reload` 会 fork reloader + worker 两个进程，用 PID 单个杀不掉（reloader 会自动重启 worker），必须按进程名终止全部实例。
> ⚠️ 不要用 `taskkill 2>$null` 链式拼接，PowerShell 的 `2>$null` 在链式命令中会异常吞掉后续 stderr 导致实际上没执行。

```powershell
# 用 PowerShell 原生的 Stop-Process，比 taskkill 可靠得多
Stop-Process -Name python -Force -ErrorAction SilentlyContinue
Stop-Process -Name node -Force -ErrorAction SilentlyContinue
```

终止后验证端口已释放（只看 LISTENING，忽略 TIME_WAIT / CLOSE_WAIT 等 TCP 残留状态）：

```powershell
netstat -ano | Select-String "8000|5173" | Select-String "LISTENING"
# 无输出 = 端口已释放
```

**5.2 删除调试/运行时产生的中间文件：**

全链路测试中 Browser Agent 产生的截图（`*.png`）以及任何临时调试文件，必须在测试结束后立即删除，保持仓库整洁：

```powershell
# 使用 PowerShell Remove-Item，多个文件用逗号分隔（不要用 cmd 的 del，PowerShell 不支持多参数）
Remove-Item -Path *.png -ErrorAction SilentlyContinue
```

> **注意**：本机为 Windows + PowerShell 环境，文件操作优先使用 PowerShell 命令，避免 cmd 兼容问题。
> 其他中间文件类型（如 `.tmp`、`.temp`）如有产生也应一并清理。
> 不要删除 `docs/` 目录下的正式文档图片。

### 6. 更新文档

更新相关文档的状态：
- `ROADMAP.md` — 更新日期、状态标记、实现说明
- `to-do.md` — 更新切入点建议

### 7. 报告并等待批准

向用户汇报：
- 改了哪些文件
- 测试结果
- 全链路验证结果
- 文档更新情况

等待用户明确同意后再提交代码。

### 8. 提交代码

按 git-workflow 规范提交：

```bash
git add <相关文件>
git commit -m "feat(scope): 简洁描述"
```

提交信息格式：`<type>(<scope>): <subject>`

- type: feat / fix / chore / docs / refactor / test
- scope: 功能模块名（如 batch、api、ui）
- subject: 中文简洁描述

用户仓库不涉及协作，可以直接在 main 分支上提交和推送。

## 技巧总结

| 步骤 | 关键动作 | 验证方式 |
|------|---------|---------|
| 1. 阅读 | 读 to-do.md / ROADMAP.md / 源码 | 理解现状 |
| 2. 实现 | 按 karpathy-guidelines 编码 | 代码审查 |
| 3. 自测 | 写测试 → 跑测试 | pytest 全绿 |
| 4. 全链路 | 启动前后端 → Browser Agent | Chrome 验证通过 |
| 5. 清理 | Stop-Process 终止进程树 + 删除中间文件 | 端口释放、仓库整洁 |
| 6. 文档 | 更新 ROADMAP.md / to-do.md | 状态一致 |
| 7. 汇报 | 等用户批准 | 用户同意 |
| 8. 提交 | git commit | 提交成功 |
