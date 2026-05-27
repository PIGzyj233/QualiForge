# 系统总览

QualiForge 是一个模块化单体后端 + SPA 前端的私有化部署 SaaS 工作台。所有服务通过 Docker Compose 编排，开发与生产共享同一拓扑。

## 1. 服务拓扑

```
┌───────────────────────────────────────────────────────────────┐
│                         Docker Compose                        │
│                                                               │
│  ┌──────────┐    ┌──────────────────┐    ┌──────────┐         │
│  │   web    │───►│      backend     │◄──►│ postgres │         │
│  │ nginx 80 │    │ FastAPI :8000    │    │   :5432  │         │
│  └──────────┘    │                  │    └──────────┘         │
│                  │                  │    ┌──────────┐         │
│                  │  TestClient app  │◄──►│   redis  │         │
│                  └──────┬───────────┘    │   :6379  │         │
│                         │                └──────────┘         │
│                         │ start_workflow / signal             │
│                         ▼                                     │
│                  ┌──────────────────┐                         │
│                  │     temporal     │                         │
│                  │ start-dev :7233  │                         │
│                  │   web ui :8233   │                         │
│                  └────────▲─────────┘                         │
│                           │ poll task queue                   │
│                           │                                   │
│                  ┌────────┴─────────┐                         │
│                  │      worker      │  (python -m app.worker) │
│                  │  Redis heartbeat │                         │
│                  │  + 未来 job 调度  │                         │
│                  └──────────────────┘                         │
│                                                               │
│  Volumes: postgres_data, git_sandbox_data,                    │
│           import_data, agent_memory_data                      │
└───────────────────────────────────────────────────────────────┘
```

完整 compose 与端口/卷映射见 `operations/deployment.md`。

## 2. 组件职责

| 组件 | 实现 | 责任 |
|------|------|------|
| `web` | `frontend/` Vite + React 18 + TS，构建后由 nginx 提供 | 工作台 UI；开发期 vite 直接代理 `/api` |
| `backend` | `backend/app/` FastAPI + SQLAlchemy 2 + Pydantic v2 | 业务 API、AI 配置、Git Sandbox 命令封装、Agent API |
| `worker` | `backend/app/worker.py` | 当前只写 Redis 心跳；预留未来 Job 调度 |
| `postgres` | `postgres:18-alpine` | 唯一主数据库，存储所有业务、审计、Agent 状态 |
| `redis` | `redis:7-alpine` | 缓存、心跳、未来 job queue |
| `temporal` | `temporalio/temporal:latest` `start-dev` | `AgentRun` 持久执行；任务队列 `qualiforge-agent-runs` |

> Temporal worker 进程当前由后端容器内启动（`agents/temporal.py`）。`docker-compose.yml` 的 `worker` 服务保留心跳职责，未来 Temporal worker 可独立成进程。

## 3. 后端领域分层

`backend/app/` 按领域拆成 7 个包（commit `a2b6d14` 引入），每个包暴露 `router: APIRouter`，在 `main.py::create_app` 中注册：

| 包 | API 前缀 | 主要文件 | 关联领域 |
|----|----------|----------|----------|
| `platform/` | — | `config.py / database.py / health.py / telemetry.py` | 平台基础：Settings、Database wrapper、健康检查、Otel/Prometheus/Langfuse |
| `workspace/` | `/api` | `routes.py` | Workspace、Member、Project、AuditLog；提供共享 helper |
| `ai/` | `/api/workspaces/{wid}` | `config.py / model_gateway.py` | LLMProvider、ModelProfile、AI 数据策略、ModelGateway（OpenAI 兼容） |
| `git/` | `/api/workspaces/{wid}` | `gitlab.py / sandbox.py` | GitLab 接入、Git Sandbox（bare mirror / worktree） |
| `cases/` | `/api/workspaces/{wid}/projects/{pid}` | `modules / imports / reviews / diff_analysis / ai_suggestions / domain` | 模块、映射、用例导入、评审、Diff、AI 建议 |
| `planning/` | `/api/workspaces/{wid}/projects/{pid}` | `test_plans / release_reports` | TestPlan、PlanItem、执行结果、Report |
| `agents/` | `/api/workspaces/{wid}` | `routes / models / temporal / workflows / activities / graph_executor / graph_nodes / ...` | AgentConversation/Run/Message/StagedOutput、Temporal workflow、LangGraph 执行器 |

详细数据流见 `architecture/backend.md`。

## 4. 前端分层

`frontend/src/`：

- `api/`：按领域拆分的后端响应类型与 fetch helper，是前端 API 的单一事实源。
- `App.tsx`：根据 `localStorage` 里的 `qualiforge.session` 渲染 `LoginView` 或 `AppRouter`。
- `routes/AppRouter.tsx`：react-router 路由表，按 `/w/:wid/p/:pid/...` 嵌套 layout。
- `views/`：顶层视图（admin / panel / overview）；其中 `views/workspace/*` 与 `views/project/*` 是工作台分区，其余 `*Admin.tsx` 与各后端 slice 一一对应。
- `components/`：跨视图复用的小部件。
- `hooks/`、`lib/`：Workspace context、导航与路由常量。

详见 `architecture/frontend.md`。

## 5. 跨层数据流（典型 AI 用例生成）

```
1. 前端 AISuggestionAdmin 调用 POST /api/.../ai/suggestions
2. cases/ai_suggestions.py 校验 actor + 数据策略，
   写 AgentRun + AgentToolCall 草案，
   start_agent_run_workflow → Temporal
3. Temporal workflow (agents/workflows.py) 调度 activities
4. activities 在后端进程内执行：
     - graph_executor.py 组装 LangGraph 子图，graph_nodes/ 承载节点实现
     - 通过 graph_tools 调用 git/code_tools / diff_engine / case_imports
     - 走 ai/model_gateway 调 LLM，记录 AIInvocationLog
5. 产出 AgentStagedOutput（人未审）+ 候选用例
6. 前端轮询 /api/.../agent/runs/{id}，渲染时间线与 staged outputs
7. 评审通过后由 cases/reviews.py 落地为正式 TestCase
```

## 6. 部署形态选择

- **本地开发**：后端 `uv run uvicorn`、前端 `npm run dev`，依赖 `docker compose up postgres redis temporal`。
- **全栈本地**：`docker compose up --build`，含 web/backend/worker/postgres/redis/temporal。
- **私有化**：相同 compose 即可，建议外置 PostgreSQL 与对象存储；`QUALIFORGE_*` 环境变量覆盖默认值（见 `operations/configuration.md`）。
- **SaaS**：暂不支持，需补租户隔离、计费、token 加密轮换（roadmap §4.3）。

## 7. 可观测性

- OpenTelemetry trace：`platform/telemetry.py` 提供 `agent_span()`，HTTP 请求中间件自动开 span。
- Prometheus metrics：`/api/metrics` 暴露；`telemetry_prometheus_enabled` 控制。
- Langfuse：可选，通过 `QUALIFORGE_TELEMETRY_LANGFUSE_*` 启用，挂到 ModelGateway。
- 健康检查：`/api/health`（轻量）与 `/api/health/detailed`（检查 DB / Redis / Worker）。

## 8. 安全边界一览

| 边界 | 保护手段 |
|------|----------|
| GitLab token | 数据库加密存储，不在 API 响应中明文返回 |
| Git Sandbox | 路径系统生成，禁止符号链接逃逸，目录级隔离 |
| 仓库操作 | 仅 allowlist 命令（clone/fetch/checkout/diff/show/ls-files/rg），通过 typed 工具暴露给 Agent |
| AI 数据策略 | 任务启动前检查；策略变更走 audit；prompt 仅记录摘要 |
| 评审治理 | 默认不允许自评审；AI 输出不能直接成正式资产 |
| 审计 | `audit()` helper 写 AuditLog；AgentToolCall / AIInvocationLog 分别记录工具与模型调用 |
