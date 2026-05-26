# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Product context

QualiForge is an AI-native test asset workbench for small/mid-sized QA teams. Read `CONTEXT.md` for the domain vocabulary (`Workspace`, `Project`, `Repository`, `Module`/`FeatureArea`, `ModuleMapping`, `TestCase`, `CaseRevision`, `Review`, `DiffAnalysis`, `AICaseCandidate`, `TestPlan`, `PlanItem`, `Job`, `Report`). `docs/product/prd.md` has the full MVP scope; `docs/product/roadmap.md` is explicitly deferred. `docs/README.md` is the documentation index.

Three product invariants govern design decisions:

- **AI never bypasses human review for the formal case library.** AI-generated candidates can run as temporary `PlanItem`s, but they must pass `Review` before being promoted into `TestCase`s.
- **Git access is strictly read-only.** The Git Sandbox clones/mirrors repos for diff analysis. The platform must not run project code, start services, execute arbitrary commands, or touch business databases.
- **Black-box testers shouldn't need to know code paths.** Code-to-feature associations are inferred from `ModuleMapping` rules and surfaced for human confirmation/correction.

## Common commands

Full stack (recommended for end-to-end checks):

```bash
cp .env.example .env
docker compose up --build
# web: http://localhost:5173, api: http://localhost:8000/api/health
```

Backend (Python 3.12, `uv`-managed):

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload      # api on :8000
uv run python -m app.worker                # redis heartbeat worker
uv run pytest tests                        # full suite
uv run pytest tests/test_workspaces.py::test_workspace_owner_can_create_and_switch_workspaces  # single test
```

Frontend (Vite + React 18 + TS):

```bash
cd frontend
npm install
npm run dev          # vite on :5173, proxies /api to localhost:8000
npm run build        # tsc --noEmit on both tsconfigs + vite build
```

There is no linter/formatter wired in either package — don't fabricate one. There is no Alembic migration tool; SQLAlchemy `Base.metadata.create_all` runs lazily on first DB use (see `app/database.py`).

## Backend architecture

The FastAPI app is composed of **domain packages** under `backend/app/` (`platform/`, `workspace/`, `ai/`, `git/`, `cases/`, `planning/`, `agents/`). Each exposes one `router: APIRouter`. `app/main.py::create_app` wires them via `include_router`. Root-level shim files (`app/workspaces.py`, `app/ai_config.py`, etc.) re-export from sub-packages for backwards compatibility — new code should import the sub-package paths directly.

Key shared infrastructure:

- `app/platform/database.py` — `Base = DeclarativeBase` (every package's models inherit it), `Database` wrapper that normalizes `postgresql://` → `postgresql+psycopg://`, lazy `create_all` on first session, and special-cases SQLite (including in-memory `StaticPool` used by tests).
- `app/workspace/routes.py` is the **foundation module**. Other packages import these helpers from it: `audit()` (writes `AuditLog`), `get_workspace_or_404`, `get_project_or_404`, `require_workspace_owner` (raises 403 if actor isn't `WorkspaceOwner`), `now_utc`, `new_id` (uuid4 hex), and the `ActorEmail` query-param alias. Don't duplicate these — import them.
- `app/platform/config.py` — Pydantic settings with `QUALIFORGE_` env prefix. CORS origins come from a comma-separated string. Sandbox/storage paths default to `.qualiforge/...` locally and `/data/...` in Compose. Full reference in `docs/operations/configuration.md`.
- `app/worker.py` — standalone process started via `python -m app.worker`. Currently just writes a Redis heartbeat key every `worker_heartbeat_seconds`; no task queue yet. Long-running agent work runs via Temporal (`agents/temporal.py`, `workflows.py`); other long mutations (git sync, diff analysis) currently run inline using FastAPI `BackgroundTasks`.

Routing conventions:

- Workspace-scoped resources live under `/api/workspaces/{workspace_id}/...`; project-scoped under `/api/workspaces/{workspace_id}/projects/{project_id}/...`. Slice prefixes already encode this — check the `APIRouter(prefix=...)` line before adding a route.
- Mutating endpoints take `actor_email` as a **query parameter** (not a header — the MVP has no real auth). Most call `require_workspace_owner` and emit an `audit(...)` entry in the same transaction.
- `app/main.py` also exposes a stub `/api/auth/login` that returns a fake bearer token (`local-dev-token:<email>`) and a hard-coded `/api/dashboard/summary`. Treat these as scaffolding, not production auth.

Testing pattern (`backend/tests/`):

- `conftest.py` only adds the backend root to `sys.path`. There are no fixtures.
- Tests build an isolated app per test via `create_app(Settings(database_url="sqlite+pysqlite:///:memory:", redis_url="redis://localhost:6379/15"))` and use FastAPI's `TestClient`. Follow this pattern for new tests — don't rely on the module-level `app` for stateful tests.

Full architecture walkthrough lives in `docs/architecture/backend.md`; cross-package data flow and Temporal/LangGraph split in `docs/architecture/overview.md` and `docs/architecture/ai-agent.md`.

## Frontend architecture

Single-page React app in `frontend/src/`, routed by react-router (see `routes/AppRouter.tsx`):

- `api.ts` is the **single source of truth** for backend types and fetch helpers. Every backend response shape is mirrored here. When you change a backend schema, update `api.ts` in the same change.
- `App.tsx` toggles between `LoginView` and `<AppRouter>` based on a `Session` persisted to `localStorage` under `qualiforge.session`.
- `routes/AppRouter.tsx` owns the route table. Layouts: `WorkspaceLayout` (top chrome + sidebar), `AdminLayout` (workspace admin tabs), `ProjectLayout` (project sub-nav).
- Admin views (`views/*Admin.tsx`) are the working surfaces — one per backend slice (`AIConfigAdmin`, `GitLabSandboxAdmin`, `ModuleMappingAdmin`, `CaseImportAdmin`, `DiffAnalysisAdmin`, `AISuggestionAdmin`, `TestPlanAdmin`, `ReleaseReportAdmin`, `AgentWorkbenchView`). Top-level navigational hosts like `LibraryView`, `ReviewQueueView`, and the panels in `views/workspace/*` and `views/project/*` compose those admin components and lighter panels.
- UI copy is **Simplified Chinese** for user-facing strings; identifiers and comments stay English. Match this when adding strings.
- `vite.config.ts` proxies `/api` → `http://localhost:8000` in dev. `VITE_API_URL` overrides the base in `api.ts`.
- No state library, no UI kit, no test runner — keep additions minimal unless asked.

Full route table and views inventory in `docs/architecture/frontend.md`.

## Issue tracking & conventions

- Issues live in GitHub (`PIGzyj233/QualiForge`). Use `gh` CLI. The MVP work plan is twelve issues `#1`–`#12` and they are all marked done in `app/main.py::dashboard_summary` — when you finish a slice that maps to one of them, keep that summary aligned.
- Triage labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix` (see `docs/agents/triage-labels.md`).
- ADRs go in `docs/adr/` (`0001-agent-architecture.md`, `0002-human-confirmed-module-mapping.md`; index at `docs/adr/README.md`).
