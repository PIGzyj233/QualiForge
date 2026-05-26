# 本地开发

## 1. 先决条件

- **Python 3.12+**，[`uv`](https://docs.astral.sh/uv/) 包管理器（项目用 `uv` 管 venv、依赖与运行）。
- **Node.js 20+** 与 `npm`。
- **Docker Desktop**（运行 postgres / redis / temporal；不一定要全栈跑 backend 容器）。
- Windows 用户使用 PowerShell；Linux/macOS 命令等价。

## 2. 推荐工作流

最常见姿势：依赖容器 + 本地热重载后端/前端。

```powershell
# 1. 准备 .env
Copy-Item .env.example .env
# 编辑 .env，至少填 QUALIFORGE_MODEL_GATEWAY_API_KEY

# 2. 起依赖
docker compose up -d postgres redis temporal

# 3. 后端
Set-Location backend
uv sync
uv run uvicorn app.main:app --reload    # http://localhost:8000

# 4. 前端（新窗口）
Set-Location frontend
npm install
npm run dev                              # http://localhost:5173
```

`vite.config.ts` 会把 `/api` 代理到 `http://localhost:8000`，无需额外 CORS 设置。

## 3. 全栈容器

需要测试 nginx 打包后的前端、worker 心跳、Temporal 全链路时：

```powershell
docker compose up --build
```

## 4. 后端命令速查

```powershell
Set-Location backend

uv sync                                          # 同步依赖
uv run uvicorn app.main:app --reload             # API 服务
uv run python -m app.worker                      # worker 心跳（独立终端）
uv run pytest tests                              # 全量测试
uv run pytest tests/test_workspaces.py           # 单文件
uv run pytest tests/test_agents.py::test_xxx     # 单测试
uv run pytest -k "diff and analysis" -x          # 关键字 + 失败即停
```

`uv sync` 会创建 `backend/.venv`；如需手动激活：`backend/.venv/Scripts/Activate.ps1`。

## 5. 前端命令速查

```powershell
Set-Location frontend

npm install
npm run dev          # vite dev server :5173
npm run build        # tsc --noEmit (app + node config) + vite build
```

构建产物在 `frontend/dist/`，由 nginx 镜像复制。

## 6. Temporal Smoke Test

`scripts/smoke_temporal_compose.py` 是 Agent 链路的最小回归脚本（依赖 compose 已启动）：

```powershell
python scripts/smoke_temporal_compose.py
```

它会创建临时 Workspace / Project，触发 `AgentRun(mode=execute)`，轮询 workflow 直到完成。

## 7. 截图

`scripts/take_screenshots.py` 自动化生成 `docs/screenshots/` 的演示截图。需要本地起好前后端，并按 README 流程登录种子数据。

## 8. 测试编写要点

- **无共享 fixture**：每个测试自建 `create_app(Settings(...))` + `TestClient`。
- in-memory SQLite + `StaticPool` 保证隔离；Redis URL 用 `db=15` 这种隔离 db。
- Agent 相关测试如需绕开 Temporal，可设置 `agent_execute_sync_mode=True` 让 run 直接在请求中执行。
- 模型调用应通过 `ai/model_gateway.py` 的 stub（参考 `tests/test_model_gateway.py`）；**不要**真打外部 API。

完整后端结构与领域包说明见 `architecture/backend.md`。

## 9. 调试技巧

- `/api/health/detailed`：快速看 DB / Redis / Worker 状态。
- `/api/metrics`：Prometheus 风格指标。
- `/api/dashboard/summary`：MVP 主线进度（hard-coded，作为 12 条主题对照表）。
- Temporal Web UI（`http://localhost:8233`）：workflow 状态、信号、重试、子 workflow 树。
- 后端日志：`docker compose logs -f backend`；本地 `uvicorn` 会直接 stdout。
- 把 `QUALIFORGE_TELEMETRY_TRACE_CONSOLE_ENABLED=true` 打开可在 stdout 看到 trace。

## 10. 常见坑

- **没装数据库驱动**：依赖里有 `psycopg[binary]`，`uv sync` 即可。Windows 环境如果碰到编译问题，确认走的是 binary wheel。
- **Schema 漂移**：没有 Alembic。删除模型字段不会自动 drop column，且老库列还在；演进期建议直接删卷 `docker compose down -v` 重建。
- **Temporal 不连**：`QUALIFORGE_AGENT_EXECUTE_SYNC_MODE=true` 可临时绕开，但只适合调试单个请求路径。
- **`.env` 不生效**：确保从 `backend/` 或仓库根运行（Pydantic 会向上查找）；compose 通过 `env_file` 单独注入。
- **API key 空**：所有 AI 功能都会返回 503-style 错误，请先在 AI 配置面板或 `.env` 中填入。
