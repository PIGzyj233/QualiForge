import { Link, useParams } from "react-router-dom";
import { Bot, BrainCircuit, ClipboardCheck, FileText, GitCompareArrows, ListChecks, Network, Users } from "lucide-react";
import { useWorkspaceContext } from "../../hooks/useWorkspaceContext";
import { routes } from "../../lib/routes";

const tiles = (wid: string, pid: string) => [
  { to: routes.projectTeam(wid, pid), title: "项目团队", desc: "查看团队成员、分工与联系方式", Icon: Users },
  { to: routes.projectModules(wid, pid), title: "模块目录", desc: "维护功能模块树、新增子模块、映射代码路径", Icon: Network },
  { to: routes.projectLibrary(wid, pid), title: "用例库", desc: "浏览、搜索、新建结构化测试用例（步骤-预期成对）", Icon: ClipboardCheck },
  { to: routes.projectDiffs(wid, pid), title: "Diff 分析", desc: "代码差异分析，识别受影响模块与风险等级", Icon: GitCompareArrows },
  { to: routes.projectAI(wid, pid), title: "AI 智能推荐", desc: "基于 Diff 生成回归用例与候选用例", Icon: BrainCircuit },
  { to: routes.projectAgent(wid, pid), title: "Agent 工作台", desc: "对话式 Agent，自动生成候选用例", Icon: Bot },
  { to: routes.projectPlans(wid, pid), title: "测试计划", desc: "组织本次发布的执行计划与进度", Icon: ListChecks },
  { to: routes.projectReports(wid, pid), title: "发布报告", desc: "执行结果汇总与发布决策", Icon: FileText }
];

export function ProjectOverview() {
  const { wid = "", pid = "" } = useParams<{ wid: string; pid: string }>();
  const { currentProject } = useWorkspaceContext();

  return (
    <>
      <div className="page-head">
        <div>
          <span className="eyebrow">Project</span>
          <h2>{currentProject?.name ?? "项目首页"}</h2>
          <p>{currentProject?.description || "选择左侧任务进入相应工作面板。"}</p>
        </div>
      </div>
      <div className="overview-grid">
        {tiles(wid, pid).map((tile) => (
          <Link className="overview-tile" to={tile.to} key={tile.to}>
            <tile.Icon size={22} aria-hidden="true" />
            <strong>{tile.title}</strong>
            <span>{tile.desc}</span>
          </Link>
        ))}
      </div>
    </>
  );
}
