# 配置

QualiForge 通过 Pydantic `BaseSettings` 读取配置，env prefix 统一为 `QUALIFORGE_`。
源代码：`backend/app/platform/config.py`。

`.env` 文件自动加载（在仓库根目录或后端运行目录）。Docker Compose 通过 `env_file` 与显式 `environment` 覆盖。

## 1. 基础

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `QUALIFORGE_APP_NAME` | `QualiForge` | 服务名，出现在 OpenAPI / 健康检查中 |
| `QUALIFORGE_ENVIRONMENT` | `local` | 运行环境标识 |
| `QUALIFORGE_SECRET_KEY` | `dev-secret-change-me` | **必须改**：用于加密敏感字段（token） |
| `QUALIFORGE_DATABASE_URL` | `postgresql://qualiforge:qualiforge@localhost:5432/qualiforge` | `postgresql://` 会被自动改写为 `postgresql+psycopg://` |
| `QUALIFORGE_REDIS_URL` | `redis://localhost:6379/0` | Agent Worker heartbeat 与未来 job queue |
| `QUALIFORGE_CORS_ORIGINS` | `http://localhost:5173,http://localhost:3000` | 逗号分隔 |
| `QUALIFORGE_WORKER_HEARTBEAT_SECONDS` | `15` | Agent Worker 写 Redis heartbeat 间隔 |

## 2. Git Sandbox

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `QUALIFORGE_GIT_SANDBOX_ROOT` | `.qualiforge/git-sandbox`（本地）/ `/data/git-sandbox`（compose） | bare mirror + worktree 根目录 |
| `QUALIFORGE_GIT_SYNC_TIMEOUT_SECONDS` | `120` | 同步超时 |
| `QUALIFORGE_GIT_REPO_SIZE_LIMIT_MB` | `1024` | 仓库大小上限 |
| `QUALIFORGE_GIT_DIFF_FILE_LIMIT` | `500` | 单次 diff 文件数上限 |

## 3. 存储

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `QUALIFORGE_IMPORT_STORAGE_ROOT` | `.qualiforge/imports` / `/data/imports` | 上传 Excel/CSV 与解析产物 |
| `QUALIFORGE_EVIDENCE_STORAGE_ROOT` | `.qualiforge/evidence` | 证据附件（截图、log 等） |

## 4. ModelGateway（LLM）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `QUALIFORGE_MODEL_GATEWAY_PROVIDER` | `deepseek` | 标识；当前实现统一走 OpenAI 兼容端点 |
| `QUALIFORGE_MODEL_GATEWAY_API_BASE_URL` | `""`（需填） | 例：`https://api.deepseek.com` |
| `QUALIFORGE_MODEL_GATEWAY_API_KEY` | `""`（需填） | OpenAI 兼容 API key |
| `QUALIFORGE_MODEL_GATEWAY_DEFAULT_MODEL` | `deepseek-v4-pro` | 默认模型 |
| `QUALIFORGE_MODEL_GATEWAY_REASONING_EFFORT` | `high` | 推理强度（仅支持模型生效） |
| `QUALIFORGE_MODEL_GATEWAY_TIMEOUT_SECONDS` | `30` | 单次请求超时 |
| `QUALIFORGE_MODEL_GATEWAY_MAX_ATTEMPTS` | `3` | 失败重试上限 |

> 任何 OpenAI 兼容端点都可（直接 provider、本地 vLLM/Ollama、NewAPI 等网关）。设置 `API_BASE_URL` 指向相应路径即可。

## 5. Temporal

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `QUALIFORGE_TEMPORAL_ADDRESS` | `localhost:7233`（compose 中 `temporal:7233`） | Temporal frontend gRPC |
| `QUALIFORGE_TEMPORAL_NAMESPACE` | `default` | Namespace |
| `QUALIFORGE_AGENT_TASK_QUEUE` | `qualiforge-agent-runs` | Agent Temporal Worker 监听队列 |
| `QUALIFORGE_AGENT_EXECUTE_SYNC_MODE` | `True`（本地）/ `false`（compose） | 同步模式跳过 Temporal，直接在请求中执行（仅用于本地快测） |
| `QUALIFORGE_AGENT_WORKFLOW_TIMEOUT_MINUTES` | `30` | workflow wall-clock |
| `QUALIFORGE_AGENT_ACTIVITY_START_TO_CLOSE_TIMEOUT_MINUTES` | `25` | 单 activity 超时 |
| `QUALIFORGE_AGENT_ACTIVITY_HEARTBEAT_TIMEOUT_SECONDS` | `30` | activity heartbeat |
| `QUALIFORGE_AGENT_ACTIVITY_RETRY_ATTEMPTS` | `3` | activity 重试 |

## 6. Agent 预算（默认值）

运行级预算可以被 Workspace / Project / Run 覆盖。

| 变量 | 默认 | 用途 |
|------|------|------|
| `QUALIFORGE_AGENT_DEFAULT_MAX_TOOL_CALLS` | `60` | 单 run 工具调用上限 |
| `QUALIFORGE_AGENT_DEFAULT_MAX_SUBAGENTS` | `4` | 总子代理数 |
| `QUALIFORGE_AGENT_DEFAULT_MAX_PARALLEL_SUBAGENTS` | `3` | 并行子代理数 |
| `QUALIFORGE_AGENT_DEFAULT_MAX_MODEL_CALLS` | `20` | 模型调用次数 |
| `QUALIFORGE_AGENT_DEFAULT_MAX_CASE_CANDIDATES_PER_RUN` | `30` | 单 run 候选用例数 |
| `QUALIFORGE_AGENT_DEFAULT_MAX_WALL_TIME_MINUTES` | `20` | wall-clock |
| `QUALIFORGE_AGENT_DEFAULT_MAX_TOTAL_SOURCE_CHARS_SENT` | `200000` | 单 run 总源文本字符数 |

## 7. Agent 系统上限（硬天花板）

任何 run 都不能超过这些值。

| 变量 | 默认 |
|------|------|
| `QUALIFORGE_AGENT_SYSTEM_MAX_TOOL_CALLS` | `200` |
| `QUALIFORGE_AGENT_SYSTEM_MAX_SUBAGENTS` | `12` |
| `QUALIFORGE_AGENT_SYSTEM_MAX_PARALLEL_SUBAGENTS` | `6` |
| `QUALIFORGE_AGENT_SYSTEM_MAX_MODEL_CALLS` | `40` |
| `QUALIFORGE_AGENT_SYSTEM_MAX_CASE_CANDIDATES_PER_RUN` | `100` |
| `QUALIFORGE_AGENT_SYSTEM_MAX_WALL_TIME_MINUTES` | `60` |
| `QUALIFORGE_AGENT_SYSTEM_MAX_TOTAL_SOURCE_CHARS_SENT` | `500000` |

## 8. Agent Memory

| 变量 | 默认 |
|------|------|
| `QUALIFORGE_AGENT_MEMORY_ROOT` | `.qualiforge/agent-memory` / `/data/agent-memory` |

## 9. Telemetry

| 变量 | 默认 | 说明 |
|------|------|------|
| `QUALIFORGE_TELEMETRY_SERVICE_NAME` | `qualiforge-backend`（worker 用 `qualiforge-worker`） | OTLP 上报标识 |
| `QUALIFORGE_TELEMETRY_OTLP_ENABLED` | `false` | 启用 OTLP exporter |
| `QUALIFORGE_TELEMETRY_OTLP_ENDPOINT` | `""` | 例：`http://otel-collector:4317` |
| `QUALIFORGE_TELEMETRY_OTLP_HEADERS` | `""` | 形如 `key1=value1,key2=value2` |
| `QUALIFORGE_TELEMETRY_TRACE_CONSOLE_ENABLED` | `false` | 把 trace 打到 stdout（开发调试） |
| `QUALIFORGE_TELEMETRY_PROMETHEUS_ENABLED` | `true` | `/api/metrics` 暴露 |
| `QUALIFORGE_TELEMETRY_LANGFUSE_ENABLED` | `false` | 启用 Langfuse |
| `QUALIFORGE_TELEMETRY_LANGFUSE_HOST` | `""` | Langfuse host URL |
| `QUALIFORGE_TELEMETRY_LANGFUSE_PUBLIC_KEY` | `""` | 公钥 |
| `QUALIFORGE_TELEMETRY_LANGFUSE_SECRET_KEY` | `""` | 私钥 |

## 10. Compose-only 变量

`docker-compose.yml` 还使用以下变量（不进 backend Settings）：

| 变量 | 默认 | 说明 |
|------|------|------|
| `COMPOSE_PROJECT_NAME` | `qualiforge` | 卷与网络前缀 |
| `POSTGRES_IMAGE` | `postgres:18-alpine` | 可指定 mirror |
| `POSTGRES_DB / POSTGRES_USER / POSTGRES_PASSWORD` | `qualiforge` | 数据库初始化 |

## 11. 配置优先级

1. 进程环境变量（包括 compose `environment:`）。
2. `.env` 文件（自动加载）。
3. 代码默认值（`Settings` 字段）。

测试中可以直接构造 `Settings(...)` 覆盖（见 `architecture/backend.md` §7）。

## 12. 前端

前端构建期通过 `VITE_API_URL` 覆盖 API base，默认走同源 / Vite 代理：

```
VITE_API_URL=http://localhost:8000
```

详见 `architecture/frontend.md` §4。
