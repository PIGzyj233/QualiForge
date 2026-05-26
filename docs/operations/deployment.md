# 部署

QualiForge 私有化部署优先，所有组件通过根 `docker-compose.yml` 编排。

## 1. 服务清单

| 服务 | 镜像 / 构建 | 端口 | 卷 | 健康检查 |
|------|-------------|------|------|----------|
| `postgres` | `${POSTGRES_IMAGE:-postgres:18-alpine}` | `5432` | `postgres_data:/var/lib/postgresql` | `pg_isready` |
| `redis` | `redis:7-alpine` | `6379` | — | `redis-cli ping` |
| `temporal` | `temporalio/temporal:latest`，`server start-dev --ip 0.0.0.0` | `7233` (gRPC) / `8233` (Web UI) | — | `temporal operator cluster health` |
| `backend` | `./backend` 构建 | `8000` | `git_sandbox_data:/data/git-sandbox`、`import_data:/data/imports`、`agent_memory_data:/data/agent-memory` | `urllib /api/health` |
| `worker` | `./backend` 构建，`uv run --no-sync python -m app.worker` | — | 同 backend | — |
| `web` | `./frontend` 构建（nginx） | `5173:80` | — | depends_on backend healthy |

依赖：`backend` 与 `worker` 都 `depends_on postgres/redis/temporal` 健康；`web` 仅依赖 `backend` 健康。

## 2. 卷

- `postgres_data`：业务数据库持久化。
- `git_sandbox_data`：Git bare mirror 与 worktree。
- `import_data`：上传的 Excel/CSV 原始文件与解析产物。
- `agent_memory_data`：Markdown 记忆文件与版本历史。

> 这四个卷构成 QualiForge 的"状态地表"。**备份与迁移必须覆盖全部四个卷 + Postgres dump**。

## 3. 第一次启动

```powershell
Copy-Item .env.example .env
# 至少填 QUALIFORGE_MODEL_GATEWAY_API_KEY，否则 AI 相关功能会失败。
docker compose up --build
```

启动后：

- 工作台：http://localhost:5173
- 后端健康：http://localhost:8000/api/health
- 详细健康：http://localhost:8000/api/health/detailed
- Prometheus：http://localhost:8000/api/metrics
- Temporal Web UI：http://localhost:8233

首个 Workspace 通过登录界面（`/api/auth/login`）创建，默认创建者为 `WorkspaceOwner`。

## 4. 数据策略与凭证安全

- `.env` 不进 git（`.gitignore` 已忽略）。生产环境务必：
  - 自定义 `QUALIFORGE_SECRET_KEY`。
  - 自定义 `POSTGRES_PASSWORD`。
  - 修改默认数据库用户名（不留 `qualiforge/qualiforge`）。
- `QUALIFORGE_MODEL_GATEWAY_API_KEY` 是 LLM 凭证，泄漏即等同账单泄漏。
- GitLab token 在数据库中加密存储（`ai/config.py` 与 `git/gitlab.py` 共用加密），由 `QUALIFORGE_SECRET_KEY` 派生密钥。**轮换 secret key 会导致已存 token 失效**，需要先解密再换。

## 5. 端口暴露建议

私有化部署对外只暴露 `5173 (web)`；其它通过 Compose 内网访问：

- `5432 / 6379 / 7233 / 8233 / 8000` 不应直接暴露到公网。
- 如需远程开发，建议反向代理 `5173 / 8000`，并加自有 auth（当前 `/api/auth/login` 是 scaffolding，不能直接面向公网）。

## 6. 升级流程

1. `git pull`。
2. `docker compose pull` 拉取基础镜像（postgres / redis / temporal / nginx）。
3. `docker compose up --build -d`。
4. 后端首次 import session 会触发 `Base.metadata.create_all` 自动追加新列；若有删除列或破坏性变更，先备份再操作（项目暂无 Alembic）。
5. 验证：`/api/health/detailed` 全部 ok；`docker compose logs backend | grep ERROR`；Temporal Web UI 观察 `qualiforge-agent-runs` 队列。

## 7. Temporal Smoke Test

`scripts/smoke_temporal_compose.py` 用于在 compose 启动后快速验证 Agent 链路：

```powershell
docker compose up -d postgres redis temporal backend
python scripts/smoke_temporal_compose.py
```

脚本会：

1. 通过后端 API 创建一个临时 Workspace / Project。
2. 触发一个 `AgentRun(mode=execute)`。
3. 轮询直到 workflow 完成或超时。
4. 校验 `temporal_workflow_id` 已写回数据库。

CI 之前的快速回归首选这个脚本。

## 8. 备份与恢复

最小可用备份：

1. `docker compose exec postgres pg_dump -U $POSTGRES_USER $POSTGRES_DB > backup.sql`
2. `docker run --rm -v qualiforge_git_sandbox_data:/data -v ${PWD}:/backup alpine tar czf /backup/git_sandbox.tgz -C /data .`
3. 对 `import_data` / `agent_memory_data` 同样打包。

恢复时先恢复卷再 `docker compose up`，让 `create_all` 校验表结构。

## 9. 横向扩展提示（未来）

当前是单实例模型。要扩到多实例需先解决：

- Temporal worker 进程独立部署（现在跟 backend 同进程注册 activity）。
- AI 调用配额与速率限制需 Workspace 级隔离（roadmap §4.3 SaaS 准备项）。
- Postgres 主从 / 备份策略；对象存储从本地卷切换到 S3/MinIO。

详见 `product/roadmap.md` §4.3 与 "技术后续项"。
