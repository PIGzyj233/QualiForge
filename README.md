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
- GitHub issue #5: Project modules/function domains and ModuleMapping rules for directories, files, APIs, services, config keys, database migrations, and keywords.
- GitHub issue #6: CSV/XLSX historical test case import batches with preserved raw files, AI-normalized drafts, preview bulk edits, review submission, and WorkspaceOwner bulk import into the formal case library.
- GitHub issue #7: test case review governance with draft, pending review, approved, rejected, and archived states, revision snapshots, comments, edit requests, approval policy, and configurable self-review/update-review rules.
- GitHub issue #8: tag/ref diff analysis jobs that run in the Git Sandbox and surface impacted modules, risk level, recommended test scope, changed files, structural evidence, and confidence.
- GitHub issue #9: Diff-based AI test suggestions with source evidence, mapping-rule hits, related formal cases, feedback, draft AI case candidates, and temporary or formal PlanItem creation.

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
- `POST /api/workspaces/{workspace_id}/projects/{project_id}/diff-analyses?actor_email=owner@qualiforge.local`
- `GET /api/workspaces/{workspace_id}/projects/{project_id}/diff-analyses`
- `GET /api/workspaces/{workspace_id}/projects/{project_id}/diff-analyses/{analysis_id}`
- `GET /api/workspaces/{workspace_id}/projects/{project_id}/diff-analyses/{analysis_id}/job`
- `POST /api/workspaces/{workspace_id}/projects/{project_id}/diff-analyses/{analysis_id}/ai-suggestions?actor_email=owner@qualiforge.local`
- `GET /api/workspaces/{workspace_id}/projects/{project_id}/diff-analyses/{analysis_id}/ai-suggestions`
- `PATCH /api/workspaces/{workspace_id}/projects/{project_id}/ai-suggestions/{suggestion_id}?actor_email=owner@qualiforge.local`
- `POST /api/workspaces/{workspace_id}/projects/{project_id}/ai-suggestions/{suggestion_id}/candidate?actor_email=owner@qualiforge.local`
- `POST /api/workspaces/{workspace_id}/projects/{project_id}/ai-suggestions/{suggestion_id}/plan-items?actor_email=owner@qualiforge.local`
- `GET /api/workspaces/{workspace_id}/projects/{project_id}/plans`
- `POST /api/workspaces/{workspace_id}/projects/{project_id}/plans?actor_email=owner@qualiforge.local`
- `GET /api/workspaces/{workspace_id}/projects/{project_id}/plans/{plan_id}/items`
- `POST /api/workspaces/{workspace_id}/projects/{project_id}/plans/{plan_id}/items?actor_email=owner@qualiforge.local`
- `GET /api/workspaces/{workspace_id}/projects/{project_id}/modules`
- `POST /api/workspaces/{workspace_id}/projects/{project_id}/modules?actor_email=owner@qualiforge.local`
- `PATCH /api/workspaces/{workspace_id}/projects/{project_id}/modules/{module_id}?actor_email=owner@qualiforge.local`
- `DELETE /api/workspaces/{workspace_id}/projects/{project_id}/modules/{module_id}?actor_email=owner@qualiforge.local`
- `GET /api/workspaces/{workspace_id}/projects/{project_id}/mapping-rules`
- `POST /api/workspaces/{workspace_id}/projects/{project_id}/modules/{module_id}/mapping-rules?actor_email=owner@qualiforge.local`
- `PATCH /api/workspaces/{workspace_id}/projects/{project_id}/modules/{module_id}/mapping-rules/{rule_id}?actor_email=owner@qualiforge.local`
- `DELETE /api/workspaces/{workspace_id}/projects/{project_id}/modules/{module_id}/mapping-rules/{rule_id}?actor_email=owner@qualiforge.local`
- `POST /api/workspaces/{workspace_id}/projects/{project_id}/imports?actor_email=owner@qualiforge.local`
- `GET /api/workspaces/{workspace_id}/projects/{project_id}/imports`
- `GET /api/workspaces/{workspace_id}/projects/{project_id}/imports/{batch_id}/drafts`
- `PATCH /api/workspaces/{workspace_id}/projects/{project_id}/imports/{batch_id}/drafts-bulk?actor_email=owner@qualiforge.local`
- `POST /api/workspaces/{workspace_id}/projects/{project_id}/imports/{batch_id}/submit-review?actor_email=owner@qualiforge.local`
- `POST /api/workspaces/{workspace_id}/projects/{project_id}/imports/{batch_id}/bulk-import?actor_email=owner@qualiforge.local`
- `GET /api/workspaces/{workspace_id}/projects/{project_id}/test-cases`
- `POST /api/workspaces/{workspace_id}/projects/{project_id}/test-cases?actor_email=owner@qualiforge.local`
- `GET /api/workspaces/{workspace_id}/projects/{project_id}/test-cases/{case_id}`
- `PATCH /api/workspaces/{workspace_id}/projects/{project_id}/test-cases/{case_id}?actor_email=owner@qualiforge.local`
- `DELETE /api/workspaces/{workspace_id}/projects/{project_id}/test-cases/{case_id}?actor_email=owner@qualiforge.local`
- `GET /api/workspaces/{workspace_id}/review-settings`
- `PUT /api/workspaces/{workspace_id}/review-settings?actor_email=owner@qualiforge.local`
- `POST /api/workspaces/{workspace_id}/projects/{project_id}/test-cases/{case_id}/submit-review?actor_email=owner@qualiforge.local`
- `POST /api/workspaces/{workspace_id}/projects/{project_id}/test-cases/{case_id}/reviews?actor_email=owner@qualiforge.local`
- `GET /api/workspaces/{workspace_id}/projects/{project_id}/test-cases/{case_id}/reviews`
- `GET /api/workspaces/{workspace_id}/projects/{project_id}/test-cases/{case_id}/revisions`

Frontend:

```powershell
Set-Location frontend
npm install
npm run dev
```
