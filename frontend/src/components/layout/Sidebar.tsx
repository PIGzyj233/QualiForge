import { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import {
  Bot, BrainCircuit, ChevronDown, ChevronLeft, ChevronRight,
  ClipboardCheck, FileInput, FileText, FolderKanban, GitBranch,
  GitCompareArrows, LayoutDashboard, ListChecks, LogOut, Moon,
  Network, Plus, Search, Settings, ShieldCheck, Sun, Users
} from "lucide-react";
import { useUIStore } from "@/stores/ui-store";
import {
  useWorkspaceStore, useCurrentWorkspace, useCurrentProject,
  useIsOwner, switchWorkspace, refreshProjects
} from "@/stores/workspace-store";
import { useSessionStore } from "@/stores/session-store";
import { createWorkspace } from "@/api/workspace";
import { routes } from "@/lib/routes";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

function NavItem({
  to,
  icon: Icon,
  label,
  end,
  collapsed
}: {
  to: string;
  icon: React.ElementType;
  label: string;
  end?: boolean;
  collapsed: boolean;
}) {
  const item = (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        cn(
          "flex items-center gap-2.5 rounded-[var(--radius-sm)] px-2.5 py-2 text-sm font-medium transition-colors",
          "text-[var(--sidebar-foreground)]/70 hover:bg-[var(--sidebar-accent)] hover:text-[var(--sidebar-accent-foreground)]",
          isActive && "bg-[var(--sidebar-accent)] text-[var(--sidebar-accent-foreground)] font-semibold",
          collapsed && "justify-center px-2"
        )
      }
    >
      <Icon size={16} className="shrink-0" aria-hidden="true" />
      {!collapsed && <span className="truncate">{label}</span>}
    </NavLink>
  );

  if (collapsed) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>{item}</TooltipTrigger>
        <TooltipContent side="right">{label}</TooltipContent>
      </Tooltip>
    );
  }
  return item;
}

function NavGroup({
  label,
  icon: Icon,
  children,
  collapsed,
  defaultOpen = true
}: {
  label: string;
  icon: React.ElementType;
  children: React.ReactNode;
  collapsed: boolean;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);

  if (collapsed) {
    return <div className="flex flex-col gap-0.5">{children}</div>;
  }

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger className="flex w-full items-center gap-2 px-2.5 py-1.5 text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors">
        <Icon size={13} className="shrink-0" />
        <span className="flex-1 text-left">{label}</span>
        <ChevronDown size={12} className={cn("transition-transform", open && "rotate-180")} />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="flex flex-col gap-0.5 pl-1">{children}</div>
      </CollapsibleContent>
    </Collapsible>
  );
}

export function Sidebar() {
  const collapsed = useUIStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useUIStore((s) => s.toggleSidebar);
  const theme = useUIStore((s) => s.theme);
  const setTheme = useUIStore((s) => s.setTheme);
  const setCommandPaletteOpen = useUIStore((s) => s.setCommandPaletteOpen);

  const session = useSessionStore((s) => s.session);
  const signOut = useSessionStore((s) => s.signOut);

  const { workspaces, projects, currentWorkspaceId, currentProjectId, busy } = useWorkspaceStore();
  const ws = useCurrentWorkspace();
  const proj = useCurrentProject();
  const isOwner = useIsOwner();
  const navigate = useNavigate();

  const wid = ws?.id ?? "";
  const pid = proj?.id ?? "";

  const [creatingWs, setCreatingWs] = useState(false);
  const [newWsName, setNewWsName] = useState("");
  const [wsCreating, setWsCreating] = useState(false);

  async function handleCreateWorkspace(e: React.FormEvent) {
    e.preventDefault();
    if (!session || !newWsName.trim()) return;
    setWsCreating(true);
    try {
      const created = await createWorkspace({
        name: newWsName.trim(),
        owner_email: session.user.email,
        owner_display_name: session.user.display_name
      });
      useWorkspaceStore.getState().registerWorkspace(created);
      navigate(routes.adminProjects(created.id));
      setCreatingWs(false);
      setNewWsName("");
    } finally {
      setWsCreating(false);
    }
  }

  const isDark = theme === "dark";

  return (
    <aside
      className={cn(
        "flex flex-col h-screen bg-[var(--sidebar)] border-r border-[var(--sidebar-border)] transition-all duration-200",
        collapsed ? "w-16" : "w-64"
      )}
      aria-label="主导航"
    >
      {/* Brand + collapse toggle */}
      <div className={cn("flex items-center h-14 px-3 border-b border-[var(--sidebar-border)]", collapsed ? "justify-center" : "justify-between")}>
        {!collapsed && (
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[var(--radius-sm)] bg-[var(--primary)] text-[var(--primary-foreground)] text-xs font-bold">
              QF
            </div>
            <div className="min-w-0">
              <p className="text-sm font-bold font-heading truncate">QualiForge</p>
              <p className="text-[10px] text-[var(--muted-foreground)] truncate">测试资产工作台</p>
            </div>
          </div>
        )}
        {collapsed && (
          <div className="flex h-8 w-8 items-center justify-center rounded-[var(--radius-sm)] bg-[var(--primary)] text-[var(--primary-foreground)] text-xs font-bold">
            QF
          </div>
        )}
        <Button
          variant="ghost"
          size="icon"
          className={cn("h-7 w-7 shrink-0 text-[var(--muted-foreground)]", collapsed && "mt-0")}
          onClick={toggleSidebar}
          title={collapsed ? "展开侧栏" : "收起侧栏"}
        >
          {collapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
        </Button>
      </div>

      <ScrollArea className="flex-1 min-h-0">
        <div className={cn("flex flex-col gap-4 py-3", collapsed ? "px-2" : "px-3")}>

          {/* Search / Command palette trigger */}
          {!collapsed ? (
            <button
              onClick={() => setCommandPaletteOpen(true)}
              className="flex items-center gap-2 w-full rounded-[var(--radius-sm)] border border-[var(--border)] bg-[var(--muted)] px-3 py-2 text-sm text-[var(--muted-foreground)] hover:bg-[var(--sidebar-accent)] hover:text-[var(--sidebar-accent-foreground)] transition-colors"
            >
              <Search size={14} />
              <span className="flex-1 text-left">搜索或跳转...</span>
              <kbd className="text-[10px] bg-[var(--card)] border border-[var(--border)] rounded px-1.5 py-0.5">⌘K</kbd>
            </button>
          ) : (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="ghost" size="icon" className="h-9 w-9" onClick={() => setCommandPaletteOpen(true)}>
                  <Search size={16} />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right">搜索 (⌘K)</TooltipContent>
            </Tooltip>
          )}

          {/* Workspace switcher */}
          {!collapsed && (
            <div className="flex flex-col gap-1">
              <div className="flex items-center justify-between px-2.5">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">Workspace</span>
                <Button variant="ghost" size="icon" className="h-5 w-5" onClick={() => setCreatingWs((v) => !v)} title="新建 Workspace">
                  <Plus size={12} />
                </Button>
              </div>
              <select
                value={currentWorkspaceId}
                onChange={(e) => {
                  switchWorkspace(e.target.value, session?.user.email ?? "");
                  navigate(routes.workspaceOverview(e.target.value));
                }}
                disabled={busy || workspaces.length === 0}
                className="w-full rounded-[var(--radius-sm)] border border-[var(--border)] bg-[var(--card)] px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--ring)]"
              >
                {workspaces.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
              </select>
              {creatingWs && (
                <form onSubmit={handleCreateWorkspace} className="flex flex-col gap-1.5 mt-1 p-2 rounded-[var(--radius-sm)] border border-[var(--border)] bg-[var(--muted)]">
                  <input
                    value={newWsName}
                    onChange={(e) => setNewWsName(e.target.value)}
                    placeholder="Workspace 名称"
                    autoFocus
                    className="w-full rounded-[var(--radius-sm)] border border-[var(--input)] bg-[var(--card)] px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-[var(--ring)]"
                  />
                  <div className="flex gap-1">
                    <Button type="button" variant="ghost" size="sm" className="flex-1 h-7 text-xs" onClick={() => setCreatingWs(false)}>取消</Button>
                    <Button type="submit" size="sm" className="flex-1 h-7 text-xs" disabled={wsCreating || !newWsName.trim()}>创建</Button>
                  </div>
                </form>
              )}
            </div>
          )}

          <Separator />

          {/* Workspace nav */}
          {wid && (
            <NavGroup label="工作区" icon={LayoutDashboard} collapsed={collapsed}>
              <NavItem to={routes.workspaceOverview(wid)} icon={LayoutDashboard} label="工作台" end collapsed={collapsed} />
              {isOwner && <NavItem to={routes.admin(wid)} icon={ShieldCheck} label="组织管理" collapsed={collapsed} />}
              <NavItem to={routes.workspaceSettings(wid)} icon={Settings} label="AI 设置" collapsed={collapsed} />
            </NavGroup>
          )}

          {/* Project switcher + nav */}
          {wid && projects.length > 0 && (
            <>
              <Separator />
              {!collapsed && (
                <div className="flex flex-col gap-1">
                  <div className="flex items-center px-2.5">
                    <FolderKanban size={13} className="mr-1.5 text-[var(--muted-foreground)]" />
                    <span className="text-[10px] font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">当前项目</span>
                  </div>
                  <select
                    value={currentProjectId}
                    onChange={(e) => {
                      useWorkspaceStore.getState().setCurrentProjectId(e.target.value);
                      navigate(routes.projectOverview(wid, e.target.value));
                    }}
                    disabled={busy || projects.length === 0}
                    className="w-full rounded-[var(--radius-sm)] border border-[var(--border)] bg-[var(--card)] px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--ring)]"
                  >
                    {projects.map((p) => <option key={p.id} value={p.id}>{p.key} · {p.name}</option>)}
                  </select>
                </div>
              )}

              {pid && (
                <>
                  <NavItem to={routes.projectOverview(wid, pid)} icon={LayoutDashboard} label="项目首页" end collapsed={collapsed} />

                  <NavGroup label="用例资产" icon={ClipboardCheck} collapsed={collapsed}>
                    <NavItem to={routes.projectLibrary(wid, pid)} icon={ClipboardCheck} label="用例库" collapsed={collapsed} />
                    <NavItem to={routes.projectImports(wid, pid)} icon={FileInput} label="批量导入" collapsed={collapsed} />
                    <NavItem to={routes.projectReviews(wid, pid)} icon={ClipboardCheck} label="评审队列" collapsed={collapsed} />
                  </NavGroup>

                  <NavGroup label="变更分析" icon={GitCompareArrows} collapsed={collapsed}>
                    <NavItem to={routes.projectRepo(wid, pid)} icon={GitBranch} label="GitLab 仓库" collapsed={collapsed} />
                    <NavItem to={routes.projectDiffs(wid, pid)} icon={GitCompareArrows} label="Diff 分析" collapsed={collapsed} />
                    <NavItem to={routes.projectAI(wid, pid)} icon={BrainCircuit} label="AI 智能推荐" collapsed={collapsed} />
                  </NavGroup>

                  <NavGroup label="发布执行" icon={ListChecks} collapsed={collapsed}>
                    <NavItem to={routes.projectPlans(wid, pid)} icon={ListChecks} label="测试计划" collapsed={collapsed} />
                    <NavItem to={routes.projectReports(wid, pid)} icon={FileText} label="发布报告" collapsed={collapsed} />
                  </NavGroup>

                  <NavGroup label="配置" icon={Settings} collapsed={collapsed} defaultOpen={false}>
                    <NavItem to={routes.projectModules(wid, pid)} icon={Network} label="模块目录" collapsed={collapsed} />
                    <NavItem to={routes.projectTeam(wid, pid)} icon={Users} label="项目团队" collapsed={collapsed} />
                  </NavGroup>

                  <NavItem to={routes.projectAgent(wid, pid)} icon={Bot} label="Agent 工作台" collapsed={collapsed} />
                </>
              )}
            </>
          )}
        </div>
      </ScrollArea>

      {/* Footer: theme toggle + user */}
      <div className={cn("border-t border-[var(--sidebar-border)] p-3 flex flex-col gap-2", collapsed && "items-center")}>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-[var(--muted-foreground)]"
              onClick={() => setTheme(isDark ? "light" : "dark")}
            >
              {isDark ? <Sun size={15} /> : <Moon size={15} />}
            </Button>
          </TooltipTrigger>
          <TooltipContent side={collapsed ? "right" : "top"}>{isDark ? "切换浅色" : "切换深色"}</TooltipContent>
        </Tooltip>

        {!collapsed && session && (
          <div className="flex items-center gap-2 min-w-0">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--primary)]/15 text-[var(--primary)] text-xs font-bold">
              {session.user.display_name.charAt(0).toUpperCase()}
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-semibold truncate">{session.user.display_name}</p>
              <p className="text-[10px] text-[var(--muted-foreground)] truncate">{session.user.email}</p>
            </div>
            <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0 text-[var(--muted-foreground)]" onClick={signOut} title="退出">
              <LogOut size={14} />
            </Button>
          </div>
        )}
      </div>
    </aside>
  );
}
