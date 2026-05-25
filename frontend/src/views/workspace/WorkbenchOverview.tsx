import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertCircle,
  BrainCircuit,
  CheckCircle2,
  ClipboardCheck,
  Database,
  FileInput,
  FileText,
  FolderKanban,
  GitCompareArrows,
  ListChecks,
  RefreshCcw,
  ServerCog
} from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { DashboardSummary, getDashboardSummary, getHealth, HealthPayload } from "../../api";
import { Pagination } from "../../components/Pagination";
import { StatusPill } from "../../components/StatusPill";
import { usePagination } from "../../hooks/usePagination";
import { useWorkspaceContext } from "../../hooks/useWorkspaceContext";
import { statusLabel } from "../../lib/labels";
import { routes } from "../../lib/routes";

const queueTrendLabel: Record<string, string> = {
  "ready after import": "导入后进入评审",
  "ready after planning": "计划创建后开始执行",
  "ready after execution": "执行完成后生成报告",
  "provider not configured": "尚未配置模型服务"
};

const serviceNameLabel: Record<string, string> = {
  database: "Database",
  redis: "Redis",
  worker: "Worker"
};

const serviceDetailLabel: Record<string, string> = {
  local: "本地环境",
  reachable: "连接正常",
  "worker service uses Redis for heartbeat and jobs": "使用 Redis 维护心跳与任务"
};

const jobTypeLabel: Record<string, string> = {
  system: "系统"
};

export function WorkbenchOverview() {
  const { wid: routeWid } = useParams<{ wid: string }>();
  const ctx = useWorkspaceContext();
  const [health, setHealth] = useState<HealthPayload | null>(null);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const [nextHealth, nextSummary] = await Promise.all([getHealth(), getDashboardSummary()]);
      setHealth(nextHealth);
      setSummary(nextSummary);
    } catch (err) {
      setError(err instanceof Error ? err.message : "工作台数据加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  const services = useMemo(() => {
    if (!health) return [];
    return Object.entries(health.services).map(([name, service]) => ({ name, ...service }));
  }, [health]);

  const wid = routeWid ?? ctx.currentWorkspace?.id ?? "";
  const selectedProject = ctx.currentProject;
  const pid = selectedProject?.id ?? "";
  const workItems = summary?.work_items ?? [];
  const recentJobs = summary?.recent_jobs ?? [];
  const workItemsPagination = usePagination(workItems, 8);
  const jobsPagination = usePagination(recentJobs, 6);
  const completedWorkItems = workItems.filter((item) => item.status === "done").length;
  const openQueueCount = (summary?.queues ?? []).reduce((total, queue) => total + queue.value, 0);
  const serviceRows = [
    {
      label: "Backend API",
      status: health?.status ?? (loading ? "checking" : "degraded"),
      detail: serviceDetailLabel[health?.environment ?? "local"] ?? health?.environment ?? "本地环境"
    },
    ...services.map((service) => ({
      label: serviceNameLabel[service.name] ?? service.name,
      status: service.status,
      detail: serviceDetailLabel[service.detail] ?? service.detail
    }))
  ];
  const degradedServices = serviceRows.filter((service) => !["ok", "reachable", "succeeded"].includes(service.status)).length;
  const projectActions = pid
    ? [
        {
          to: routes.projectImports(wid, pid),
          title: "导入用例",
          desc: "清洗 Excel/CSV 历史资产，提交为可评审草稿。",
          meta: "资产准备",
          Icon: FileInput
        },
        {
          to: routes.projectReviews(wid, pid),
          title: "评审队列",
          desc: "处理待评审草稿，沉淀为正式用例库。",
          meta: "质量治理",
          Icon: ClipboardCheck
        },
        {
          to: routes.projectDiffs(wid, pid),
          title: "Diff 分析",
          desc: "按分支或 tag 识别变更影响和风险模块。",
          meta: "变更评估",
          Icon: GitCompareArrows
        },
        {
          to: routes.projectAI(wid, pid),
          title: "AI 建议",
          desc: "基于变更与历史用例生成回归建议。",
          meta: "智能辅助",
          Icon: BrainCircuit
        },
        {
          to: routes.projectPlans(wid, pid),
          title: "测试计划",
          desc: "组织发布范围、执行项、负责人和证据。",
          meta: "发布执行",
          Icon: ListChecks
        },
        {
          to: routes.projectReports(wid, pid),
          title: "发布报告",
          desc: "汇总执行结果，确认发布建议与结论。",
          meta: "决策输出",
          Icon: FileText
        }
      ]
    : [
        {
          to: wid ? routes.adminProjects(wid) : "/",
          title: "创建第一个项目",
          desc: "先建立项目，之后就可以导入用例、分析变更和编排测试计划。",
          meta: "开始配置",
          Icon: FolderKanban
        }
      ];

  return (
    <>
      <div className="page-head workspace-page-head">
        <div>
          <span className="eyebrow">Workspace 总览</span>
          <h2>我的工作台</h2>
          <p>围绕当前项目，把用例资产、评审、变更分析和发布执行放在一个入口里。</p>
        </div>
        <button className="icon-button" type="button" onClick={() => void refresh()} title="刷新状态">
          <RefreshCcw size={18} aria-hidden="true" />
        </button>
      </div>
      {error ? (
        <section className="notice error">
          <AlertCircle size={18} aria-hidden="true" />
          <span>{error}</span>
        </section>
      ) : null}
      <section className="dashboard-hero" aria-label="当前项目">
        <div>
          <span className="eyebrow">当前项目</span>
          <h2>{selectedProject ? `${selectedProject.key} · ${selectedProject.name}` : "尚未选择项目"}</h2>
          <p>
            {selectedProject?.description ||
              "选择一个项目后，可以从这里进入日常测试资产管理、变更影响分析和发布测试协作。"}
          </p>
        </div>
        <div className="dashboard-hero-actions">
          {pid ? (
            <>
              <Link className="primary-button" to={routes.projectLibrary(wid, pid)}>
                进入用例库
              </Link>
              <Link className="ghost-button" to={routes.projectOverview(wid, pid)}>
                项目首页
              </Link>
            </>
          ) : (
            <Link className="primary-button" to={wid ? routes.adminProjects(wid) : "/"}>
              创建项目
            </Link>
          )}
        </div>
      </section>
      <section className="workbench-layout">
        <div className="main-column">
          <section className="action-grid" aria-label="常用工作入口">
            {projectActions.map((action) => {
              const Icon = action.Icon;
              return (
                <Link className="action-card" to={action.to} key={action.title}>
                  <Icon size={22} aria-hidden="true" />
                  <span>{action.meta}</span>
                  <strong>{action.title}</strong>
                  <small>{action.desc}</small>
                </Link>
              );
            })}
          </section>
          <section className="section-block">
            <div className="section-heading">
              <div>
                <span className="eyebrow">流程进度</span>
                <h2>平台能力准备</h2>
              </div>
              <Activity size={20} aria-hidden="true" />
            </div>
            <div className="progress-strip">
              <strong>
                {completedWorkItems}/{workItems.length || 0}
              </strong>
              <span>{summary?.mvp_stage ?? "基础平台能力"}</span>
            </div>
            <div className="issue-table" role="table" aria-label="MVP issue 队列">
              <div className="issue-row issue-head" role="row">
                <span>Issue</span>
                <span>标题</span>
                <span>Owner</span>
                <span>状态</span>
              </div>
              {workItemsPagination.currentItems.map((item) => (
                <div className="issue-row" role="row" key={item.issue}>
                  <span className="issue-id">{item.issue}</span>
                  <span className="issue-title">{item.title}</span>
                  <span className="issue-owner">{item.owner}</span>
                  <StatusPill status={item.status} />
                </div>
              ))}
              {workItems.length === 0 ? <p className="empty-state">暂无工作项</p> : null}
            </div>
            <Pagination
              currentPage={workItemsPagination.currentPage}
              totalPages={workItemsPagination.totalPages}
              totalItems={workItemsPagination.totalItems}
              onPageChange={workItemsPagination.goToPage}
              itemsPerPage={8}
            />
          </section>
          <section className="section-block">
            <div className="section-heading">
              <div>
                <span className="eyebrow">Jobs</span>
                <h2>最近任务</h2>
              </div>
              <Database size={20} aria-hidden="true" />
            </div>
            <div className="job-list">
              {jobsPagination.currentItems.map((job) => (
                <div className="job-row" key={`${job.type}-${job.created_at}`}>
                  <CheckCircle2 size={18} aria-hidden="true" />
                  <div>
                    <strong>{job.summary}</strong>
                    <span>
                      {jobTypeLabel[job.type] ?? job.type} · {statusLabel[job.status] ?? job.status}
                    </span>
                  </div>
                </div>
              ))}
              {recentJobs.length === 0 ? <p className="empty-state">暂无任务记录</p> : null}
            </div>
            <Pagination
              currentPage={jobsPagination.currentPage}
              totalPages={jobsPagination.totalPages}
              totalItems={jobsPagination.totalItems}
              onPageChange={jobsPagination.goToPage}
              itemsPerPage={6}
            />
          </section>
        </div>
        <aside className="side-column" aria-label="待办概览">
          <section className="summary-panel">
            <div className="summary-panel-head">
              <div>
                <span className="eyebrow">待处理</span>
                <h3>协作队列</h3>
              </div>
              <strong>{openQueueCount}</strong>
            </div>
            <div className="queue-list">
              {(summary?.queues ?? []).map((queue) => (
                <div className="queue-row" key={queue.label}>
                  <div>
                    <strong>{queue.label}</strong>
                    <span>{queueTrendLabel[queue.trend] ?? queue.trend}</span>
                  </div>
                  <b>{queue.value}</b>
                </div>
              ))}
            </div>
          </section>
          <section className="summary-panel">
            <div className="summary-panel-head">
              <div>
                <span className="eyebrow">系统状态</span>
                <h3>服务可用性</h3>
              </div>
              <ServerCog size={20} aria-hidden="true" />
            </div>
            <div className="service-list">
              {serviceRows.map((service) => (
                <div className="service-row" key={service.label}>
                  <div>
                    <strong>{service.label}</strong>
                    <span>{service.detail}</span>
                  </div>
                  <StatusPill status={service.status} />
                </div>
              ))}
            </div>
            <p className={degradedServices > 0 ? "summary-note warning" : "summary-note"}>
              {degradedServices > 0 ? `${degradedServices} 个服务需要关注` : "全部核心服务可用"}
            </p>
          </section>
        </aside>
      </section>
    </>
  );
}
