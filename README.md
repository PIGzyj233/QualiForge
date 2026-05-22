# QualiForge

AI-native test asset workbench for small and mid-sized engineering and QA teams.

## Local MVP Workbench

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Then open:

- Web workbench: http://localhost:5173
- Backend health: http://localhost:8000/api/health
- Detailed health: http://localhost:8000/api/health/detailed

The current implementation covers the first MVP platform slice:

- GitHub issue #1: a private-deployment workbench shell with FastAPI, React, PostgreSQL, Redis, and a background worker service.
- GitHub issue #2: Workspace, member, project, and audit-log foundations with workspace-scoped APIs and UI controls.
- GitHub issue #3: OpenAI-compatible Provider, Model Profile, Workspace AI data policy, and AI invocation summary logging.
- GitHub issue #4: Workspace-owned GitLab token storage, read-only repository binding, background mirror sync jobs, and isolated Git Sandbox paths with size, timeout, and symlink-escape guards.

## Local Development

Backend:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r backend\requirements.txt -r backend\dev-requirements.txt
.\.venv\Scripts\python -m pytest backend\tests
.\.venv\Scripts\python -m uvicorn app.main:app --app-dir backend --reload
```

Useful API paths:

- `GET /api/health/detailed`
- `POST /api/workspaces`
- `GET /api/workspaces?actor_email=owner@qualiforge.local`
- `GET /api/workspaces/{workspace_id}/members`
- `GET /api/workspaces/{workspace_id}/projects`
- `GET /api/workspaces/{workspace_id}/audit-logs`
- `GET /api/workspaces/{workspace_id}/ai-settings`
- `POST /api/workspaces/{workspace_id}/llm-providers`
- `POST /api/workspaces/{workspace_id}/model-profiles`
- `POST /api/workspaces/{workspace_id}/ai-invocations`
- `GET /api/workspaces/{workspace_id}/gitlab-token`
- `PUT /api/workspaces/{workspace_id}/gitlab-token?actor_email=owner@qualiforge.local`
- `GET /api/workspaces/{workspace_id}/repositories`
- `POST /api/workspaces/{workspace_id}/repositories?actor_email=owner@qualiforge.local`
- `POST /api/workspaces/{workspace_id}/repositories/{repository_id}/sync?actor_email=owner@qualiforge.local`
- `GET /api/workspaces/{workspace_id}/jobs`

Frontend:

```powershell
Set-Location frontend
npm install
npm run dev
```
