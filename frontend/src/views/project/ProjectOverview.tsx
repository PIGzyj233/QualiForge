import { Link, useParams } from "react-router-dom";
import { Bot, BrainCircuit, ClipboardCheck, FileText, GitCompareArrows, ListChecks, Network, Users } from "lucide-react";
import { useCurrentProject } from "@/stores/workspace-store";
import { routes } from "@/lib/routes";

const tiles = (wid: string, pid: string) => [
  { to: routes.projectTeam(wid, pid), title: "项目团队", desc: "查看团队成员、分工与联系方式", Icon: Users },
  { to: routes.projectModules(wid, pid), title: "模块目录", desc: "维护功能模块树、新增子模块、映射代码路径", Icon: Network },
  { to: routes.projectLibrary(wid, pid), title: "用例库", desc: "浏览、搜索、新建结构化测试用例", Icon: ClipboardCheck },
  { to: routes.projectDiffs(wid, pid), title: "Diff 分析", desc: "代码差异分析，识别受影响模块与风险等级", Icon: GitCompareArrows },
  { to: routes.projectAI(wid, pid), title: "AI 智能推荐", desc: "基于 Diff 生成回归用例与候选用例", Icon: BrainCircuit },
  { to: routes.projectAgent(wid, pid), title: "Agent 工作台", desc: "对话式 Agent，自动生成候选用例", Icon: Bot },
  { to: routes.projectPlans(wid, pid), title: "测试计划", desc: "组织本次发布的执行计划与进度", Icon: ListChecks },
  { to: routes.projectReports(wid, pid), title: "发布报告", desc: "执行结果汇总与发布决策", Icon: FileText }
];

export function ProjectOverview() {
  const { wid = "", pid = "" } = useParams<{ wid: string; pid: string }>();
  const proj = useCurrentProject();

  return (
    <div className="flex flex-col gap-5">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)] mb-1">Project</p>
        <h1 className="font-heading text-2xl font-bold">{proj?.name ?? "项目首页"}</h1>
        <p className="mt-1 text-sm text-[var(--muted-foreground)]">{proj?.description || "选择左侧任务进入相应工作面板。"}</p>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {tiles(wid, pid).map((tile) => (
          <Link
            key={tile.to}
            to={tile.to}
            className="flex flex-col gap-2 p-4 rounded-[var(--radius-md)] border bg-[var(--card)] shadow-sm hover:border-[var(--primary)]/40 hover:shadow-md hover:-translate-y-px transition-all"
          >
            <tile.Icon size={20} className="text-[var(--primary)]" />
            <strong className="text-sm font-semibold">{tile.title}</strong>
            <span className="text-xs text-[var(--muted-foreground)] leading-snug">{tile.desc}</span>
          </Link>
        ))}
      </div>
    </div>
  );
}
