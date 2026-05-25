import { FormEvent, useEffect, useMemo, useState } from "react";
import { Archive, FilePlus2, GitCompareArrows, History, RefreshCcw } from "lucide-react";
import { useParams } from "react-router-dom";
import {
  addressReviewChanges,
  CaseDraftRecord,
  CaseStep,
  createActiveEditDraft,
  createTestCase,
  getTestCase,
  listModules,
  listModuleTree,
  listProjects,
  listTestCases,
  listWorkspaces,
  ProjectModuleRecord,
  ProjectRecord,
  Session,
  submitCaseDraftReview,
  TestCasePayload,
  TestCaseRecord,
  updateCaseDraft,
  WorkspaceRecord
} from "../api";
import { CaseDraftEditor } from "../components/CaseDraftEditor";
import { CaseRevisionViewer } from "../components/CaseRevisionViewer";
import { CaseStatusBadge } from "../components/CaseStatusBadge";
import { ModuleTree } from "../components/ModuleTree";
import { ReviewStatusBadge } from "../components/ReviewStatusBadge";
import { StepsEditor } from "../components/StepsEditor";
import { statusLabel } from "../lib/labels";
import { pickExistingId } from "../lib/selection";

const detailTabs = ["基本信息", "草稿/正式", "对比", "评审记录", "版本历史", "来源血缘"] as const;

function normalizeSteps(value: unknown): CaseStep[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => {
    if (item && typeof item === "object" && !Array.isArray(item)) {
      const o = item as Record<string, unknown>;
      return { action: String(o.action ?? ""), expected: String(o.expected ?? "") };
    }
    return { action: String(item ?? ""), expected: "" };
  });
}

function draftOrRevision(caseRecord: TestCaseRecord) {
  const draft = caseRecord.active_draft;
  const snapshot = caseRecord.current_revision?.content_snapshot;
  return {
    title: draft?.title ?? String(snapshot?.title ?? caseRecord.title),
    steps: draft?.steps ?? normalizeSteps(snapshot?.steps),
    priority: draft?.priority ?? String(snapshot?.priority ?? "P2"),
    risk: draft?.risk ?? String(snapshot?.risk ?? "medium"),
    tags: draft?.tags ?? (Array.isArray(snapshot?.tags) ? snapshot.tags.map(String) : [])
  };
}

export function LibraryView({ session }: { session: Session }) {
  const actorEmail = session.user.email;
  const { wid: routeWorkspaceId = "", pid: routeProjectId = "" } = useParams<{ wid: string; pid: string }>();
  const [workspaces, setWorkspaces] = useState<WorkspaceRecord[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState("");
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [modules, setModules] = useState<ProjectModuleRecord[]>([]);
  const [moduleTree, setModuleTree] = useState<Awaited<ReturnType<typeof listModuleTree>>>([]);
  const [selectedModuleId, setSelectedModuleId] = useState("");
  const [cases, setCases] = useState<TestCaseRecord[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState("");
  const [selectedCase, setSelectedCase] = useState<TestCaseRecord | null>(null);
  const [lifecycleFilter, setLifecycleFilter] = useState<"" | TestCaseRecord["lifecycle_status"]>("");
  const [reviewFilter, setReviewFilter] = useState<"" | "pending_review" | "changes_requested">("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [priorityFilter, setPriorityFilter] = useState("");
  const [search, setSearch] = useState("");
  const [activeDetailTab, setActiveDetailTab] = useState<(typeof detailTabs)[number]>("基本信息");
  const [newTitle, setNewTitle] = useState("新的测试用例");
  const [newModuleId, setNewModuleId] = useState("");
  const [newSteps, setNewSteps] = useState<CaseStep[]>([
    { action: "打开目标功能", expected: "进入对应界面" },
    { action: "执行关键路径", expected: "行为符合预期" }
  ]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function refreshCaseDetail(workspaceId: string, projectId: string, caseId: string) {
    if (!caseId) {
      setSelectedCase(null);
      return;
    }
    const detail = await getTestCase(workspaceId, projectId, caseId);
    setSelectedCase(detail);
  }

  async function refreshCases(workspaceId: string, projectId: string, preferredCaseId?: string, moduleOverride = selectedModuleId) {
    const filters = {
      sourceType: sourceFilter || undefined,
      priority: priorityFilter || undefined,
      search: search || undefined
    };
    const [nextModules, nextTree, nextCases] = await Promise.all([
      listModules(workspaceId, projectId),
      listModuleTree(workspaceId, projectId),
      listTestCases(workspaceId, projectId, moduleOverride || undefined, reviewFilter || lifecycleFilter || undefined, filters)
    ]);
    setModules(nextModules);
    setModuleTree(nextTree);
    setCases(nextCases);
    if (!newModuleId && nextModules[0]) setNewModuleId(nextModules[0].id);
    const nextCaseId = pickExistingId(nextCases, preferredCaseId, selectedCaseId);
    setSelectedCaseId(nextCaseId);
    await refreshCaseDetail(workspaceId, projectId, nextCaseId);
  }

  async function refreshWorkspace(preferredWorkspaceId?: string, preferredProjectId?: string, preferredCaseId?: string) {
    setBusy(true);
    setMessage(null);
    try {
      const nextWorkspaces = await listWorkspaces(actorEmail);
      setWorkspaces(nextWorkspaces);
      const workspaceId = pickExistingId(nextWorkspaces, preferredWorkspaceId, selectedWorkspaceId);
      setSelectedWorkspaceId(workspaceId);
      if (!workspaceId) return;
      const nextProjects = await listProjects(workspaceId);
      setProjects(nextProjects);
      const projectId = pickExistingId(nextProjects, preferredProjectId, selectedProjectId);
      setSelectedProjectId(projectId);
      if (projectId) await refreshCases(workspaceId, projectId, preferredCaseId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "用例库加载失败");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void refreshWorkspace(routeWorkspaceId || undefined, routeProjectId || undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routeWorkspaceId, routeProjectId]);

  async function handleWorkspaceSwitch(workspaceId: string) {
    setSelectedWorkspaceId(workspaceId);
    const nextProjects = await listProjects(workspaceId);
    setProjects(nextProjects);
    const projectId = nextProjects[0]?.id ?? "";
    setSelectedProjectId(projectId);
    if (projectId) await refreshCases(workspaceId, projectId);
  }

  async function handleProjectSwitch(projectId: string) {
    setSelectedProjectId(projectId);
    if (selectedWorkspaceId && projectId) await refreshCases(selectedWorkspaceId, projectId);
  }

  async function handleCreateCase(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedWorkspaceId || !selectedProjectId) return;
    setBusy(true);
    setMessage(null);
    try {
      const payload: TestCasePayload = {
        module_id: newModuleId || null,
        title: newTitle,
        steps: newSteps.filter((step) => step.action.trim() || step.expected.trim()),
        priority: "P2",
        risk: "medium",
        tags: ["manual"],
        custom_fields: {}
      };
      const created = await createTestCase(selectedWorkspaceId, selectedProjectId, actorEmail, payload);
      setMessage(`已创建草稿：${created.title}`);
      await refreshCases(selectedWorkspaceId, selectedProjectId, created.id);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "创建用例失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleSelectCase(caseId: string) {
    setSelectedCaseId(caseId);
    if (selectedWorkspaceId && selectedProjectId) {
      await refreshCaseDetail(selectedWorkspaceId, selectedProjectId, caseId);
    }
  }

  async function saveDraft(draft: CaseDraftRecord, payload: Partial<TestCasePayload>) {
    if (!selectedWorkspaceId || !selectedProjectId) return;
    setBusy(true);
    setMessage(null);
    try {
      await updateCaseDraft(selectedWorkspaceId, selectedProjectId, draft.id, actorEmail, payload);
      setMessage("草稿已保存");
      await refreshCases(selectedWorkspaceId, selectedProjectId, draft.test_case_id);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "保存草稿失败");
    } finally {
      setBusy(false);
    }
  }

  async function submitDraft(draft: CaseDraftRecord) {
    if (!selectedWorkspaceId || !selectedProjectId) return;
    setBusy(true);
    setMessage(null);
    try {
      await submitCaseDraftReview(selectedWorkspaceId, selectedProjectId, draft.id, actorEmail);
      setMessage("已提交评审");
      await refreshCases(selectedWorkspaceId, selectedProjectId, draft.test_case_id);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "提交评审失败");
    } finally {
      setBusy(false);
    }
  }

  async function addressChanges(comment: string) {
    if (!selectedWorkspaceId || !selectedProjectId || !selectedCase?.open_cycle) return;
    setBusy(true);
    setMessage(null);
    try {
      await addressReviewChanges(selectedWorkspaceId, selectedProjectId, selectedCase.open_cycle.id, actorEmail, { comment });
      setMessage("已提交复审");
      await refreshCases(selectedWorkspaceId, selectedProjectId, selectedCase.id);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "提交复审失败");
    } finally {
      setBusy(false);
    }
  }

  async function createEditDraft() {
    if (!selectedWorkspaceId || !selectedProjectId || !selectedCase) return;
    setBusy(true);
    setMessage(null);
    try {
      await createActiveEditDraft(selectedWorkspaceId, selectedProjectId, selectedCase.id, actorEmail);
      setMessage("已创建正式用例编辑稿");
      await refreshCases(selectedWorkspaceId, selectedProjectId, selectedCase.id);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "创建编辑稿失败");
    } finally {
      setBusy(false);
    }
  }

  const selectedContent = selectedCase ? draftOrRevision(selectedCase) : null;
  const selectedProject = projects.find((project) => project.id === selectedProjectId);
  const moduleById = useMemo(() => new Map(modules.map((module) => [module.id, module])), [modules]);

  return (
    <section className="section-block case-library">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Case Library</span>
          <h2>用例库</h2>
        </div>
        <RefreshCcw size={20} aria-hidden="true" />
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
          <span>{cases.length} cases · 模块选择默认包含后代模块</span>
        </div>

        <form className="case-filter-bar" onSubmit={(event) => { event.preventDefault(); void refreshCases(selectedWorkspaceId, selectedProjectId); }}>
          <select value={lifecycleFilter} onChange={(event) => setLifecycleFilter(event.target.value as typeof lifecycleFilter)}>
            <option value="">全部资产</option>
            <option value="draft">草稿资产</option>
            <option value="active">正式资产</option>
            <option value="archived">归档资产</option>
          </select>
          <select value={reviewFilter} onChange={(event) => setReviewFilter(event.target.value as typeof reviewFilter)}>
            <option value="">全部评审</option>
            <option value="pending_review">待评审</option>
            <option value="changes_requested">要求修改</option>
          </select>
          <select value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value)}>
            <option value="">全部来源</option>
            <option value="manual">手工</option>
            <option value="import">导入</option>
            <option value="ai_suggestion">AI</option>
            <option value="active_edit">正式编辑</option>
          </select>
          <input value={priorityFilter} onChange={(event) => setPriorityFilter(event.target.value)} placeholder="优先级" />
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索标题" />
          <button className="ghost-button" type="submit" disabled={busy || !selectedWorkspaceId || !selectedProjectId}>
            筛选
          </button>
        </form>

        <div className="case-library-layout">
          <ModuleTree
            modules={moduleTree}
            selectedModuleId={selectedModuleId}
            onSelect={(moduleId) => {
              setSelectedModuleId(moduleId);
              void refreshCases(selectedWorkspaceId, selectedProjectId, undefined, moduleId);
            }}
          />

          <section className="case-list-panel" aria-label="用例列表">
            <div className="pane-heading">
              <div>
                <span className="eyebrow">Cases</span>
                <h3>用例列表</h3>
              </div>
              <FilePlus2 size={18} aria-hidden="true" />
            </div>
            <form className="stack-form compact-create" onSubmit={handleCreateCase}>
              <input value={newTitle} onChange={(event) => setNewTitle(event.target.value)} placeholder="新用例标题" required />
              <select value={newModuleId} onChange={(event) => setNewModuleId(event.target.value)}>
                <option value="">未归属</option>
                {modules.map((module) => (
                  <option value={module.id} key={module.id}>
                    {module.path_label}
                  </option>
                ))}
              </select>
              <StepsEditor steps={newSteps} onChange={setNewSteps} disabled={busy} />
              <button className="primary-button small" type="submit" disabled={busy || !selectedWorkspaceId || !selectedProjectId}>
                创建草稿
              </button>
            </form>
            <div className="data-list case-list">
              {cases.map((testCase) => (
                <button className={selectedCaseId === testCase.id ? "case-row active" : "case-row"} type="button" key={testCase.id} onClick={() => void handleSelectCase(testCase.id)}>
                  <strong>{testCase.title}</strong>
                  <span>{testCase.module_path_label || moduleById.get(testCase.module_id ?? "")?.path_label || "未归属"}</span>
                  <small>{statusLabel[testCase.lifecycle_status]} · {testCase.review_status ? statusLabel[testCase.review_status] : "无评审"} · rev {testCase.current_revision_number}</small>
                </button>
              ))}
              {cases.length === 0 ? <p className="empty-state">暂无用例</p> : null}
            </div>
          </section>

          <section className="case-detail-panel" aria-label="用例详情">
            {selectedCase && selectedContent ? (
              <>
                <div className="case-detail-head">
                  <div>
                    <span className="eyebrow">Detail</span>
                    <h3>{selectedContent.title}</h3>
                    <p>{selectedCase.module_path_label}</p>
                  </div>
                  <div className="case-badges">
                    <CaseStatusBadge status={selectedCase.lifecycle_status} />
                    <ReviewStatusBadge status={selectedCase.review_status} />
                  </div>
                </div>
                <div className="sub-tabs compact-tabs">
                  {detailTabs.map((tab) => (
                    <button className={activeDetailTab === tab ? "sub-tab active" : "sub-tab"} type="button" onClick={() => setActiveDetailTab(tab)} key={tab}>
                      {tab}
                    </button>
                  ))}
                </div>

                {activeDetailTab === "基本信息" ? (
                  <div className="case-content">
                    <div className="case-meta-grid">
                      <span>{selectedContent.priority}</span>
                      <span>{selectedContent.risk}</span>
                      <span>{selectedCase.source_type}</span>
                      <span>rev {selectedCase.current_revision_number}</span>
                    </div>
                    <ol className="step-list paired">
                      {selectedContent.steps.map((step, i) => (
                        <li key={i}>
                          <span className="step-action">{step.action || "(空步骤)"}</span>
                          {step.expected ? <span className="step-expected">→ {step.expected}</span> : null}
                        </li>
                      ))}
                    </ol>
                    <small>{selectedContent.tags.join(", ") || "无标签"}</small>
                  </div>
                ) : null}

                {activeDetailTab === "草稿/正式" ? (
                  selectedCase.active_draft ? (
                    <CaseDraftEditor
                      draft={selectedCase.active_draft}
                      modules={modules}
                      busy={busy}
                      onSave={(payload) => saveDraft(selectedCase.active_draft as CaseDraftRecord, payload)}
                      onSubmitReview={selectedCase.active_draft.draft_status === "editing" ? () => submitDraft(selectedCase.active_draft as CaseDraftRecord) : undefined}
                      onAddressChanges={selectedCase.review_status === "changes_requested" ? addressChanges : undefined}
                    />
                  ) : (
                    <div className="case-content">
                      <CaseRevisionViewer revision={selectedCase.current_revision} />
                      {selectedCase.lifecycle_status === "active" ? (
                        <button className="ghost-button" type="button" disabled={busy} onClick={() => void createEditDraft()}>
                          <GitCompareArrows size={16} aria-hidden="true" />
                          创建编辑稿
                        </button>
                      ) : null}
                    </div>
                  )
                ) : null}

                {activeDetailTab === "对比" ? (
                  <div className="comparison-grid">
                    <CaseRevisionViewer revision={selectedCase.current_revision} />
                    {selectedCase.active_draft ? (
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
                    ) : (
                      <p className="empty-state">暂无待对比草稿</p>
                    )}
                  </div>
                ) : null}

                {activeDetailTab === "评审记录" ? (
                  <div className="audit-list">
                    {(selectedCase.review_events ?? []).map((event) => (
                      <div className="audit-row" key={event.id}>
                        <span>{statusLabel[event.action] ?? event.action}</span>
                        <strong>{event.comment || event.actor_email}</strong>
                        <small>{event.actor_email} · {new Date(event.created_at).toLocaleString()}</small>
                      </div>
                    ))}
                    {(selectedCase.review_events ?? []).length === 0 ? <p className="empty-state">暂无评审记录</p> : null}
                  </div>
                ) : null}

                {activeDetailTab === "版本历史" ? (
                  <div className="data-list">
                    {(selectedCase.revisions ?? []).map((revision) => (
                      <div className="data-row wide" key={revision.id}>
                        <div>
                          <strong>Revision {revision.revision_number} · {revision.change_summary}</strong>
                          <span>{revision.module_path_label} · {revision.created_by}</span>
                        </div>
                      </div>
                    ))}
                    {(selectedCase.revisions ?? []).length === 0 ? <p className="empty-state">暂无版本</p> : null}
                  </div>
                ) : null}

                {activeDetailTab === "来源血缘" ? (
                  <div className="case-content">
                    <div className="case-meta-grid">
                      <span>{selectedCase.source_type}</span>
                      <span>{selectedCase.created_by}</span>
                      <span>{new Date(selectedCase.created_at).toLocaleDateString()}</span>
                      <span>{selectedCase.current_revision_id?.slice(0, 8) ?? "no revision"}</span>
                    </div>
                    <pre>{JSON.stringify(selectedCase.source_ref, null, 2)}</pre>
                  </div>
                ) : null}

                <div className="case-detail-actions">
                  {selectedCase.lifecycle_status === "active" ? (
                    <button className="ghost-button" type="button" disabled={busy}>
                      <Archive size={16} aria-hidden="true" />
                      归档
                    </button>
                  ) : null}
                  <button className="ghost-button" type="button" onClick={() => void refreshCaseDetail(selectedWorkspaceId, selectedProjectId, selectedCase.id)} disabled={busy}>
                    <History size={16} aria-hidden="true" />
                    刷新详情
                  </button>
                </div>
              </>
            ) : (
              <p className="empty-state">从左侧选择用例，或创建一条新草稿。</p>
            )}
          </section>
        </div>
      </div>
    </section>
  );
}
