import { Navigate, Outlet, useParams } from "react-router-dom";
import { routes } from "@/lib/routes";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useNavigate, useLocation } from "react-router-dom";

export function AdminLayout() {
  const { wid = "" } = useParams<{ wid: string }>();
  const navigate = useNavigate();
  const location = useLocation();

  const tab = location.pathname.includes("/members")
    ? "members"
    : location.pathname.includes("/projects")
    ? "projects"
    : location.pathname.includes("/audit")
    ? "audit"
    : "members";

  return (
    <div className="flex flex-col gap-5">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)] mb-1">组织管理</p>
        <h1 className="text-2xl font-bold font-heading">Workspace 管理</h1>
      </div>
      <Tabs value={tab} onValueChange={(v) => {
        if (v === "members") navigate(routes.adminMembers(wid));
        else if (v === "projects") navigate(routes.adminProjects(wid));
        else if (v === "audit") navigate(routes.adminAudit(wid));
      }}>
        <TabsList>
          <TabsTrigger value="members">成员</TabsTrigger>
          <TabsTrigger value="projects">项目</TabsTrigger>
          <TabsTrigger value="audit">审计日志</TabsTrigger>
        </TabsList>
      </Tabs>
      <Outlet />
    </div>
  );
}
