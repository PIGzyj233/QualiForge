import { FormEvent, useEffect, useState } from "react";
import { FileText, History, ShieldCheck, Sparkles } from "lucide-react";
import {
  confirmReleaseReportDecision,
  createReleaseReportDraft,
  exportReleaseReportMarkdown,
  listProjects,
  listReleaseReports,
  listTestPlans,
  listWorkspaces,
  ProjectRecord,
  ReleaseReportRecord,
  Session,
  TestPlanRecord,
  WorkspaceRecord
} from "../api";
import { statusLabel } from "../lib/labels";

export function ReleaseReportAdmin({ session }: { session: Session }) {
  const actorEmail = session.user.email;
  const [workspaces, setWorkspaces] = useState<WorkspaceRecord[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState("");
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [plans, setPlans] = useState<TestPlanRecord[]>([]);
  const [selectedPlanId, setSelectedPlanId] = useState("");
  const [reports, setReports] = useState<ReleaseReportRecord[]>([]);
  const [selectedReportId, setSelectedReportId] = useState("");
  const [releaseDecision, setReleaseDecision] = useState("hold_release");
  const [decisionComment, setDecisionComment] = useState("Release decision pending owner review.");
  const [markdownExport, setMarkdownExport] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function refreshReports(workspaceId: string, projectId: string, planId: string, preferredReportId?: string) {
    if (!planId) {
      setReports([]);
      setSelectedReportId("");
      setMarkdownExport("");
      return;
    }
    const nextReports = await listReleaseReports(workspaceId, projectId, planId);
    setReports(nextReports);
    const nextReport = nextReports.find((report) => report.id === preferredReportId) ?? nextReports.find((report) => report.id === selectedReportId) ?? nextReports[0];
    setSelectedReportId(nextReport?.id ?? "");
    if (nextReport) {
      setReleaseDecision(nextReport.release_decision === "pending_owner_confirmation" ? nextReport.release_suggestion : nextReport.release_decision);
      setDecisionComment(nextReport.decision_comment || "Release decision pending owner review.");
    }
  }

  async function refreshReportProject(workspaceId: string, projectId: string, preferredPlanId?: string, preferredReportId?: string) {
    const nextPlans = await listTestPlans(workspaceId, projectId);
    setPlans(nextPlans);
    const nextPlanId = preferredPlanId || selectedPlanId || nextPlans[0]?.id || "";
    setSelectedPlanId(nextPlanId);
    await refreshReports(workspaceId, projectId, nextPlanId, preferredReportId);
  }

  async function refreshReportWorkspaces(preferredWorkspaceId?: string, preferredProjectId?: string) {
    setBusy(true);
    setMessage(null);
    try {
      const nextWorkspaces = await listWorkspaces(actorEmail);
      setWorkspaces(nextWorkspaces);
      const nextWorkspaceId = preferredWorkspaceId || selectedWorkspaceId || nextWorkspaces[0]?.id || "";
      setSelectedWorkspaceId(nextWorkspaceId);
      if (!nextWorkspaceId) return;
      const nextProjects = await listProjects(nextWorkspaceId);
      setProjects(nextProjects);
      const nextProjectId = preferredProjectId || selectedProjectId || nextProjects[0]?.id || "";
      setSelectedProjectId(nextProjectId);
      if (nextProjectId) {
        await refreshReportProject(nextWorkspaceId, nextProjectId);
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "发布报告加载失败");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void refreshReportWorkspaces();
  }, []);

  async function handleWorkspaceSwitch(workspaceId: string) {
    setSelectedWorkspaceId(workspaceId);
    setBusy(true);
    setMessage(null);
    try {
      const nextProjects = await listProjects(workspaceId);
      setProjects(nextProjects);
      const nextProjectId = nextProjects[0]?.id ?? "";
      setSelectedProjectId(nextProjectId);
      if (nextProjectId) {
        await refreshReportProject(workspaceId, nextProjectId);
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "发布报告 Workspace 切换失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleProjectSwitch(projectId: string) {
    setSelectedProjectId(projectId);
    if (!selectedWorkspaceId || !projectId) return;
    setBusy(true);
    setMessage(null);
    try {
      await refreshReportProject(selectedWorkspaceId, projectId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "发布报告 Project 切换失败");
    } finally {
      setBusy(false);
    }
  }

  async function handlePlanSwitch(planId: string) {
    setSelectedPlanId(planId);
    if (!selectedWorkspaceId || !selectedProjectId) return;
    setBusy(true);
    setMessage(null);
    try {
      await refreshReports(selectedWorkspaceId, selectedProjectId, planId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "报告列表加载失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleReportSwitch(reportId: string) {
    setSelectedReportId(reportId);
    const report = reports.find((item) => item.id === reportId);
    if (report) {
      setReleaseDecision(report.release_decision === "pending_owner_confirmation" ? report.release_suggestion : report.release_decision);
      setDecisionComment(report.decision_comment || "Release decision pending owner review.");
      setMarkdownExport("");
    }
  }

  async function handleGenerateDraft() {
    if (!selectedWorkspaceId || !selectedProjectId || !selectedPlanId) return;
    setBusy(true);
    setMessage(null);
    try {
      const report = await createReleaseReportDraft(selectedWorkspaceId, selectedProjectId, selectedPlanId, actorEmail);
      setMessage(`已生成报告草稿：${report.title}`);
      await refreshReportProject(selectedWorkspaceId, selectedProjectId, selectedPlanId, report.id);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "报告草稿生成失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleConfirmDecision(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedWorkspaceId || !selectedProjectId || !selectedReportId) return;
    setBusy(true);
    setMessage(null);
    try {
      const report = await confirmReleaseReportDecision(selectedWorkspaceId, selectedProjectId, selectedReportId, actorEmail, {
        release_decision: releaseDecision,
        decision_comment: decisionComment
      });
      setMessage(`已确认发布结论：${statusLabel[report.release_decision] ?? report.release_decision}`);
      await refreshReportProject(selectedWorkspaceId, selectedProjectId, selectedPlanId, report.id);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "发布结论确认失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleExportMarkdown() {
    if (!selectedWorkspaceId || !selectedProjectId || !selectedReportId) return;
    setBusy(true);
    setMessage(null);
    try {
      const markdown = await exportReleaseReportMarkdown(selectedWorkspaceId, selectedProjectId, selectedReportId);
      setMarkdownExport(markdown);
      setMessage("Markdown 报告已生成");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Markdown 导出失败");
    } finally {
      setBusy(false);
    }
  }

  const selectedProject = projects.find((project) => project.id === selectedProjectId);
  const selectedPlan = plans.find((plan) => plan.id === selectedPlanId);
  const selectedReport = reports.find((report) => report.id === selectedReportId);
  const sections = (selectedReport?.sections ?? {}) as Record<string, unknown>;
  const summary = (sections.summary ?? {}) as Record<string, unknown>;
  const versionDiff = (sections.version_diff ?? {}) as Record<string, unknown>;
  const scope = (sections.scope ?? {}) as Record<string, unknown>;
  const stats = (sections.execution_statistics ?? {}) as Record<string, unknown>;
  const counts = (stats.counts ?? {}) as Record<string, number>;
  const risk = (sections.risk_assessment ?? {}) as Record<string, unknown>;
  const failedBlocked = Array.isArray(sections.failed_blocked_items) ? (sections.failed_blocked_items as Array<Record<string, unknown>>) : [];
  const appendixItems = Array.isArray((sections.appendix as Record<string, unknown> | undefined)?.items)
    ? (((sections.appendix as Record<string, unknown>).items ?? []) as Array<Record<string, unknown>>)
    : [];

  return (
    <section className="section-block release-report-admin">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Release Report</span>
          <h2>发布测试报告</h2>
        </div>
        <FileText size={20} aria-hidden="true" />
      </div>
      <div className="admin-body">
        {message ? <div className="inline-notice">{message}</div> : null}

        <div className="admin-toolbar">
          <label className="select-label">
            当前 Workspace
            <select value={selectedWorkspaceId} onChange={(event) => void handleWorkspaceSwitch(event.target.value)} disabled={busy || workspaces.length === 0}>
              <option value="">未选择</option>
              {workspaces.map((workspace) => (
                <option value={workspace.id} key={workspace.id}>
                  {workspace.name}
                </option>
              ))}
            </select>
          </label>
          <label className="select-label">
            当前 Project
            <select value={selectedProjectId} onChange={(event) => void handleProjectSwitch(event.target.value)} disabled={busy || projects.length === 0}>
              <option value="">未选择</option>
              {projects.map((project) => (
                <option value={project.id} key={project.id}>
                  {project.key} · {project.name}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="admin-context">
          <strong>{selectedProject ? `${selectedProject.key} · ${selectedProject.name}` : "尚未选择 Project"}</strong>
          <span>{selectedReport ? `${selectedReport.title} · ${statusLabel[selectedReport.status]}` : selectedPlan ? `${selectedPlan.name} · ${selectedPlan.version_ref || "no version"}` : "选择计划生成发布报告"}</span>
        </div>

        <div className="admin-grid">
          <section className="admin-pane" aria-label="报告草稿">
            <div className="pane-heading">
              <div>
                <span className="eyebrow">Draft</span>
                <h3>报告草稿</h3>
              </div>
              <Sparkles size={18} aria-hidden="true" />
            </div>
            <div className="stack-form">
              <label>
                TestPlan
                <select value={selectedPlanId} onChange={(event) => void handlePlanSwitch(event.target.value)} disabled={busy || plans.length === 0}>
                  <option value="">未选择</option>
                  {plans.map((plan) => (
                    <option value={plan.id} key={plan.id}>
                      {plan.name} · {plan.version_ref || "no version"}
                    </option>
                  ))}
                </select>
              </label>
              <button className="primary-button small" type="button" onClick={() => void handleGenerateDraft()} disabled={busy || !selectedPlanId}>
                生成报告草稿
              </button>
            </div>
            <div className="data-list">
              {reports.map((report) => (
                <div className="data-row module-row" key={report.id}>
                  <div>
                    <strong>{report.title}</strong>
                    <span>{statusLabel[report.status]} · AI {statusLabel[report.release_suggestion] ?? report.release_suggestion}</span>
                    <small>{report.release_decision === "pending_owner_confirmation" ? "待负责人确认" : `${statusLabel[report.release_decision] ?? report.release_decision} · ${report.confirmed_by}`}</small>
                  </div>
                  <button className="ghost-button" type="button" onClick={() => void handleReportSwitch(report.id)}>
                    查看
                  </button>
                </div>
              ))}
              {reports.length === 0 ? <p className="empty-state">暂无发布报告</p> : null}
            </div>
          </section>

          <section className="admin-pane" aria-label="发布结论确认">
            <div className="pane-heading">
              <div>
                <span className="eyebrow">Decision</span>
                <h3>负责人确认</h3>
              </div>
              <ShieldCheck size={18} aria-hidden="true" />
            </div>
            <form className="stack-form" onSubmit={handleConfirmDecision}>
              <label>
                Release Decision
                <select value={releaseDecision} onChange={(event) => setReleaseDecision(event.target.value)}>
                  <option value="hold_release">暂缓发布</option>
                  <option value="conditional_release">有条件发布</option>
                  <option value="approve_release">确认发布</option>
                </select>
              </label>
              <label>
                结论说明
                <textarea value={decisionComment} onChange={(event) => setDecisionComment(event.target.value)} rows={4} />
              </label>
              <button className="primary-button small" type="submit" disabled={busy || !selectedReportId}>
                确认发布结论
              </button>
              <button className="ghost-button" type="button" onClick={() => void handleExportMarkdown()} disabled={busy || !selectedReportId}>
                导出 Markdown
              </button>
            </form>
          </section>
        </div>

        {selectedReport ? (
          <section className="audit-pane" aria-label="在线发布报告">
            <div className="pane-heading">
              <div>
                <span className="eyebrow">Web Report</span>
                <h3>{selectedReport.title}</h3>
              </div>
              <History size={18} aria-hidden="true" />
            </div>
            <div className="report-grid">
              <div className="report-section">
                <strong>Summary</strong>
                <span>{String(summary.text ?? "")}</span>
              </div>
              <div className="report-section">
                <strong>Version & Diff</strong>
                <span>{String(versionDiff.version_ref ?? "n/a")} · {String(versionDiff.diff_summary ?? "")}</span>
              </div>
              <div className="report-section">
                <strong>Scope</strong>
                <span>{String(scope.scope_summary ?? "")}</span>
              </div>
              <div className="report-section">
                <strong>Execution Statistics</strong>
                <span>{String(stats.recorded ?? 0)}/{String(stats.total ?? 0)} · {String(stats.completion_rate ?? 0)}% · pass {counts.passed ?? 0} / fail {counts.failed ?? 0} / blocked {counts.blocked ?? 0}</span>
              </div>
              <div className="report-section">
                <strong>Failed / Blocked Items</strong>
                {failedBlocked.length > 0 ? (
                  failedBlocked.map((item) => (
                    <span key={String(item.id)}>{String(item.title)} · {String(item.status)} · {String(item.failure_reason || item.actual_result || "no result")}</span>
                  ))
                ) : (
                  <span>None</span>
                )}
              </div>
              <div className="report-section">
                <strong>Risk Assessment</strong>
                <span>{String(risk.risk_level ?? "unknown")} · acceptable {String(risk.risk_acceptable ?? false)} · {String(risk.text ?? "")}</span>
              </div>
              <div className="report-section">
                <strong>AI Notes</strong>
                {selectedReport.ai_notes.map((note) => (
                  <span key={note}>{note}</span>
                ))}
              </div>
              <div className="report-section">
                <strong>Release Decision</strong>
                <span>{statusLabel[selectedReport.release_decision] ?? selectedReport.release_decision} · {selectedReport.decision_comment || "pending"} · {selectedReport.confirmed_by || "unconfirmed"}</span>
              </div>
              <div className="report-section">
                <strong>Appendix</strong>
                <span>{appendixItems.length} plan item(s) captured with execution metadata and evidence references.</span>
              </div>
            </div>
          </section>
        ) : null}

        {markdownExport ? (
          <section className="audit-pane" aria-label="Markdown 导出">
            <div className="pane-heading">
              <div>
                <span className="eyebrow">Markdown</span>
                <h3>导出内容</h3>
              </div>
              <FileText size={18} aria-hidden="true" />
            </div>
            <textarea className="markdown-preview" value={markdownExport} readOnly rows={14} />
          </section>
        ) : null}
      </div>
    </section>
  );
}
