import { FolderKanban, History, ShieldCheck, Users } from "lucide-react";
import { NavLink, Outlet, useParams } from "react-router-dom";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";
import { routes } from "../lib/routes";

const tabs = (wid: string) => [
  { to: routes.adminMembers(wid), label: "成员", icon: Users },
  { to: routes.adminProjects(wid), label: "项目", icon: FolderKanban },
  { to: routes.adminAudit(wid), label: "审计", icon: History }
];

export function AdminLayout() {
  const { wid = "" } = useParams<{ wid: string }>();
  const { isOwner, currentMember, busy } = useWorkspaceContext();
  if (!busy && currentMember && !isOwner) {
    return (
      <section className="panel">
        <header className="panel-head">
          <div>
            <ShieldCheck size={20} aria-hidden="true" />
            <h2>无权限</h2>
            <p className="panel-sub">只有 Workspace Owner 可以访问此页面。当前角色：{currentMember.role}</p>
          </div>
        </header>
      </section>
    );
  }
  return (
    <section className="admin-shell">
      <header className="admin-shell-head">
        <div>
          <ShieldCheck size={20} aria-hidden="true" />
          <h2>Workspace 管理</h2>
        </div>
        <p className="panel-sub">仅 Workspace Owner 可在此处管理成员、项目与审计。</p>
      </header>
      <nav className="sub-nav-row" aria-label="管理子导航">
        {tabs(wid).map((tab) => {
          const Icon = tab.icon;
          return (
            <NavLink to={tab.to} key={tab.to} className={({ isActive }) => (isActive ? "sub-nav-button active" : "sub-nav-button")}>
              <Icon size={16} aria-hidden="true" />
              <span>{tab.label}</span>
            </NavLink>
          );
        })}
      </nav>
      <div className="admin-shell-body">
        <Outlet />
      </div>
    </section>
  );
}
