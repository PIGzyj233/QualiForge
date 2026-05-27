import { useEffect } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { Session } from "../api/workspace";
import { WorkspaceProvider, useWorkspaceContext } from "../hooks/useWorkspaceContext";
import { routes } from "../lib/routes";
import { AISuggestionAdmin } from "../views/AISuggestionAdmin";
import { AIConfigAdmin } from "../views/AIConfigAdmin";
import { AgentWorkbenchView } from "../views/AgentWorkbenchView";
import { CaseImportAdmin } from "../views/CaseImportAdmin";
import { DiffAnalysisAdmin } from "../views/DiffAnalysisAdmin";
import { GitLabSandboxAdmin } from "../views/GitLabSandboxAdmin";
import { LibraryView } from "../views/LibraryView";
import { ModuleMappingAdmin } from "../views/ModuleMappingAdmin";
import { ReleaseReportAdmin } from "../views/ReleaseReportAdmin";
import { ReviewQueueView } from "../views/ReviewQueueView";
import { TestPlanAdmin } from "../views/TestPlanAdmin";
import { ProjectOverview } from "../views/project/ProjectOverview";
import { ProjectTeamPanel } from "../views/project/ProjectTeamPanel";
import { WorkbenchOverview } from "../views/workspace/WorkbenchOverview";
import { WorkspaceAuditPanel } from "../views/workspace/WorkspaceAuditPanel";
import { WorkspaceMembersPanel } from "../views/workspace/WorkspaceMembersPanel";
import { WorkspaceProjectsPanel } from "../views/workspace/WorkspaceProjectsPanel";
import { AdminLayout } from "./AdminLayout";
import { ProjectLayout } from "./ProjectLayout";
import { WorkspaceLayout } from "./WorkspaceLayout";

function WorkspaceEntry() {
  const ctx = useWorkspaceContext();
  const navigate = useNavigate();
  useEffect(() => {
    if (!ctx.busy && ctx.currentWorkspace) {
      navigate(routes.workspaceOverview(ctx.currentWorkspace.id), { replace: true });
    }
  }, [ctx.busy, ctx.currentWorkspace?.id, navigate]);
  if (ctx.busy && !ctx.currentWorkspace) {
    return <p className="empty-state">加载 Workspace...</p>;
  }
  if (!ctx.currentWorkspace) {
    return (
      <section className="panel">
        <h2>尚无 Workspace</h2>
        <p>请使用左上角「新建」创建第一个 Workspace。</p>
      </section>
    );
  }
  return null;
}

export function AppRouter({ session, onSignOut }: { session: Session; onSignOut: () => void }) {
  return (
    <WorkspaceProvider session={session}>
      <Routes>
        <Route element={<WorkspaceLayout session={session} onSignOut={onSignOut} />}>
          <Route path="/" element={<WorkspaceEntry />} />
          <Route path="/w/:wid" element={<WorkbenchOverview />} />
          <Route path="/w/:wid/settings" element={<AIConfigAdmin session={session} />} />

          <Route path="/w/:wid/admin" element={<AdminLayout />}>
            <Route index element={<Navigate to="members" replace />} />
            <Route path="members" element={<WorkspaceMembersPanel />} />
            <Route path="projects" element={<WorkspaceProjectsPanel />} />
            <Route path="audit" element={<WorkspaceAuditPanel />} />
          </Route>

          <Route path="/w/:wid/p/:pid" element={<ProjectLayout />}>
            <Route index element={<Navigate to="overview" replace />} />
            <Route path="overview" element={<ProjectOverview />} />
            <Route path="team" element={<ProjectTeamPanel />} />
            <Route path="modules" element={<ModuleMappingAdmin session={session} />} />
            <Route path="repo" element={<GitLabSandboxAdmin session={session} />} />
            <Route path="library/*" element={<LibraryView session={session} />} />
            <Route path="imports" element={<CaseImportAdmin session={session} />} />
            <Route path="reviews" element={<ReviewQueueView session={session} />} />
            <Route path="diffs" element={<DiffAnalysisAdmin session={session} />} />
            <Route path="ai" element={<AISuggestionAdmin session={session} />} />
            <Route path="agent/*" element={<AgentWorkbenchView session={session} />} />
            <Route path="plans" element={<TestPlanAdmin session={session} />} />
            <Route path="reports" element={<ReleaseReportAdmin session={session} />} />
          </Route>
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </WorkspaceProvider>
  );
}
