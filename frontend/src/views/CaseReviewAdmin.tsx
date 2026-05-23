import { FormEvent, useEffect, useState } from "react";
import { ClipboardCheck, History, Plus, Settings2, ShieldCheck } from "lucide-react";
import {
  CaseReviewAction,
  CaseReviewRecord,
  CaseRevisionRecord,
  createTestCase,
  getReviewSettings,
  listCaseReviews,
  listCaseRevisions,
  listModules,
  listProjects,
  listTestCases,
  listWorkspaces,
  ProjectRecord,
  ProjectModuleRecord,
  ReviewSettingsRecord,
  reviewTestCase,
  Session,
  submitTestCaseReview,
  TestCaseRecord,
  TestCasePayload,
  updateReviewSettings,
  updateTestCase,
  WorkspaceRecord
} from "../api";
import { Pagination } from "../components/Pagination";
import { usePagination } from "../hooks/usePagination";
import { statusLabel } from "../lib/labels";

export function CaseReviewAdmin({ session }: { session: Session }) {
  const actorEmail = session.user.email;
  const [workspaces, setWorkspaces] = useState<WorkspaceRecord[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState("");
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [modules, setModules] = useState<ProjectModuleRecord[]>([]);
  const [settings, setSettings] = useState<ReviewSettingsRecord | null>(null);
  const [testCases, setTestCases] = useState<TestCaseRecord[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState("");
  const [reviews, setReviews] = useState<CaseReviewRecord[]>([]);
  const [revisions, setRevisions] = useState<CaseRevisionRecord[]>([]);
  const [allowSelfReview, setAllowSelfReview] = useState(false);
  const [requireReviewOnUpdate, setRequireReviewOnUpdate] = useState(true);
  const [caseTitle, setCaseTitle] = useState("Checkout payment succeeds");
  const [caseModuleId, setCaseModuleId] = useState("");
  const [caseSteps, setCaseSteps] = useState("Open checkout\nPay order");
  const [caseExpected, setCaseExpected] = useState("Order is paid and receipt is visible");
  const [casePriority, setCasePriority] = useState("P1");
  const [caseRisk, setCaseRisk] = useState("high");
  const [caseTags, setCaseTags] = useState("checkout, review");
  const [caseCustomFields, setCaseCustomFields] = useState("{\"source\":\"manual\"}");
  const [reviewComment, setReviewComment] = useState("Looks good");
  const [editTitle, setEditTitle] = useState("Checkout payment succeeds after 3DS");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const testCasesPagination = usePagination(testCases, 10);

  function parseList(value: string): string[] {
    return value.split(/\r?\n|[,，;；]/).map((item) => item.trim()).filter(Boolean);
  }

  function buildCasePayload(): TestCasePayload {
    return {
      module_id: caseModuleId || null,
      title: caseTitle,
      steps: parseList(caseSteps),
      expected_result: caseExpected,
      priority: casePriority,
      risk: caseRisk,
      tags: parseList(caseTags),
      custom_fields: caseCustomFields.trim() ? (JSON.parse(caseCustomFields) as Record<string, string>) : {}
    };
  }

  async function refreshSelectedCase(workspaceId: string, projectId: string, caseId: string) {
    if (!caseId) {
      setReviews([]);
      setRevisions([]);
      return;
    }
    const [nextReviews, nextRevisions] = await Promise.all([
      listCaseReviews(workspaceId, projectId, caseId),
      listCaseRevisions(workspaceId, projectId, caseId)
    ]);
    setReviews(nextReviews);
    setRevisions(nextRevisions);
  }

  async function refreshCaseProject(workspaceId: string, projectId: string, preferredCaseId?: string) {
    const [nextModules, nextCases] = await Promise.all([listModules(workspaceId, projectId), listTestCases(workspaceId, projectId)]);
    setModules(nextModules);
    setTestCases(nextCases);
    if (!caseModuleId && nextModules[0]) {
      setCaseModuleId(nextModules[0].id);
    }
    const nextCaseId = preferredCaseId || selectedCaseId || nextCases[0]?.id || "";
    setSelectedCaseId(nextCaseId);
    await refreshSelectedCase(workspaceId, projectId, nextCaseId);
  }

  async function refreshCaseWorkspaces(preferredWorkspaceId?: string, preferredProjectId?: string, preferredCaseId?: string) {
    setBusy(true);
    setMessage(null);
    try {
      const nextWorkspaces = await listWorkspaces(actorEmail);
      setWorkspaces(nextWorkspaces);
      const nextWorkspaceId = preferredWorkspaceId || selectedWorkspaceId || nextWorkspaces[0]?.id || "";
      setSelectedWorkspaceId(nextWorkspaceId);
      if (!nextWorkspaceId) return;
      const nextSettings = await getReviewSettings(nextWorkspaceId);
      setSettings(nextSettings);
      setAllowSelfReview(nextSettings.allow_self_review);
      setRequireReviewOnUpdate(nextSettings.require_review_on_case_update);
      const nextProjects = await listProjects(nextWorkspaceId);
      setProjects(nextProjects);
      const nextProjectId = preferredProjectId || selectedProjectId || nextProjects[0]?.id || "";
      setSelectedProjectId(nextProjectId);
      if (nextProjectId) {
        await refreshCaseProject(nextWorkspaceId, nextProjectId, preferredCaseId);
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "评审数据加载失败");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void refreshCaseWorkspaces();
  }, []);

  async function handleWorkspaceSwitch(workspaceId: string) {
    setSelectedWorkspaceId(workspaceId);
    setBusy(true);
    setMessage(null);
    try {
      const [nextSettings, nextProjects] = await Promise.all([getReviewSettings(workspaceId), listProjects(workspaceId)]);
      setSettings(nextSettings);
      setAllowSelfReview(nextSettings.allow_self_review);
      setRequireReviewOnUpdate(nextSettings.require_review_on_case_update);
      setProjects(nextProjects);
      const nextProjectId = nextProjects[0]?.id ?? "";
      setSelectedProjectId(nextProjectId);
      if (nextProjectId) {
        await refreshCaseProject(workspaceId, nextProjectId);
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "评审 Workspace 切换失败");
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
      await refreshCaseProject(selectedWorkspaceId, projectId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "评审 Project 切换失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleSettingsSave() {
    if (!selectedWorkspaceId) return;
    setBusy(true);
    setMessage(null);
    try {
      const nextSettings = await updateReviewSettings(selectedWorkspaceId, actorEmail, {
        allow_self_review: allowSelfReview,
        require_review_on_case_update: requireReviewOnUpdate
      });
      setSettings(nextSettings);
      setMessage("已保存评审策略");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "评审策略保存失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateCase(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedWorkspaceId || !selectedProjectId) return;
    setBusy(true);
    setMessage(null);
    try {
      const created = await createTestCase(selectedWorkspaceId, selectedProjectId, actorEmail, buildCasePayload());
      setMessage(`已创建候选用例：${created.title}`);
      await refreshCaseProject(selectedWorkspaceId, selectedProjectId, created.id);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "候选用例创建失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleSelectCase(caseId: string) {
    setSelectedCaseId(caseId);
    if (!selectedWorkspaceId || !selectedProjectId) return;
    setBusy(true);
    setMessage(null);
    try {
      await refreshSelectedCase(selectedWorkspaceId, selectedProjectId, caseId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "评审详情加载失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleSubmitCase(caseId: string) {
    if (!selectedWorkspaceId || !selectedProjectId) return;
    setBusy(true);
    setMessage(null);
    try {
      const submitted = await submitTestCaseReview(selectedWorkspaceId, selectedProjectId, caseId, actorEmail);
      setMessage(`已提交评审：${submitted.title}`);
      await refreshCaseProject(selectedWorkspaceId, selectedProjectId, submitted.id);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "提交评审失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleReviewAction(action: CaseReviewAction) {
    if (!selectedWorkspaceId || !selectedProjectId || !selectedCaseId) return;
    setBusy(true);
    setMessage(null);
    try {
      await reviewTestCase(selectedWorkspaceId, selectedProjectId, selectedCaseId, actorEmail, {
        action,
        comment: reviewComment,
        edits: action === "edited" ? { title: editTitle } : undefined
      });
      setMessage(`已处理评审：${statusLabel[action] ?? action}`);
      await refreshCaseProject(selectedWorkspaceId, selectedProjectId, selectedCaseId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "评审操作失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleDirectEdit() {
    if (!selectedWorkspaceId || !selectedProjectId || !selectedCaseId) return;
    setBusy(true);
    setMessage(null);
    try {
      const updated = await updateTestCase(selectedWorkspaceId, selectedProjectId, selectedCaseId, actorEmail, { title: editTitle });
      setMessage(`已修改正式用例：${statusLabel[updated.status]}`);
      await refreshCaseProject(selectedWorkspaceId, selectedProjectId, updated.id);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "正式用例修改失败");
    } finally {
      setBusy(false);
    }
  }

  const selectedProject = projects.find((project) => project.id === selectedProjectId);
  const selectedCase = testCases.find((item) => item.id === selectedCaseId);
  const moduleById = new Map(modules.map((module) => [module.id, module]));

  return (
    <section className="section-block review-admin">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Case Review</span>
          <h2>用例评审治理</h2>
        </div>
        <ShieldCheck size={20} aria-hidden="true" />
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
          <span>
            {testCases.length} cases · {settings ? `self review ${settings.allow_self_review ? "on" : "off"} · update review ${settings.require_review_on_case_update ? "on" : "off"}` : "loading"}
          </span>
        </div>

        <div className="admin-grid">
          <section className="admin-pane" aria-label="评审策略">
            <div className="pane-heading">
              <div>
                <span className="eyebrow">Policy</span>
                <h3>评审策略</h3>
              </div>
              <Settings2 size={18} aria-hidden="true" />
            </div>
            <div className="stack-form">
              <label className="checkbox-label">
                <input type="checkbox" checked={allowSelfReview} onChange={(event) => setAllowSelfReview(event.target.checked)} />
                允许提交人自评审
              </label>
              <label className="checkbox-label">
                <input type="checkbox" checked={requireReviewOnUpdate} onChange={(event) => setRequireReviewOnUpdate(event.target.checked)} />
                正式用例修改后重新评审
              </label>
              <button className="ghost-button" type="button" onClick={() => void handleSettingsSave()} disabled={busy || !selectedWorkspaceId}>
                保存策略
              </button>
            </div>
          </section>

          <section className="admin-pane" aria-label="创建候选用例">
            <div className="pane-heading">
              <div>
                <span className="eyebrow">Candidate</span>
                <h3>候选用例</h3>
              </div>
              <Plus size={18} aria-hidden="true" />
            </div>
            <form className="stack-form" onSubmit={handleCreateCase}>
              <label>
                标题
                <input value={caseTitle} onChange={(event) => setCaseTitle(event.target.value)} required />
              </label>
              <label>
                模块
                <select value={caseModuleId} onChange={(event) => setCaseModuleId(event.target.value)}>
                  <option value="">未归属</option>
                  {modules.map((module) => (
                    <option value={module.id} key={module.id}>
                      {module.key} · {module.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                步骤
                <input value={caseSteps} onChange={(event) => setCaseSteps(event.target.value)} />
              </label>
              <label>
                预期
                <input value={caseExpected} onChange={(event) => setCaseExpected(event.target.value)} />
              </label>
              <div className="form-row">
                <label>
                  优先级
                  <input value={casePriority} onChange={(event) => setCasePriority(event.target.value)} />
                </label>
                <label>
                  风险
                  <input value={caseRisk} onChange={(event) => setCaseRisk(event.target.value)} />
                </label>
              </div>
              <label>
                标签
                <input value={caseTags} onChange={(event) => setCaseTags(event.target.value)} />
              </label>
              <label>
                自定义字段 JSON
                <input value={caseCustomFields} onChange={(event) => setCaseCustomFields(event.target.value)} />
              </label>
              <button className="ghost-button" type="submit" disabled={busy || !selectedWorkspaceId || !selectedProjectId}>
                创建候选
              </button>
            </form>
          </section>
        </div>

        <section className="audit-pane" aria-label="用例库治理列表">
          <div className="pane-heading">
            <div>
              <span className="eyebrow">Library</span>
              <h3>用例库</h3>
            </div>
            <ClipboardCheck size={18} aria-hidden="true" />
          </div>
          <div className="data-list">
            {testCasesPagination.currentItems.map((testCase) => (
              <div className="data-row module-row" key={testCase.id}>
                <div>
                  <strong>{testCase.title} · {statusLabel[testCase.status]}</strong>
                  <span>{moduleById.get(testCase.module_id ?? "")?.key ?? "未归属"} · rev {testCase.current_revision_number} · submitted {testCase.submitted_by || "none"}</span>
                  <small>{testCase.steps.join(" / ")} → {testCase.expected_result}</small>
                </div>
                <button className="ghost-button" type="button" onClick={() => void handleSelectCase(testCase.id)}>
                  查看
                </button>
                <button className="ghost-button" type="button" onClick={() => void handleSubmitCase(testCase.id)} disabled={busy}>
                  提交
                </button>
              </div>
            ))}
            {testCases.length === 0 ? <p className="empty-state">暂无用例</p> : null}
          </div>
          <Pagination
            currentPage={testCasesPagination.currentPage}
            totalPages={testCasesPagination.totalPages}
            totalItems={testCasesPagination.totalItems}
            onPageChange={testCasesPagination.goToPage}
          />
        </section>

        <div className="admin-grid">
          <section className="admin-pane" aria-label="评审操作">
            <div className="pane-heading">
              <div>
                <span className="eyebrow">Review</span>
                <h3>评审操作</h3>
              </div>
              <ShieldCheck size={18} aria-hidden="true" />
            </div>
            <div className="stack-form">
              <div className="admin-context compact-context">
                <strong>{selectedCase?.title ?? "尚未选择用例"}</strong>
                <span>{selectedCase ? `${statusLabel[selectedCase.status]} · rev ${selectedCase.current_revision_number}` : "从用例库选择一条候选或正式用例。"}</span>
              </div>
              <label>
                评论
                <input value={reviewComment} onChange={(event) => setReviewComment(event.target.value)} />
              </label>
              <label>
                编辑标题
                <input value={editTitle} onChange={(event) => setEditTitle(event.target.value)} />
              </label>
              <div className="form-row compact review-actions">
                <button className="ghost-button" type="button" onClick={() => void handleReviewAction("commented")} disabled={busy || !selectedCaseId}>
                  评论
                </button>
                <button className="ghost-button" type="button" onClick={() => void handleReviewAction("edited")} disabled={busy || !selectedCaseId}>
                  评审编辑
                </button>
                <button className="ghost-button" type="button" onClick={() => void handleReviewAction("changes_requested")} disabled={busy || !selectedCaseId}>
                  要求修改
                </button>
                <button className="ghost-button" type="button" onClick={() => void handleReviewAction("rejected")} disabled={busy || !selectedCaseId}>
                  驳回
                </button>
                <button className="primary-button small" type="button" onClick={() => void handleReviewAction("approved")} disabled={busy || !selectedCaseId}>
                  通过
                </button>
                <button className="ghost-button" type="button" onClick={() => void handleDirectEdit()} disabled={busy || !selectedCaseId}>
                  修改正式用例
                </button>
              </div>
            </div>
          </section>

          <section className="admin-pane" aria-label="评审历史">
            <div className="pane-heading">
              <div>
                <span className="eyebrow">Trace</span>
                <h3>评审和 Revision</h3>
              </div>
              <History size={18} aria-hidden="true" />
            </div>
            <div className="audit-list">
              {reviews.slice(0, 5).map((review) => (
                <div className="audit-row" key={review.id}>
                  <span>{statusLabel[review.action] ?? review.action}</span>
                  <strong>{review.comment || review.actor_email}</strong>
                  <small>{review.revision_id ? `revision ${review.revision_id.slice(0, 8)}` : review.actor_email}</small>
                </div>
              ))}
              {reviews.length === 0 ? <p className="empty-state">暂无评审记录</p> : null}
            </div>
            <div className="data-list">
              {revisions.slice(0, 5).map((revision) => (
                <div className="data-row wide" key={revision.id}>
                  <div>
                    <strong>Revision {revision.revision_number} · {revision.change_summary}</strong>
                    <span>{revision.created_by} · title {(revision.content_snapshot.title as string) ?? "unknown"}</span>
                  </div>
                </div>
              ))}
              {revisions.length === 0 ? <p className="empty-state">暂无 Revision</p> : null}
            </div>
          </section>
        </div>
      </div>
    </section>
  );
}
