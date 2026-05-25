import { ArrowUpRight, FolderKanban, LayoutDashboard, LogOut, Settings, ShieldCheck } from "lucide-react";
import { ReactNode } from "react";
import { Link, NavLink, Outlet, useNavigate, useParams } from "react-router-dom";
import { Session } from "../api";
import { ProjectSwitcher } from "../components/ProjectSwitcher";
import { StatusPill } from "../components/StatusPill";
import { WorkspaceSwitcher } from "../components/WorkspaceSwitcher";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";
import { routes } from "../lib/routes";

function WorkspaceNav({ wid, isOwner }: { wid: string; isOwner: boolean }) {
  return (
    <nav className="sidebar-section" aria-label="Workspace 主导航">
      <NavLink to={routes.workspaceOverview(wid)} end className={({ isActive }) => (isActive ? "nav-button active" : "nav-button")}>
        <LayoutDashboard size={18} aria-hidden="true" />
        <span>工作台</span>
      </NavLink>
      {isOwner ? (
        <NavLink to={routes.admin(wid)} className={({ isActive }) => (isActive ? "nav-button active" : "nav-button")}>
          <ShieldCheck size={18} aria-hidden="true" />
          <span>组织管理</span>
        </NavLink>
      ) : null}
      <NavLink to={routes.workspaceSettings(wid)} className={({ isActive }) => (isActive ? "nav-button active" : "nav-button")}>
        <Settings size={18} aria-hidden="true" />
        <span>AI 设置</span>
      </NavLink>
    </nav>
  );
}

export function WorkspaceLayout({
  session,
  onSignOut,
  children
}: {
  session: Session;
  onSignOut: () => void;
  children?: ReactNode;
}) {
  const navigate = useNavigate();
  const params = useParams<{ wid?: string; pid?: string }>();
  const ctx = useWorkspaceContext();
  const wid = params.wid ?? ctx.currentWorkspace?.id ?? "";
  const pid = params.pid ?? ctx.currentProject?.id ?? "";

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="主导航">
        <div className="brand-lockup">
          <div className="brand-icon">QF</div>
          <div>
            <strong>QualiForge</strong>
            <span>测试资产工作台</span>
          </div>
        </div>

        <WorkspaceSwitcher
          workspaces={ctx.workspaces}
          currentWorkspaceId={wid}
          session={session}
          busy={ctx.busy}
          onSwitch={(next) => {
            ctx.selectWorkspace(next);
            navigate(routes.workspaceOverview(next));
          }}
          onCreated={(ws) => {
            ctx.registerWorkspace(ws);
            navigate(routes.adminProjects(ws.id));
          }}
        />

        {wid ? <WorkspaceNav wid={wid} isOwner={ctx.isOwner} /> : null}

        {wid && ctx.projects.length > 0 ? (
          <div className="sidebar-section project-sidebar-section">
            <div className="sidebar-section-title">
              <FolderKanban size={15} aria-hidden="true" />
              <span>当前项目</span>
            </div>
            <ProjectSwitcher
              projects={ctx.projects}
              currentProjectId={pid}
              busy={ctx.busy}
              onSwitch={(next) => {
                ctx.selectProject(next);
                navigate(routes.projectOverview(wid, next));
              }}
            />
            {pid ? (
              <Link className="nav-button subtle" to={routes.projectOverview(wid, pid)}>
                <ArrowUpRight size={16} aria-hidden="true" />
                <span>进入项目工作台</span>
              </Link>
            ) : null}
          </div>
        ) : null}
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div>
            <span className="eyebrow">{ctx.currentWorkspace?.name ?? session.workspace.name}</span>
            <h1>{ctx.currentProject ? `${ctx.currentProject.key} · ${ctx.currentProject.name}` : ctx.currentWorkspace?.name ?? "QualiForge"}</h1>
          </div>
          <div className="topbar-actions">
            <StatusPill status={ctx.error ? "degraded" : "ok"} />
            <span className="user-chip">
              {session.user.display_name} · {session.user.email}
            </span>
            <button className="ghost-button" type="button" onClick={onSignOut}>
              <LogOut size={16} aria-hidden="true" />
              退出
            </button>
          </div>
        </header>
        {ctx.error ? <section className="notice error">{ctx.error}</section> : null}
        {children ?? <Outlet />}
      </main>
    </div>
  );
}
