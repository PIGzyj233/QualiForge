import {
  Bot,
  BrainCircuit,
  ClipboardCheck,
  FileInput,
  FileText,
  GitBranch,
  GitCompareArrows,
  LayoutDashboard,
  ListChecks,
  Network,
  Users
} from "lucide-react";
import { NavLink, Outlet, useParams } from "react-router-dom";
import { routes } from "../lib/routes";

const navItems = (wid: string, pid: string) => [
  { to: routes.projectOverview(wid, pid), label: "项目首页", icon: LayoutDashboard, end: true },
  { to: routes.projectTeam(wid, pid), label: "项目团队", icon: Users },
  { to: routes.projectModules(wid, pid), label: "模块目录", icon: Network },
  { to: routes.projectRepo(wid, pid), label: "代码沙箱", icon: GitBranch },
  { to: routes.projectLibrary(wid, pid), label: "用例库", icon: ClipboardCheck },
  { to: routes.projectImports(wid, pid), label: "批量导入", icon: FileInput },
  { to: routes.projectReviews(wid, pid), label: "评审队列", icon: ClipboardCheck },
  { to: routes.projectDiffs(wid, pid), label: "Diff 分析", icon: GitCompareArrows },
  { to: routes.projectAI(wid, pid), label: "AI 智能推荐", icon: BrainCircuit },
  { to: routes.projectAgent(wid, pid), label: "Agent 工作台", icon: Bot },
  { to: routes.projectPlans(wid, pid), label: "测试计划", icon: ListChecks },
  { to: routes.projectReports(wid, pid), label: "发布报告", icon: FileText }
];

export function ProjectLayout() {
  const { wid = "", pid = "" } = useParams<{ wid: string; pid: string }>();
  return (
    <section className="project-shell">
      <nav className="project-nav" aria-label="项目导航">
        {navItems(wid, pid).map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              to={item.to}
              end={item.end}
              key={item.to}
              className={({ isActive }) => (isActive ? "project-nav-button active" : "project-nav-button")}
            >
              <Icon size={16} aria-hidden="true" />
              <span>{item.label}</span>
            </NavLink>
          );
        })}
      </nav>
      <div className="project-shell-body">
        <Outlet />
      </div>
    </section>
  );
}
