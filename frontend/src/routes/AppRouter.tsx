import { useEffect } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { useSessionStore } from "@/stores/session-store";
import { routes } from "@/lib/routes";
import { AISuggestionAdmin } from "@/views/AISuggestionAdmin";
import { AIConfigAdmin } from "@/views/AIConfigAdmin";
import { AgentWorkbenchView } from "@/views/AgentWorkbenchView";
import { CaseImportAdmin } from "@/views/CaseImportAdmin";
import { DiffAnalysisAdmin } from "@/views/DiffAnalysisAdmin";
import { GitLabSandboxAdmin } from "@/views/GitLabSandboxAdmin";
import { LibraryView } from "@/views/LibraryView";
import { ModuleMappingAdmin } from "@/views/ModuleMappingAdmin";
import { ReleaseReportAdmin } from "@/views/ReleaseReportAdmin";
import { ReviewQueueView } from "@/views/ReviewQueueView";
import { TestPlanAdmin } from "@/views/TestPlanAdmin";
import { ProjectOverview } from "@/views/project/ProjectOverview";
import { ProjectTeamPanel } from "@/views/project/ProjectTeamPanel";
import { WorkbenchOverview } from "@/views/workspace/WorkbenchOverview";
import { WorkspaceAuditPanel } from "@/views/workspace/WorkspaceAuditPanel";
import { WorkspaceMembersPanel } from "@/views/workspace/WorkspaceMembersPanel";
import { WorkspaceProjectsPanel } from "@/views/workspace/WorkspaceProjectsPanel";
import { AdminLayout } from "./AdminLayout";
import { ProjectLayout } from "./ProjectLayout";
import { WorkspaceLayout } from "./WorkspaceLayout";

function WorkspaceEntry() {
  const { busy, currentWorkspaceId } = useWorkspaceStore();
  const navigate = useNavigate();
  useEffect(() => {
    if (!busy && currentWorkspaceId) {
      navigate(routes.workspaceOverview(currentWorkspaceId), { replace: true });
    }
  }, [busy, currentWorkspaceId, navigate]);
  if (busy && !currentWorkspaceId) return <p className="text-sm text-[var(--muted-foreground)]">加载 Workspace...</p>;
  if (!currentWorkspaceId) return (
    <div className="flex flex-col gap-2">
      <h2 className="text-lg font-bold font-heading">尚无 Workspace</h2>
      <p className="text-sm text-[var(--muted-foreground)]">请使用左侧「新建」创建第一个 Workspace。</p>
    </div>
  );
  return null;
}

export function AppRouter() {
  const session = useSessionStore((s) => s.session);
  if (!session) return null;

  return (
    <Routes>
      <Route element={<WorkspaceLayout />}>
        <Route path="/" element={<WorkspaceEntry />} />
        <Route path="/w/:wid" element={<WorkbenchOverview />} />
        <Route path="/w/:wid/settings" element={<AIConfigAdmin />} />

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
          <Route path="modules" element={<ModuleMappingAdmin />} />
          <Route path="repo" element={<GitLabSandboxAdmin />} />
          <Route path="library/*" element={<LibraryView />} />
          <Route path="imports" element={<CaseImportAdmin />} />
          <Route path="reviews" element={<ReviewQueueView />} />
          <Route path="diffs" element={<DiffAnalysisAdmin />} />
          <Route path="ai" element={<AISuggestionAdmin />} />
          <Route path="agent/*" element={<AgentWorkbenchView />} />
          <Route path="plans" element={<TestPlanAdmin />} />
          <Route path="reports" element={<ReleaseReportAdmin />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
