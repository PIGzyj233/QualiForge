import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, FileSearch, MessageSquareWarning, XCircle } from "lucide-react";
import {
  approveReviewCycle,
  getTestCase,
  listModules,
  listProjects,
  listReviewQueue,
  listWorkspaces,
  ProjectModuleRecord,
  ProjectRecord,
  rejectReviewCycle,
  requestReviewChanges,
  Session,
  TestCaseRecord,
  WorkspaceRecord
} from "../api";
import { CaseRevisionViewer } from "../components/CaseRevisionViewer";
import { ReviewStatusBadge } from "../components/ReviewStatusBadge";

export function ReviewQueueView({ session }: { session: Session }) {
  const actorEmail = session.user.email;
  const [workspaces, setWorkspaces] = useState<WorkspaceRecord[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState("");
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [modules, setModules] = useState<ProjectModuleRecord[]>([]);
  const [queue, setQueue] = useState<TestCaseRecord[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState("");
  const [selectedCase, setSelectedCase] = useState<TestCaseRecord | null>(null);
  const [reviewComment, setReviewComment] = useState("Looks good");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function refreshDetail(workspaceId: string, projectId: string, caseId: string) {
    if (!caseId) {
      setSelectedCase(null);
      return;
    }
    setSelectedCase(await getTestCase(workspaceId, projectId, caseId));
  }

  async function refreshQueue(workspaceId: string, projectId: string, preferredCaseId?: string) {
    const [nextModules, nextQueue] = await Promise.all([listModules(workspaceId, projectId), listReviewQueue(workspaceId, projectId)]);
    setModules(nextModules);
    setQueue(nextQueue);
    const caseId = preferredCaseId || selectedCaseId || nextQueue[0]?.id || "";
    setSelectedCaseId(caseId);
    await refreshDetail(workspaceId, projectId, caseId);
  }

  async function refreshWorkspace(preferredWorkspaceId?: string, preferredProjectId?: string) {
    setBusy(true);
    setMessage(null);
    try {
      const nextWorkspaces = await listWorkspaces(actorEmail);
      setWorkspaces(nextWorkspaces);
      const workspaceId = preferredWorkspaceId || selectedWorkspaceId || nextWorkspaces[0]?.id || "";
      setSelectedWorkspaceId(workspaceId);
      if (!workspaceId) return;
      const nextProjects = await listProjects(workspaceId);
      setProjects(nextProjects);
      const projectId = preferredProjectId || selectedProjectId || nextProjects[0]?.id || "";
      setSelectedProjectId(projectId);
      if (projectId) await refreshQueue(workspaceId, projectId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "评审队列加载失败");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void refreshWorkspace();
  }, []);

  async function handleAction(action: "approve" | "changes" | "reject") {
    if (!selectedWorkspaceId || !selectedProjectId || !selectedCase?.open_cycle) return;
    setBusy(true);
    setMessage(null);
    try {
      if (action === "approve") {
        await approveReviewCycle(selectedWorkspaceId, selectedProjectId, selectedCase.open_cycle.id, actorEmail, reviewComment || "Approved");
        setMessage("已通过评审");
      } else if (action === "changes") {
        await requestReviewChanges(selectedWorkspaceId, selectedProjectId, selectedCase.open_cycle.id, actorEmail, reviewComment);
        setMessage("已要求修改");
      } else {
        await rejectReviewCycle(selectedWorkspaceId, selectedProjectId, selectedCase.open_cycle.id, actorEmail, reviewComment || "Rejected");
        setMessage("已驳回评审");
      }
      await refreshQueue(selectedWorkspaceId, selectedProjectId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "评审操作失败");
    } finally {
      setBusy(false);
    }
  }

  const moduleById = useMemo(() => new Map(modules.map((module) => [module.id, module])), [modules]);

  return (
    <section className="section-block review-queue">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Review Queue</span>
          <h2>评审队列</h2>
        </div>
        <FileSearch size={20} aria-hidden="true" />
      </div>
      <div className="admin-body">
        {message ? <div className="inline-notice">{message}</div> : null}
        <div className="admin-toolbar">
          <label className="select-label">
            当前 Workspace
            <select value={selectedWorkspaceId} onChange={(event) => void refreshWorkspace(event.target.value)} disabled={busy || workspaces.length === 0}>
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
            <select
              value={selectedProjectId}
              onChange={(event) => {
                setSelectedProjectId(event.target.value);
                void refreshQueue(selectedWorkspaceId, event.target.value);
              }}
              disabled={busy || projects.length === 0}
            >
              <option value="">未选择</option>
              {projects.map((project) => (
                <option value={project.id} key={project.id}>
                  {project.key} · {project.name}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="review-queue-layout">
          <section className="case-list-panel" aria-label="待评审列表">
            <div className="pane-heading">
              <div>
                <span className="eyebrow">Pending</span>
                <h3>待评审工作</h3>
              </div>
              <ReviewStatusBadge status="pending_review" />
            </div>
            <div className="data-list case-list">
              {queue.map((testCase) => (
                <button
                  className={selectedCaseId === testCase.id ? "case-row active" : "case-row"}
                  type="button"
                  key={testCase.id}
                  onClick={() => {
                    setSelectedCaseId(testCase.id);
                    void refreshDetail(selectedWorkspaceId, selectedProjectId, testCase.id);
                  }}
                >
                  <strong>{testCase.title}</strong>
                  <span>{moduleById.get(testCase.module_id ?? "")?.path_label ?? testCase.module_path_label}</span>
                  <small>{testCase.active_draft?.source_type ?? testCase.source_type} · {testCase.open_cycle?.submitted_by ?? "unknown"}</small>
                </button>
              ))}
              {queue.length === 0 ? <p className="empty-state">暂无待评审项</p> : null}
            </div>
          </section>

          <section className="case-detail-panel" aria-label="评审详情">
            {selectedCase?.active_draft ? (
              <>
                <div className="case-detail-head">
                  <div>
                    <span className="eyebrow">Draft</span>
                    <h3>{selectedCase.active_draft.title}</h3>
                    <p>{selectedCase.module_path_label}</p>
                  </div>
                  <ReviewStatusBadge status={selectedCase.review_status} />
                </div>
                <div className="comparison-grid">
                  <CaseRevisionViewer revision={selectedCase.current_revision} />
                  <div className="case-content">
                    <h3>{selectedCase.active_draft.title}</h3>
                    <ol className="step-list paired">
                      {selectedCase.active_draft.steps.map((step, i) => (
                        <li key={i}>
                          <span className="step-action">{step.action || "(空步骤)"}</span>
                          {step.expected ? <span className="step-expected">→ {step.expected}</span> : null}
                        </li>
                      ))}
                    </ol>
                  </div>
                </div>
                <label className="select-label">
                  评审意见
                  <textarea value={reviewComment} onChange={(event) => setReviewComment(event.target.value)} rows={3} />
                </label>
                <div className="review-action-strip">
                  <button className="primary-button small" type="button" disabled={busy} onClick={() => void handleAction("approve")}>
                    <CheckCircle2 size={16} aria-hidden="true" />
                    通过
                  </button>
                  <button className="ghost-button" type="button" disabled={busy || !reviewComment.trim()} onClick={() => void handleAction("changes")}>
                    <MessageSquareWarning size={16} aria-hidden="true" />
                    要求修改
                  </button>
                  <button className="ghost-button" type="button" disabled={busy} onClick={() => void handleAction("reject")}>
                    <XCircle size={16} aria-hidden="true" />
                    驳回
                  </button>
                </div>
              </>
            ) : (
              <p className="empty-state">评审队列只展示 pending_review 项。</p>
            )}
          </section>
        </div>
      </div>
    </section>
  );
}
