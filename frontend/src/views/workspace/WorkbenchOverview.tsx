import { useEffect, useMemo, useState } from "react";
import {
  Activity, AlertCircle, BrainCircuit, CheckCircle2, ClipboardCheck,
  Database, FileInput, FileText, FolderKanban, GitCompareArrows,
  ListChecks, RefreshCcw, ServerCog
} from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { type DashboardSummary, getDashboardSummary, getHealth, type HealthPayload } from "@/api/workspace";
import { Pagination } from "@/components/Pagination";
import { StatusPill } from "@/components/StatusPill";
import { usePagination } from "@/hooks/usePagination";
import { useCurrentWorkspace, useCurrentProject } from "@/stores/workspace-store";
import { statusLabel } from "@/lib/labels";
import { routes } from "@/lib/routes";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";

const queueTrendLabel: Record<string, string> = {
  "ready after import": "导入后进入评审",
  "ready after planning": "计划创建后开始执行",
  "ready after execution": "执行完成后生成报告",
  "provider not configured": "尚未配置模型服务"
};

const serviceNameLabel: Record<string, string> = {
  database: "Database", redis: "Redis", worker: "Worker"
};

const serviceDetailLabel: Record<string, string> = {
  local: "本地环境", reachable: "连接正常",
  "worker service uses Redis for heartbeat and jobs": "使用 Redis 维护心跳与任务"
};

const jobTypeLabel: Record<string, string> = { system: "系统" };

export function WorkbenchOverview() {
  const { wid: routeWid } = useParams<{ wid: string }>();
  const ws = useCurrentWorkspace();
  const proj = useCurrentProject();
  const [health, setHealth] = useState<HealthPayload | null>(null);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setLoading(true); setError(null);
    try {
      const [h, s] = await Promise.all([getHealth(), getDashboardSummary()]);
      setHealth(h); setSummary(s);
    } catch (err) {
      setError(err instanceof Error ? err.message : "工作台数据加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void refresh(); }, []);

  const services = useMemo(() => health ? Object.entries(health.services).map(([name, s]) => ({ name, ...s })) : [], [health]);
  const wid = routeWid ?? ws?.id ?? "";
  const pid = proj?.id ?? "";
  const workItems = summary?.work_items ?? [];
  const recentJobs = summary?.recent_jobs ?? [];
  const workItemsPagination = usePagination(workItems, 8);
  const jobsPagination = usePagination(recentJobs, 6);
  const completedWorkItems = workItems.filter((i) => i.status === "done").length;
  const openQueueCount = (summary?.queues ?? []).reduce((t, q) => t + q.value, 0);

  const serviceRows = [
    { label: "Backend API", status: health?.status ?? (loading ? "checking" : "degraded"), detail: serviceDetailLabel[health?.environment ?? "local"] ?? health?.environment ?? "本地环境" },
    ...services.map((s) => ({ label: serviceNameLabel[s.name] ?? s.name, status: s.status, detail: serviceDetailLabel[s.detail] ?? s.detail }))
  ];
  const degradedServices = serviceRows.filter((s) => !["ok", "reachable", "succeeded"].includes(s.status)).length;

  const projectActions = pid
    ? [
        { to: routes.projectImports(wid, pid), title: "导入用例", desc: "清洗 Excel/CSV 历史资产，提交为可评审草稿。", meta: "资产准备", Icon: FileInput },
        { to: routes.projectReviews(wid, pid), title: "评审队列", desc: "处理待评审草稿，沉淀为正式用例库。", meta: "质量治理", Icon: ClipboardCheck },
        { to: routes.projectDiffs(wid, pid), title: "Diff 分析", desc: "按分支或 tag 识别变更影响和风险模块。", meta: "变更评估", Icon: GitCompareArrows },
        { to: routes.projectAI(wid, pid), title: "AI 建议", desc: "基于变更与历史用例生成回归建议。", meta: "智能辅助", Icon: BrainCircuit },
        { to: routes.projectPlans(wid, pid), title: "测试计划", desc: "组织发布范围、执行项、负责人和证据。", meta: "发布执行", Icon: ListChecks },
        { to: routes.projectReports(wid, pid), title: "发布报告", desc: "汇总执行结果，确认发布建议与结论。", meta: "决策输出", Icon: FileText }
      ]
    : [{ to: wid ? routes.adminProjects(wid) : "/", title: "创建第一个项目", desc: "先建立项目，之后就可以导入用例、分析变更和编排测试计划。", meta: "开始配置", Icon: FolderKanban }];

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)] mb-1">Workspace 总览</p>
          <h1 className="font-heading text-2xl font-bold">我的工作台</h1>
          <p className="mt-1 text-sm text-[var(--muted-foreground)]">围绕当前项目，把用例资产、评审、变更分析和发布执行放在一个入口里。</p>
        </div>
        <Button variant="outline" size="icon" onClick={() => void refresh()} title="刷新状态">
          <RefreshCcw size={16} />
        </Button>
      </div>

      {error && <Alert variant="destructive"><AlertCircle size={16} className="shrink-0" /><AlertDescription>{error}</AlertDescription></Alert>}

      {/* Hero */}
      <Card>
        <CardContent className="flex items-center justify-between gap-4 p-5">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)] mb-1">当前项目</p>
            <h2 className="font-heading text-xl font-bold">{proj ? `${proj.key} · ${proj.name}` : "尚未选择项目"}</h2>
            <p className="mt-1 text-sm text-[var(--muted-foreground)] max-w-2xl">{proj?.description || "选择一个项目后，可以从这里进入日常测试资产管理、变更影响分析和发布测试协作。"}</p>
          </div>
          <div className="flex gap-2 shrink-0">
            {pid ? (
              <>
                <Button asChild><Link to={routes.projectLibrary(wid, pid)}>进入用例库</Link></Button>
                <Button variant="outline" asChild><Link to={routes.projectOverview(wid, pid)}>项目首页</Link></Button>
              </>
            ) : (
              <Button asChild><Link to={wid ? routes.adminProjects(wid) : "/"}>创建项目</Link></Button>
            )}
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_300px] gap-5 items-start">
        <div className="flex flex-col gap-5">
          {/* Action grid */}
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3" aria-label="常用工作入口">
            {projectActions.map((action) => {
              const Icon = action.Icon;
              return (
                <Link
                  key={action.title}
                  to={action.to}
                  className="flex flex-col gap-2 p-4 rounded-[var(--radius-md)] border bg-[var(--card)] shadow-sm hover:border-[var(--primary)]/40 hover:shadow-md hover:-translate-y-px transition-all"
                >
                  <Icon size={20} className="text-[var(--primary)]" />
                  <span className="text-[10px] font-bold uppercase tracking-wider text-[var(--muted-foreground)]">{action.meta}</span>
                  <strong className="text-sm font-semibold leading-snug">{action.title}</strong>
                  <small className="text-xs text-[var(--muted-foreground)] leading-snug">{action.desc}</small>
                </Link>
              );
            })}
          </div>

          {/* Work items */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--muted-foreground)] mb-0.5">流程进度</p>
                  <CardTitle>平台能力准备</CardTitle>
                </div>
                <Activity size={18} className="text-[var(--muted-foreground)]" />
              </div>
              <div className="flex items-center gap-3 pt-1">
                <span className="text-xl font-bold text-[var(--primary)]">{completedWorkItems}/{workItems.length || 0}</span>
                <span className="text-sm text-[var(--muted-foreground)]">{summary?.mvp_stage ?? "基础平台能力"}</span>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              <div role="table" aria-label="MVP issue 队列">
                <div className="grid grid-cols-[88px_1fr_120px_100px] gap-3 px-5 py-2.5 text-[11px] font-bold uppercase tracking-wider text-[var(--muted-foreground)] border-b">
                  <span>Issue</span><span>标题</span><span>Owner</span><span>状态</span>
                </div>
                {workItemsPagination.currentItems.map((item) => (
                  <div key={item.issue} className="grid grid-cols-[88px_1fr_120px_100px] gap-3 px-5 py-3 border-b last:border-0 text-sm hover:bg-[var(--muted)]/40 transition-colors" role="row">
                    <span className="font-mono text-xs text-[var(--muted-foreground)]">{item.issue}</span>
                    <span className="truncate">{item.title}</span>
                    <span className="text-[var(--muted-foreground)] truncate">{item.owner}</span>
                    <StatusPill status={item.status} />
                  </div>
                ))}
                {workItems.length === 0 && <p className="px-5 py-4 text-sm text-[var(--muted-foreground)]">暂无工作项</p>}
              </div>
              <div className="px-5"><Pagination currentPage={workItemsPagination.currentPage} totalPages={workItemsPagination.totalPages} totalItems={workItemsPagination.totalItems} onPageChange={workItemsPagination.goToPage} itemsPerPage={8} /></div>
            </CardContent>
          </Card>

          {/* Recent jobs */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--muted-foreground)] mb-0.5">Jobs</p>
                  <CardTitle>最近任务</CardTitle>
                </div>
                <Database size={18} className="text-[var(--muted-foreground)]" />
              </div>
            </CardHeader>
            <CardContent className="p-0">
              {jobsPagination.currentItems.map((job) => (
                <div key={`${job.type}-${job.created_at}`} className="flex items-start gap-3 px-5 py-3 border-b last:border-0">
                  <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-[var(--primary)]" />
                  <div className="min-w-0">
                    <p className="text-sm font-semibold truncate">{job.summary}</p>
                    <p className="text-xs text-[var(--muted-foreground)]">{jobTypeLabel[job.type] ?? job.type} · {statusLabel[job.status] ?? job.status}</p>
                  </div>
                </div>
              ))}
              {recentJobs.length === 0 && <p className="px-5 py-4 text-sm text-[var(--muted-foreground)]">暂无任务记录</p>}
              <div className="px-5"><Pagination currentPage={jobsPagination.currentPage} totalPages={jobsPagination.totalPages} totalItems={jobsPagination.totalItems} onPageChange={jobsPagination.goToPage} itemsPerPage={6} /></div>
            </CardContent>
          </Card>
        </div>

        {/* Side column */}
        <div className="flex flex-col gap-4">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--muted-foreground)] mb-0.5">待处理</p>
                  <CardTitle>协作队列</CardTitle>
                </div>
                <span className="text-2xl font-bold text-[var(--primary)]">{openQueueCount}</span>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              {(summary?.queues ?? []).map((queue) => (
                <div key={queue.label} className="flex items-center justify-between gap-3 px-5 py-3 border-t">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold">{queue.label}</p>
                    <p className="text-xs text-[var(--muted-foreground)]">{queueTrendLabel[queue.trend] ?? queue.trend}</p>
                  </div>
                  <span className="text-xl font-bold text-[var(--primary)] shrink-0">{queue.value}</span>
                </div>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--muted-foreground)] mb-0.5">系统状态</p>
                  <CardTitle>服务可用性</CardTitle>
                </div>
                <ServerCog size={18} className="text-[var(--muted-foreground)]" />
              </div>
            </CardHeader>
            <CardContent className="p-0">
              {serviceRows.map((s) => (
                <div key={s.label} className="flex items-center justify-between gap-3 px-5 py-3 border-t">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold">{s.label}</p>
                    <p className="text-xs text-[var(--muted-foreground)] truncate">{s.detail}</p>
                  </div>
                  <StatusPill status={s.status} />
                </div>
              ))}
              <div className={`mx-5 my-3 rounded-[var(--radius-sm)] px-3 py-2 text-xs font-semibold ${degradedServices > 0 ? "bg-amber-50 text-amber-800 dark:bg-amber-900/20 dark:text-amber-400" : "bg-green-50 text-green-800 dark:bg-green-900/20 dark:text-green-400"}`}>
                {degradedServices > 0 ? `${degradedServices} 个服务需要关注` : "全部核心服务可用"}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
