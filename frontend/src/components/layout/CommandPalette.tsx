import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Command } from "cmdk";
import {
  Bot, BrainCircuit, ClipboardCheck, FileInput, FileText,
  GitCompareArrows, LayoutDashboard, ListChecks, Network,
  GitBranch, Settings, ShieldCheck, Users
} from "lucide-react";
import { useUIStore } from "@/stores/ui-store";
import { useWorkspaceStore, useCurrentWorkspace, useCurrentProject } from "@/stores/workspace-store";
import { routes } from "@/lib/routes";
import { cn } from "@/lib/utils";

export function CommandPalette() {
  const open = useUIStore((s) => s.commandPaletteOpen);
  const setOpen = useUIStore((s) => s.setCommandPaletteOpen);
  const navigate = useNavigate();
  const ws = useCurrentWorkspace();
  const proj = useCurrentProject();
  const wid = ws?.id ?? "";
  const pid = proj?.id ?? "";

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen(true);
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [setOpen]);

  const go = (path: string) => {
    navigate(path);
    setOpen(false);
  };

  const wsItems = wid
    ? [
        { label: "工作台", icon: LayoutDashboard, path: routes.workspaceOverview(wid) },
        { label: "AI 设置", icon: Settings, path: routes.workspaceSettings(wid) },
        { label: "组织管理", icon: ShieldCheck, path: routes.admin(wid) }
      ]
    : [];

  const projItems =
    wid && pid
      ? [
          { label: "项目首页", icon: LayoutDashboard, path: routes.projectOverview(wid, pid) },
          { label: "用例库", icon: ClipboardCheck, path: routes.projectLibrary(wid, pid) },
          { label: "批量导入", icon: FileInput, path: routes.projectImports(wid, pid) },
          { label: "评审队列", icon: ClipboardCheck, path: routes.projectReviews(wid, pid) },
          { label: "Diff 分析", icon: GitCompareArrows, path: routes.projectDiffs(wid, pid) },
          { label: "AI 智能推荐", icon: BrainCircuit, path: routes.projectAI(wid, pid) },
          { label: "Agent 工作台", icon: Bot, path: routes.projectAgent(wid, pid) },
          { label: "测试计划", icon: ListChecks, path: routes.projectPlans(wid, pid) },
          { label: "发布报告", icon: FileText, path: routes.projectReports(wid, pid) },
          { label: "模块目录", icon: Network, path: routes.projectModules(wid, pid) },
          { label: "代码沙箱", icon: GitBranch, path: routes.projectRepo(wid, pid) },
          { label: "项目团队", icon: Users, path: routes.projectTeam(wid, pid) }
        ]
      : [];

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[20vh]">
      <div className="fixed inset-0 bg-black/40 backdrop-blur-sm" onClick={() => setOpen(false)} />
      <div className="relative w-full max-w-lg rounded-[var(--radius-lg)] border bg-[var(--card)] shadow-2xl overflow-hidden">
        <Command className="[&_[cmdk-input-wrapper]]:border-b [&_[cmdk-input-wrapper]]:border-[var(--border)]">
          <Command.Input
            placeholder="跳转到..."
            className="w-full px-4 py-3 text-sm bg-transparent outline-none placeholder:text-[var(--muted-foreground)]"
            autoFocus
          />
          <Command.List className="max-h-72 overflow-y-auto p-2">
            <Command.Empty className="py-6 text-center text-sm text-[var(--muted-foreground)]">
              无匹配结果
            </Command.Empty>
            {wsItems.length > 0 && (
              <Command.Group heading={<span className="px-2 py-1 text-xs font-semibold text-[var(--muted-foreground)] uppercase tracking-wider">{ws?.name}</span>}>
                {wsItems.map((item) => {
                  const Icon = item.icon;
                  return (
                    <Command.Item
                      key={item.path}
                      onSelect={() => go(item.path)}
                      className={cn(
                        "flex items-center gap-3 px-3 py-2 rounded-[var(--radius-sm)] text-sm cursor-pointer",
                        "aria-selected:bg-[var(--accent)] aria-selected:text-[var(--accent-foreground)]"
                      )}
                    >
                      <Icon size={15} className="text-[var(--muted-foreground)]" />
                      {item.label}
                    </Command.Item>
                  );
                })}
              </Command.Group>
            )}
            {projItems.length > 0 && (
              <Command.Group heading={<span className="px-2 py-1 text-xs font-semibold text-[var(--muted-foreground)] uppercase tracking-wider">{proj?.key} · {proj?.name}</span>}>
                {projItems.map((item) => {
                  const Icon = item.icon;
                  return (
                    <Command.Item
                      key={item.path}
                      onSelect={() => go(item.path)}
                      className={cn(
                        "flex items-center gap-3 px-3 py-2 rounded-[var(--radius-sm)] text-sm cursor-pointer",
                        "aria-selected:bg-[var(--accent)] aria-selected:text-[var(--accent-foreground)]"
                      )}
                    >
                      <Icon size={15} className="text-[var(--muted-foreground)]" />
                      {item.label}
                    </Command.Item>
                  );
                })}
              </Command.Group>
            )}
          </Command.List>
        </Command>
      </div>
    </div>
  );
}
