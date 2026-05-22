from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.ai_config import router as ai_config_router
from app.config import Settings, get_settings
from app.database import Database
from app.gitlab import router as gitlab_router
from app.health import check_redis
from app.workspaces import router as workspace_router


class LoginRequest(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=254)
    display_name: str = Field(min_length=1, max_length=80)
    workspace_name: str = Field(default="QualiForge Lab", min_length=1, max_length=80)


class SessionResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict[str, str]
    workspace: dict[str, str]


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Private MVP workbench API for QualiForge.",
    )
    app.state.settings = settings
    app.state.database = Database(settings.database_url)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/")
    async def root() -> dict[str, str]:
        return {"service": settings.app_name, "docs": "/docs", "health": "/api/health"}

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "backend",
            "environment": settings.environment,
            "checked_at": datetime.now(UTC).isoformat(),
        }

    @app.get("/api/health/detailed")
    async def detailed_health() -> dict[str, object]:
        database, redis = await asyncio.gather(
            asyncio.to_thread(app.state.database.check),
            check_redis(settings),
        )
        service_statuses = [database["status"], redis["status"]]

        return {
            "status": "ok" if all(status == "ok" for status in service_statuses) else "degraded",
            "service": "backend",
            "environment": settings.environment,
            "checked_at": datetime.now(UTC).isoformat(),
            "services": {
                "database": database,
                "redis": redis,
                "worker": {"status": "configured", "detail": "worker service uses Redis for heartbeat and jobs"},
            },
        }

    @app.post("/api/auth/login", response_model=SessionResponse)
    async def login(payload: LoginRequest) -> SessionResponse:
        slug = payload.workspace_name.lower().replace(" ", "-")
        return SessionResponse(
            access_token=f"local-dev-token:{payload.email}",
            user={"email": payload.email, "display_name": payload.display_name, "role": "WorkspaceOwner"},
            workspace={"id": slug, "name": payload.workspace_name},
        )

    @app.get("/api/dashboard/summary")
    async def dashboard_summary() -> dict[str, object]:
        return {
            "workspace": "QualiForge Lab",
            "mvp_stage": "基础平台、Workspace、AI 配置与 Git Sandbox",
            "work_items": [
                {
                    "issue": "#1",
                    "title": "初始化私有化 QualiForge 工作台",
                    "status": "done",
                    "owner": "Platform",
                    "blocked_by": [],
                },
                {
                    "issue": "#2",
                    "title": "创建 Workspace、成员、项目和基础审计",
                    "status": "done",
                    "owner": "Workspace",
                    "blocked_by": ["#1"],
                },
                {
                    "issue": "#3",
                    "title": "配置 LLM Provider、Model Profile 和 AI 数据策略",
                    "status": "done",
                    "owner": "AI Platform",
                    "blocked_by": ["#2"],
                },
                {
                    "issue": "#4",
                    "title": "接入只读 GitLab 仓库与 Git Sandbox",
                    "status": "done",
                    "owner": "Git Sandbox",
                    "blocked_by": ["#2"],
                },
                {
                    "issue": "#5",
                    "title": "维护模块/功能域和 ModuleMapping 规则",
                    "status": "next",
                    "owner": "Module Mapping",
                    "blocked_by": ["#2", "#4"],
                },
                {
                    "issue": "#6",
                    "title": "导入 Excel/CSV 历史用例为可评审草稿",
                    "status": "blocked",
                    "owner": "Case Assets",
                    "blocked_by": ["#2", "#3", "#5"],
                },
                {
                    "issue": "#12",
                    "title": "生成、确认并导出发布测试报告",
                    "status": "blocked",
                    "owner": "Release",
                    "blocked_by": ["#11", "#3"],
                },
            ],
            "queues": [
                {"label": "待评审用例", "value": 0, "trend": "ready after import"},
                {"label": "待执行计划项", "value": 0, "trend": "ready after planning"},
                {"label": "待确认报告", "value": 0, "trend": "ready after execution"},
                {"label": "最近 AI 任务", "value": 0, "trend": "provider not configured"},
            ],
            "recent_jobs": [
                {
                    "type": "system",
                    "status": "succeeded",
                    "summary": "MVP workbench shell bootstrapped",
                    "created_at": datetime.now(UTC).isoformat(),
                }
            ],
        }

    app.include_router(workspace_router)
    app.include_router(ai_config_router)
    app.include_router(gitlab_router)

    return app


app = create_app()
