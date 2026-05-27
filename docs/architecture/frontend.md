# 前端架构

`frontend/` 是 Vite + React 18 + TypeScript SPA，react-router 驱动；不引入状态管理库、UI 框架、测试运行器。

## 1. 入口与会话

- `main.tsx` → `App.tsx`。
- `App.tsx` 读取 `localStorage["qualiforge.session"]`，未登录渲染 `LoginView`，已登录渲染 `<AppRouter session>`。
- 登出清理 storage 并刷新页面。

## 2. 路由表

`src/routes/AppRouter.tsx` 是路由唯一来源，所有路径通过 `lib/routes.ts` 的常量函数生成：

```
/                                    → 选择/创建 Workspace 后跳转
/w/:wid                              → WorkbenchOverview（工作台总览）
/w/:wid/settings                     → AIConfigAdmin（Workspace 设置）

/w/:wid/admin
  /members                           → WorkspaceMembersPanel
  /projects                          → WorkspaceProjectsPanel
  /audit                             → WorkspaceAuditPanel

/w/:wid/p/:pid
  /overview                          → ProjectOverview
  /team                              → ProjectTeamPanel
  /modules                           → ModuleMappingAdmin
  /repo                              → GitLabSandboxAdmin
  /library/*                         → LibraryView（含子路由）
  /imports                           → CaseImportAdmin
  /reviews                           → ReviewQueueView
  /diffs                             → DiffAnalysisAdmin
  /ai                                → AISuggestionAdmin
  /agent/*                           → AgentWorkbenchView
  /plans                             → TestPlanAdmin
  /reports                           → ReleaseReportAdmin
```

外部分层布局：

- `WorkspaceLayout`：顶部 bar + 左侧 workspace 导航 + outlet。
- `AdminLayout`：workspace 管理面板的二级 tab outlet。
- `ProjectLayout`：项目子导航 + outlet。

`hooks/useWorkspaceContext.tsx` 提供 `<WorkspaceProvider>`，统一管理 workspace 列表 / 当前 workspace / busy 状态。

## 3. 视图组织

`src/views/` 分两类：

### 3.1 `*Admin.tsx`（工作面板）

每个 admin 视图对应一个后端 slice，是测试人员/管理员的主要工作面：

| Admin 视图 | 后端 slice | 主要操作 |
|------------|------------|----------|
| `AIConfigAdmin` | `ai/config.py` | LLM Provider / Model Profile / 数据策略 |
| `GitLabSandboxAdmin` | `git/gitlab.py` | GitLab token、仓库接入、Sandbox 同步 |
| `ModuleMappingAdmin` | `cases/modules.py` | 模块树、映射规则、AI 模块树草稿 |
| `CaseImportAdmin` | `cases/imports.py` | Excel/CSV 上传 + 预览 + 确认 |
| `DiffAnalysisAdmin` | `cases/diff_analysis.py` | tag diff 触发 + 影响面 |
| `AISuggestionAdmin` | `cases/ai_suggestions.py` | AI 候选用例评审 |
| `TestPlanAdmin` | `planning/test_plans.py` | 计划与 PlanItem 管理 |
| `ReleaseReportAdmin` | `planning/release_reports.py` | 报告草稿 → 人工确认 → 导出 |
| `AgentWorkbenchView` | `agents/routes.py` | 会话、运行时间线、staged outputs、审批 |

### 3.2 `*View.tsx` / `views/{workspace,project}/*Panel.tsx`（顶层视图）

- `LibraryView`：用例库浏览与详情。
- `ReviewQueueView`：跨项目评审队列。
- `LoginView`：登录入口。
- `views/workspace/`：`WorkbenchOverview / WorkspaceMembersPanel / WorkspaceProjectsPanel / WorkspaceAuditPanel`。
- `views/project/`：`ProjectOverview / ProjectTeamPanel`。

## 4. API 层

`src/api/` 是**唯一**与后端打交道的目录：

- `client.ts` 统一封装 `requestJson / requestNoContent / requestFormJson` 和 `VITE_API_URL` base URL。
- `workspace.ts / ai.ts / git.ts / planning.ts / agents.ts / cases.ts` 按后端领域包暴露响应类型与 fetch helper。
- `cases.ts` 是 cases 领域的 barrel，内部再拆 `cases.*.ts`，避免单个文件重新膨胀成浅模块。
- 每个端点都有 fetch helper，函数名以 `list / get / create / update / delete / submit / approve / reject ...` 等动词开头。
- 统一附带 `actor_email` query 参数与 `Authorization: Bearer <token>`。
- 通过 `VITE_API_URL` 覆盖 base URL；默认走 vite 代理（dev）或同源（prod）。

> **约定**：后端 schema 变更必须同步改匹配的 `src/api/*` 模块；不允许在视图里就地拼字符串。

## 5. 组件

`src/components/`（按出现频率排序）：

- `StatusPill / StatusTile / CaseStatusBadge / ReviewStatusBadge`：状态徽标。
- `Pagination / SubTabs`：通用列表导航。
- `ProjectSwitcher / WorkspaceSwitcher`：顶部切换。
- `ModuleTree`：模块树渲染（左侧选择 + 右侧编辑器）。
- `CaseDraftEditor / CaseRevisionViewer / StepsEditor`：用例编辑核心组件，`StepsEditor` 实现配对的 操作/预期 步骤编辑（commit `c94f626`）。

## 6. 样式

`src/styles.css`（约 54KB，全局 CSS）。设计风格：

- 工作台密度：紧凑表格、密集状态点、避免大卡片营销感。
- 配色以深色顶栏 + 浅灰内容区为主，状态色用于评审/执行/AI 置信度。
- 文案：用户面向使用简体中文；变量、组件名、注释用英文。

不引入 Tailwind / Styled Components / UI 库。新增样式直接写到 `styles.css` 或视图内 `<style>`，命名走 `qf-<area>-<element>` 约定（已有样式遵循此命名）。

## 7. 构建与开发

```powershell
Set-Location frontend
npm install
npm run dev           # vite :5173，/api 代理到 :8000
npm run build         # tsc --noEmit（main + node）+ vite build
```

- `vite.config.ts`：dev server 与代理；root `tsconfig.json` 是 app 配置，`tsconfig.node.json` 是构建脚本配置。
- 无 eslint / prettier / 单测；不要自己加，除非用户要求。
