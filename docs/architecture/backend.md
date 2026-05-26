# 后端架构

`backend/app/` 是 FastAPI + SQLAlchemy 2 + Pydantic v2 的模块化单体。本文档描述实际现状（commit `a2b6d14` 后的 7 个领域包），与代码 1:1 对齐。

## 1. 顶层组装

`app/main.py::create_app(settings)`：

- 读取 `Settings`，初始化 telemetry 与 `Database`。
- 注册 CORS 中间件与 `agent_span` HTTP 中间件。
- 暴露根级端点：
  - `GET /` → 服务自描述。
  - `GET /api/health`、`GET /api/health/detailed`。
  - `GET /api/metrics`（Prometheus）。
  - `POST /api/auth/login`：MVP scaffolding，返回 `local-dev-token:<email>` 假 token。
  - `GET /api/dashboard/summary`：工作台 hard-coded 12 条主线状态。
- 按顺序 `include_router`：workspace → ai_config → gitlab → modules → case_imports → case_reviews → diff_analysis → test_plans → ai_suggestions → release_reports → agents。

> `app/workspaces.py / app/ai_config.py / app/case_imports.py / ...` 这些根级文件是**兼容 shim**，把 import 重定向到子包（例如 `app.workspaces` → `app.workspace.routes`）。新代码请直接 import 子包路径。

## 2. 共享基础设施

### 2.1 `platform/database.py`

- `Base = DeclarativeBase`：所有 ORM 模型继承。
- `Database`：包装 `engine + sessionmaker`，自动把 `postgresql://` 改写为 `postgresql+psycopg://`，SQLite（含 in-memory `StaticPool`）单独处理。
- 首次拿 session 时执行 `Base.metadata.create_all`，**没有 Alembic 迁移**——所有 schema 变更必须保证可由 `create_all` 重建。

### 2.2 `platform/config.py`

`Settings(BaseSettings)`，env prefix `QUALIFORGE_`，`.env` 自动加载。完整字段见 `operations/configuration.md`。

`get_settings()` 是 `@lru_cache` 单例，测试通过显式传入 `Settings(...)` 覆盖。

### 2.3 `platform/telemetry.py`

- `configure_telemetry(settings)`：可选启用 OTLP exporter、console exporter、Langfuse。
- `agent_span(name, **attrs)` 上下文管理器：业务代码与 Agent 工具共用。
- `prometheus_response()`：`/api/metrics` 的渲染。

### 2.4 `platform/health.py`

`check_redis(settings)`：返回 `{status, detail}`，供详细健康检查并发执行。

### 2.5 `workspace/routes.py` 共享 helper

其他 slice **必须** import 这些 helper，不要自己重复：

- `audit(db, *, workspace_id, actor_email, action, entity_type, entity_id, before=None, after=None, ...)`：写 `AuditLog`。
- `get_workspace_or_404(db, workspace_id)`、`get_project_or_404(db, project_id)`。
- `require_workspace_owner(db, workspace_id, actor_email)`：非 owner 抛 403。
- `now_utc()`、`new_id()`（uuid4 hex）。
- `ActorEmail`：FastAPI `Query` 别名，约定 `actor_email` 走查询参数。

## 3. 领域包

每个包暴露一个 `router: APIRouter`，命名约定与前缀如下：

| 包 / 文件 | 前缀 | tag | 主要职责 |
|-----------|------|-----|----------|
| `workspace/routes.py` | `/api` | `workspaces` | Workspace / Member / Project / AuditLog 查询 |
| `ai/config.py` | `/api/workspaces/{wid}` | `ai-config` | LLMProvider、ModelProfile、AI 数据策略 |
| `git/gitlab.py` | `/api/workspaces/{wid}` | `gitlab` | GitLab token、Repository 接入、Sandbox 同步 |
| `cases/modules.py` | `/api/workspaces/{wid}/projects/{pid}` | `modules` | ProjectModule、ModuleMappingRule、AI 模块树草稿 |
| `cases/imports.py` | `/api/workspaces/{wid}/projects/{pid}` | `case-imports` | Excel/CSV 上传、AI 整理、批量确认 |
| `cases/reviews.py` | `/api/workspaces/{wid}` | `case-reviews` | TestCase / CaseRevision / Review 流转 |
| `cases/diff_analysis.py` | `/api/workspaces/{wid}/projects/{pid}` | `diff-analysis` | tag diff 任务、结果存储 |
| `cases/ai_suggestions.py` | `/api/workspaces/{wid}/projects/{pid}` | `ai-suggestions` | AI 候选用例生成 / 接受 / 忽略 |
| `planning/test_plans.py` | `/api/workspaces/{wid}/projects/{pid}` | `test-plans` | TestPlan、PlanItem、执行结果 |
| `planning/release_reports.py` | `/api/workspaces/{wid}/projects/{pid}` | `release-reports` | Report 草稿 / 确认 / 导出 |
| `agents/routes.py` | `/api/workspaces/{wid}` | `agents` | AgentConversation / Run / Message / StagedOutput |

### 3.1 cases 子包内部分层

`cases/` 因为体量大，进一步拆出领域工具模块（不直接挂路由）：

- `domain.py / step_models.py`：核心 `TestCase / CaseRevision / TestStep` 模型与序列化。
- `import_models.py / import_support.py`：导入批次的数据模型与 Excel/CSV 解析。
- `review_models.py / review_workflow.py`：评审状态机与持久化。
- `diff_models.py / diff_engine.py`：Diff 任务模型与执行引擎（24KB）。
- `modules.py`：模块树、`MappingRuleType/Relationship/Status/Source` 五个枚举、AI 模块树草稿对接 Temporal。
- `ai_suggestions.py`：AI 建议路由（62KB，含 staged output 流转）。

### 3.2 agents 子包内部分层

`agents/`：

- `models.py`：ORM 模型 `AgentConversation / AgentRun / AgentMessage / AgentToolCall / AgentApproval / AgentStagedOutput`，以及 `AgentConversationStatus / AgentRunMode / AgentRunStatus / AgentMessageRole / AgentStagedOutputStatus` 枚举。
- `schemas.py / serializers.py`：Pydantic schema 与 ORM ↔ schema 映射。
- `routes.py`：HTTP 入口（会话、消息、运行、staged outputs、approvals）。
- `temporal.py`：Temporal client + `start_agent_run_workflow`、`AgentTemporalUnavailable` 异常。
- `workflows.py`：Temporal workflow 定义（取消信号、活动调度、重试策略）。
- `activities.py`：Temporal activities（执行 LangGraph、持久化中间结果、写 AgentToolCall）。
- `graph_executor.py`（98KB）：LangGraph 主执行器，承载多种 specialized graph。
- `graph_*.py`：分析图、预算、策略、结果聚合、工具表、运行器、类型定义。
- `budget.py`：默认/系统/运行级预算。
- `memory.py`：Markdown 记忆文件存取与版本。
- `coverage.py`：CoverageIndex 索引。
- `repository.py / state.py`：状态机辅助。

## 4. 路由与权限约定

- **写接口 `actor_email` 走 query**（无真实 auth，MVP 假设可信网络）。
- 写接口几乎都调用 `require_workspace_owner` 或类似 guard，并在同一事务里 `audit(...)`。
- 资源 ID 用 `new_id()` 生成的 32 位 hex，所有 PK/外键统一使用 `String(32)`。
- 时间字段统一 UTC（`now_utc()`），列类型 `DateTime(timezone=True)`。

## 5. 后台任务

当前两种后台路径：

1. **Temporal workflow**：仅 `AgentRun` 使用。`start_agent_run_workflow` 把 workflow id 写回 `AgentRun.temporal_workflow_id`；workflow 通过 signal 接受取消/暂停。
2. **FastAPI BackgroundTasks**：其他长任务（Git 同步、Diff 分析、批量导入）以请求内 background task 兜底；后续如需更强 durability 应迁移到 Temporal 或独立 worker。

`app/worker.py` 是独立进程（`python -m app.worker`），目前只往 Redis 写 `worker:heartbeat` key，间隔 `worker_heartbeat_seconds`。

## 6. ModelGateway

`ai/model_gateway.py` 是 LLM 调用的唯一入口：

- v1 走 OpenAI 兼容 chat completions（默认 DeepSeek，可指向任何兼容端点）。
- 自动写 `AIInvocationLog`（输入摘要、token、缓存命中、成本、失败原因）。
- 按用途（导入清洗 / Diff 分析 / 用例生成 / 报告 / Agent）选 model profile。
- 失败重试上限由 `model_gateway_max_attempts`（默认 3）。
- Telemetry：每次调用开 `agent_span("model.invoke", ...)`，Langfuse 可选。

Agent 与业务代码都**不应直接** `from openai import ...`，必须经过 `ModelGateway`。

## 7. 测试约定

`backend/tests/`：

- `conftest.py` 只把 `backend/` 加入 `sys.path`，**没有 fixture**。
- 每个测试自建 app：

```python
from app.main import create_app
from app.platform.config import Settings

app = create_app(Settings(
    database_url="sqlite+pysqlite:///:memory:",
    redis_url="redis://localhost:6379/15",
))
client = TestClient(app)
```

- 跨测试**禁止**共享 `app/database`；in-memory SQLite + `StaticPool` 保证隔离。
- 当前测试 19 个文件，覆盖每个 slice 主流程 + Temporal 集成 + 模型网关。

运行：

```powershell
cd backend
uv run pytest tests
uv run pytest tests/test_workspaces.py::test_workspace_owner_can_create_and_switch_workspaces
```

## 8. 没有 lint / 格式化 / 迁移

- 后端不带 ruff/black/mypy 配置；前端不带 eslint/prettier。**不要自己加，除非用户明确要求**。
- 没有 Alembic：schema 变更只能通过模型字段加默认值 + `create_all` 重建。
- 没有 CI workflow（commit 历史也未见）。本地 `uv run pytest tests` 是唯一回归手段。
