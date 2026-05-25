import { useEffect, useMemo, useState } from "react";
import { Activity, AlertCircle, CheckCircle2, Database, RefreshCcw } from "lucide-react";
import { DashboardSummary, getDashboardSummary, getHealth, HealthPayload } from "../../api";
import { Pagination } from "../../components/Pagination";
import { StatusPill } from "../../components/StatusPill";
import { StatusTile } from "../../components/StatusTile";
import { usePagination } from "../../hooks/usePagination";

export function WorkbenchOverview() {
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

  const workItems = summary?.work_items ?? [];
  const recentJobs = summary?.recent_jobs ?? [];
  const workItemsPagination = usePagination(workItems, 8);
  const jobsPagination = usePagination(recentJobs, 6);

  return (
    <>
      <div className="page-head">
        <div>
          <span className="eyebrow">Workspace 总览</span>
          <h2>工作台</h2>
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
      <section className="status-grid" aria-label="服务状态">
        <StatusTile
          label="Backend API"
          status={health?.status ?? (loading ? "checking" : "degraded")}
          detail={health?.environment ?? "local"}
        />
        {services.map((service) => (
          <StatusTile key={service.name} label={service.name} status={service.status} detail={service.detail} />
        ))}
      </section>
      <section className="workbench-layout">
        <div className="main-column">
          <section className="section-block">
            <div className="section-heading">
              <div>
                <span className="eyebrow">Issue Chain</span>
                <h2>{summary?.mvp_stage ?? "基础平台"}</h2>
              </div>
              <Activity size={20} aria-hidden="true" />
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
                      {job.type} · {job.status}
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
          {(summary?.queues ?? []).map((queue) => (
            <div className="metric-card" key={queue.label}>
              <span>{queue.label}</span>
              <strong>{queue.value}</strong>
              <small>{queue.trend}</small>
            </div>
          ))}
        </aside>
      </section>
    </>
  );
}
