import { useState } from "react";
import type { Session } from "../api";
import { SubTabs } from "../components/SubTabs";
import { DiffAnalysisAdmin } from "./DiffAnalysisAdmin";
import { GitLabSandboxAdmin } from "./GitLabSandboxAdmin";
import { ModuleMappingAdmin } from "./ModuleMappingAdmin";
import { WorkspaceAdmin } from "./WorkspaceAdmin";

const tabs = [
  { key: "projects", label: "项目设置" },
  { key: "members", label: "团队成员" },
  { key: "git", label: "代码沙箱" },
  { key: "modules", label: "模块目录与映射" },
  { key: "diff", label: "Diff 分析" },
  { key: "audit", label: "审计日志" }
] as const;

type ProjectsTab = (typeof tabs)[number]["key"];

export function ProjectsView({ session }: { session: Session }) {
  const [activeTab, setActiveTab] = useState<ProjectsTab>("projects");

  return (
    <div className="view-panel">
      <SubTabs tabs={[...tabs]} active={activeTab} onChange={(key) => setActiveTab(key as ProjectsTab)} />
      <div className="view-panel-body">
        {activeTab === "projects" ? <WorkspaceAdmin session={session} section="projects" /> : null}
        {activeTab === "members" ? <WorkspaceAdmin session={session} section="members" /> : null}
        {activeTab === "git" ? <GitLabSandboxAdmin session={session} /> : null}
        {activeTab === "modules" ? <ModuleMappingAdmin session={session} /> : null}
        {activeTab === "diff" ? <DiffAnalysisAdmin session={session} /> : null}
        {activeTab === "audit" ? <WorkspaceAdmin session={session} section="audit" /> : null}
      </div>
    </div>
  );
}
