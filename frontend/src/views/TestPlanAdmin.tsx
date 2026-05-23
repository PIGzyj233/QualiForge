import { FormEvent, useEffect, useMemo, useState } from "react";
import { CheckCircle2, ClipboardCheck, FileText, History, Plus } from "lucide-react";
import {
  createPlanItem,
  createTestPlan,
  listPlanItems,
  listProjects,
  listTestPlans,
  listTestCases,
  listWorkspaces,
  ProjectRecord,
  PlanItemRecord,
  Session,
  TestPlanRecord,
  TestCaseRecord,
  updatePlanItemExecution,
  uploadPlanItemEvidence,
  WorkspaceRecord
} from "../api";
import { Pagination } from "../components/Pagination";
import { usePagination } from "../hooks/usePagination";
import { statusLabel, executionStatuses, ExecutionStatus } from "../lib/labels";

export function TestPlanAdmin({ session }: { session: Session }) {
  const actorEmail = session.user.email;
  const [workspaces, setWorkspaces] = useState<WorkspaceRecord[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState("");
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [plans, setPlans] = useState<TestPlanRecord[]>([]);
  const [selectedPlanId, setSelectedPlanId] = useState("");
  const [planItems, setPlanItems] = useState<PlanItemRecord[]>([]);
  const [approvedCases, setApprovedCases] = useState<TestCaseRecord[]>([]);
  const [planName, setPlanName] = useState("Release plan v2");
  const [planType, setPlanType] = useState<TestPlanRecord["plan_type"]>("release");
  const [versionRef, setVersionRef] = useState("v2");
  const [scopeSummary, setScopeSummary] = useState("Checkout payment and refund scope");
  const [ownerEmail, setOwnerEmail] = useState(session.user.email);
  const [itemSourceType, setItemSourceType] = useState<PlanItemRecord["source_type"]>("formal_case");
  const [selectedCaseId, setSelectedCaseId] = useState("");
  const [itemTitle, setItemTitle] = useState("Manual payment observability check");
  const [itemRationale, setItemRationale] = useState("Release scope item");
  const [itemSnapshot, setItemSnapshot] = useState("{\"steps\":[\"Open dashboard\",\"Verify payment metrics\"]}");
  const [executionFilter, setExecutionFilter] = useState<"all" | "failed_blocked" | ExecutionStatus>("all");
  const [selectedExecutionItemId, setSelectedExecutionItemId] = useState("");
  const [executionStatus, setExecutionStatus] = useState<ExecutionStatus>("not_run");
  const [executionAssignee, setExecutionAssignee] = useState(session.user.email);
  const [actualResult, setActualResult] = useState("");
  const [failureReason, setFailureReason] = useState("");
  const [defectLinksText, setDefectLinksText] = useState("");
  const [evidenceFile, setEvidenceFile] = useState<File | null>(null);
  const [evidenceNote, setEvidenceNote] = useState("Execution evidence");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  function setExecutionFormFromItem(item: PlanItemRecord | undefined) {
    if (!item) {
      setSelectedExecutionItemId("");
      setExecutionStatus("not_run");
      setExecutionAssignee(session.user.email);
      setActualResult("");
      setFailureReason("");
      setDefectLinksText("");
      return;
    }
    setSelectedExecutionItemId(item.id);
    setExecutionStatus(executionStatuses.includes(item.status as ExecutionStatus) ? (item.status as ExecutionStatus) : "not_run");
    setExecutionAssignee(item.assignee_email || session.user.email);
    setActualResult(item.actual_result);
    setFailureReason(item.failure_reason);
    setDefectLinksText(item.defect_links.join("\n"));
  }

  async function refreshPlanItems(workspaceId: string, projectId: string, planId: string) {
    if (!planId) {
      setPlanItems([]);
      setExecutionFormFromItem(undefined);
      return;
    }
    const nextItems = await listPlanItems(workspaceId, projectId, planId);
    setPlanItems(nextItems);
    setExecutionFormFromItem(nextItems.find((item) => item.id === selectedExecutionItemId) ?? nextItems[0]);
  }

  async function refreshPlanProject(workspaceId: string, projectId: string, preferredPlanId?: string) {
    const [nextPlans, nextCases] = await Promise.all([
      listTestPlans(workspaceId, projectId),
      listTestCases(workspaceId, projectId, undefined, "approved")
    ]);
    setPlans(nextPlans);
    setApprovedCases(nextCases);
    const nextPlanId = preferredPlanId || selectedPlanId || nextPlans[0]?.id || "";
    setSelectedPlanId(nextPlanId);
    if (!selectedCaseId && nextCases[0]) {
      setSelectedCaseId(nextCases[0].id);
    }
    await refreshPlanItems(workspaceId, projectId, nextPlanId);
  }

  async function refreshPlanWorkspaces(preferredWorkspaceId?: string, preferredProjectId?: string) {
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
        await refreshPlanProject(nextWorkspaceId, nextProjectId);
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "测试计划加载失败");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void refreshPlanWorkspaces();
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
        await refreshPlanProject(workspaceId, nextProjectId);
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "测试计划 Workspace 切换失败");
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
      await refreshPlanProject(selectedWorkspaceId, projectId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "测试计划 Project 切换失败");
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
      await refreshPlanItems(selectedWorkspaceId, selectedProjectId, planId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "计划项加载失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleCreatePlan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedWorkspaceId || !selectedProjectId) return;
    setBusy(true);
    setMessage(null);
    try {
      const plan = await createTestPlan(selectedWorkspaceId, selectedProjectId, actorEmail, {
        name: planName,
        plan_type: planType,
        scope_summary: scopeSummary,
        version_ref: versionRef,
        owner_email: ownerEmail
      });
      setMessage(`已创建测试计划：${plan.name}`);
      await refreshPlanProject(selectedWorkspaceId, selectedProjectId, plan.id);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "测试计划创建失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleCreatePlanItem(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedWorkspaceId || !selectedProjectId || !selectedPlanId) return;
    setBusy(true);
    setMessage(null);
    try {
      const snapshot = itemSourceType === "formal_case" ? undefined : (JSON.parse(itemSnapshot || "{}") as Record<string, unknown>);
      const item = await createPlanItem(selectedWorkspaceId, selectedProjectId, selectedPlanId, actorEmail, {
        source_type: itemSourceType,
        source_id: itemSourceType === "formal_case" ? selectedCaseId : itemSourceType === "ai_temp" ? "manual-ai-temp" : null,
        title: itemSourceType === "formal_case" ? undefined : itemTitle,
        snapshot,
        rationale: itemRationale
      });
      setMessage(`已加入计划项：${item.title}`);
      await refreshPlanProject(selectedWorkspaceId, selectedProjectId, selectedPlanId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "计划项创建失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveExecution(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedWorkspaceId || !selectedProjectId || !selectedPlanId || !selectedExecutionItemId) return;
    setBusy(true);
    setMessage(null);
    try {
      const updated = await updatePlanItemExecution(selectedWorkspaceId, selectedProjectId, selectedPlanId, selectedExecutionItemId, actorEmail, {
        status: executionStatus,
        assignee_email: executionAssignee,
        actual_result: actualResult,
        failure_reason: failureReason,
        defect_links: defectLinksText
          .split(/\r?\n|,/)
          .map((link) => link.trim())
          .filter(Boolean)
      });
      setMessage(`已保存执行结果：${updated.title} · ${statusLabel[updated.status]}`);
      setExecutionFormFromItem(updated);
      await refreshPlanProject(selectedWorkspaceId, selectedProjectId, selectedPlanId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "执行结果保存失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleUploadEvidence(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedWorkspaceId || !selectedProjectId || !selectedPlanId || !selectedExecutionItemId || !evidenceFile) return;
    setBusy(true);
    setMessage(null);
    try {
      const updated = await uploadPlanItemEvidence(selectedWorkspaceId, selectedProjectId, selectedPlanId, selectedExecutionItemId, actorEmail, evidenceFile, evidenceNote);
      setMessage(`已上传证据：${evidenceFile.name}`);
      setEvidenceFile(null);
      setExecutionFormFromItem(updated);
      await refreshPlanProject(selectedWorkspaceId, selectedProjectId, selectedPlanId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "证据上传失败");
    } finally {
      setBusy(false);
    }
  }

  const selectedProject = projects.find((project) => project.id === selectedProjectId);
  const selectedPlan = plans.find((plan) => plan.id === selectedPlanId);
  const selectedExecutionItem = planItems.find((item) => item.id === selectedExecutionItemId);
  const filteredPlanItems = useMemo(() => {
    if (executionFilter === "all") return planItems;
    if (executionFilter === "failed_blocked") return planItems.filter((item) => item.status === "failed" || item.status === "blocked");
    return planItems.filter((item) => item.status === executionFilter);
  }, [executionFilter, planItems]);
  const planItemsPagination = usePagination(filteredPlanItems, 10);
  const planProgress = useMemo(() => {
    const counts = { total: planItems.length, not_run: 0, passed: 0, failed: 0, blocked: 0, skipped: 0 };
    for (const item of planItems) {
      const status = item.status === "todo" || item.status === "in_progress" ? "not_run" : item.status;
      if (status in counts) {
        counts[status as keyof typeof counts] += 1;
      }
    }
    const finished = counts.passed + counts.failed + counts.blocked + counts.skipped;
    return { ...counts, finished, percent: counts.total ? Math.round((finished / counts.total) * 100) : 0 };
  }, [planItems]);
  const selectedSteps = Array.isArray(selectedExecutionItem?.snapshot.steps)
    ? selectedExecutionItem.snapshot.steps.map((step) => String(step))
    : typeof selectedExecutionItem?.snapshot.steps === "string"
      ? selectedExecutionItem.snapshot.steps.split(/\r?\n/).filter(Boolean)
      : [];

  return (
    <section className="section-block test-plan-admin">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Test Planning</span>
          <h2>发布测试计划</h2>
        </div>
        <ClipboardCheck size={20} aria-hidden="true" />
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
          <span>{selectedPlan ? `${selectedPlan.name} · ${statusLabel[selectedPlan.plan_type]} · ${statusLabel[selectedPlan.status]}` : "创建 release 测试计划后添加范围项"}</span>
        </div>

        <div className="admin-grid">
          <section className="admin-pane" aria-label="创建测试计划">
            <div className="pane-heading">
              <div>
                <span className="eyebrow">Plan</span>
                <h3>创建计划</h3>
              </div>
              <Plus size={18} aria-hidden="true" />
            </div>
            <form className="stack-form" onSubmit={handleCreatePlan}>
              <label>
                名称
                <input value={planName} onChange={(event) => setPlanName(event.target.value)} required />
              </label>
              <div className="form-row">
                <label>
                  类型
                  <select value={planType} onChange={(event) => setPlanType(event.target.value as TestPlanRecord["plan_type"])}>
                    {(["release", "regression", "smoke", "feature", "custom"] as TestPlanRecord["plan_type"][]).map((item) => (
                      <option value={item} key={item}>
                        {statusLabel[item]}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  版本
                  <input value={versionRef} onChange={(event) => setVersionRef(event.target.value)} />
                </label>
              </div>
              <label>
                范围
                <input value={scopeSummary} onChange={(event) => setScopeSummary(event.target.value)} />
              </label>
              <label>
                Owner
                <input value={ownerEmail} onChange={(event) => setOwnerEmail(event.target.value)} />
              </label>
              <button className="primary-button small" type="submit" disabled={busy || !selectedWorkspaceId || !selectedProjectId}>
                创建计划
              </button>
            </form>
          </section>

          <section className="admin-pane" aria-label="添加计划项">
            <div className="pane-heading">
              <div>
                <span className="eyebrow">Scope</span>
                <h3>添加范围项</h3>
              </div>
              <FileText size={18} aria-hidden="true" />
            </div>
            <form className="stack-form" onSubmit={handleCreatePlanItem}>
              <label>
                当前计划
                <select value={selectedPlanId} onChange={(event) => void handlePlanSwitch(event.target.value)} disabled={busy || plans.length === 0}>
                  <option value="">未选择</option>
                  {plans.map((plan) => (
                    <option value={plan.id} key={plan.id}>
                      {plan.name} · {statusLabel[plan.plan_type]}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                来源
                <select value={itemSourceType} onChange={(event) => setItemSourceType(event.target.value as PlanItemRecord["source_type"])}>
                  <option value="formal_case">正式用例快照</option>
                  <option value="ai_temp">AI 临时建议</option>
                  <option value="manual">手工临时项</option>
                </select>
              </label>
              {itemSourceType === "formal_case" ? (
                <label>
                  正式用例
                  <select value={selectedCaseId} onChange={(event) => setSelectedCaseId(event.target.value)} disabled={approvedCases.length === 0}>
                    <option value="">未选择</option>
                    {approvedCases.map((testCase) => (
                      <option value={testCase.id} key={testCase.id}>
                        {testCase.title}
                      </option>
                    ))}
                  </select>
                </label>
              ) : (
                <>
                  <label>
                    标题
                    <input value={itemTitle} onChange={(event) => setItemTitle(event.target.value)} />
                  </label>
                  <label>
                    Snapshot JSON
                    <input value={itemSnapshot} onChange={(event) => setItemSnapshot(event.target.value)} />
                  </label>
                </>
              )}
              <label>
                依据
                <input value={itemRationale} onChange={(event) => setItemRationale(event.target.value)} />
              </label>
              <button className="ghost-button" type="submit" disabled={busy || !selectedPlanId || (itemSourceType === "formal_case" && !selectedCaseId)}>
                加入计划项
              </button>
            </form>
          </section>
        </div>

        <section className="audit-pane" aria-label="测试计划列表">
          <div className="pane-heading">
            <div>
              <span className="eyebrow">Plans</span>
              <h3>计划列表</h3>
            </div>
            <History size={18} aria-hidden="true" />
          </div>
          <div className="data-list">
            {plans.map((plan) => (
              <div className="data-row module-row" key={plan.id}>
                <div>
                  <strong>{plan.name} · {statusLabel[plan.plan_type]}</strong>
                  <span>{plan.version_ref || "no version"} · owner {plan.owner_email} · {statusLabel[plan.status]}</span>
                  <small>{plan.scope_summary || "无范围说明"} · conclusion {plan.final_conclusion || "pending"}</small>
                </div>
                <button className="ghost-button" type="button" onClick={() => void handlePlanSwitch(plan.id)}>
                  查看
                </button>
              </div>
            ))}
            {plans.length === 0 ? <p className="empty-state">暂无测试计划</p> : null}
          </div>
        </section>

        <section className="audit-pane" aria-label="测试计划项">
          <div className="pane-heading">
            <div>
              <span className="eyebrow">Plan Items</span>
              <h3>执行范围快照</h3>
            </div>
            <ClipboardCheck size={18} aria-hidden="true" />
          </div>
          <div className="execution-summary">
            <strong>{planProgress.percent}%</strong>
            <span>
              {planProgress.finished}/{planProgress.total} 已记录 · {planProgress.passed} 通过 · {planProgress.failed} 失败 · {planProgress.blocked} 阻塞 · {planProgress.not_run} 未执行
            </span>
            <label className="select-label">
              筛选
              <select value={executionFilter} onChange={(event) => setExecutionFilter(event.target.value as typeof executionFilter)}>
                <option value="all">全部</option>
                <option value="failed_blocked">失败或阻塞</option>
                {executionStatuses.map((status) => (
                  <option value={status} key={status}>
                    {statusLabel[status]}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="data-list">
            {planItemsPagination.currentItems.map((item) => (
              <div className="data-row module-row" key={item.id}>
                <div>
                  <strong>{item.title} · {statusLabel[item.source_type]}</strong>
                  <span>{statusLabel[item.status] ?? item.status} · assignee {item.assignee_email || "unassigned"} · source {item.source_id?.slice(0, 8) ?? "none"}</span>
                  <small>
                    {item.rationale || "无依据"} · evidence {item.evidence.length} · defects {item.defect_links.length} · executed {item.executed_at ? new Date(item.executed_at).toLocaleString() : "pending"}
                  </small>
                </div>
                <button className="ghost-button" type="button" onClick={() => setExecutionFormFromItem(item)}>
                  执行
                </button>
              </div>
            ))}
            {filteredPlanItems.length === 0 ? <p className="empty-state">暂无匹配计划项</p> : null}
          </div>
          <Pagination
            currentPage={planItemsPagination.currentPage}
            totalPages={planItemsPagination.totalPages}
            totalItems={planItemsPagination.totalItems}
            onPageChange={planItemsPagination.goToPage}
          />
        </section>

        <section className="audit-pane execution-pane" aria-label="单项执行">
          <div className="pane-heading">
            <div>
              <span className="eyebrow">Execution</span>
              <h3>单项执行</h3>
            </div>
            <CheckCircle2 size={18} aria-hidden="true" />
          </div>
          {selectedExecutionItem ? (
            <div className="execution-detail">
              <div className="execution-card">
                <strong>{selectedExecutionItem.title}</strong>
                <span>{statusLabel[selectedExecutionItem.source_type]} · {statusLabel[selectedExecutionItem.status] ?? selectedExecutionItem.status}</span>
                <small>{String(selectedExecutionItem.snapshot.expected_result ?? selectedExecutionItem.snapshot.interfaces ?? "查看步骤并录入执行结果")}</small>
                {selectedSteps.length > 0 ? (
                  <ol className="step-list">
                    {selectedSteps.map((step, index) => (
                      <li key={`${selectedExecutionItem.id}-${index}`}>{step}</li>
                    ))}
                  </ol>
                ) : null}
              </div>

              <form className="stack-form" onSubmit={handleSaveExecution}>
                <div className="form-row">
                  <label>
                    执行人
                    <input value={executionAssignee} onChange={(event) => setExecutionAssignee(event.target.value)} />
                  </label>
                  <label>
                    状态
                    <select value={executionStatus} onChange={(event) => setExecutionStatus(event.target.value as ExecutionStatus)}>
                      {executionStatuses.map((status) => (
                        <option value={status} key={status}>
                          {statusLabel[status]}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <label>
                  实际结果
                  <textarea value={actualResult} onChange={(event) => setActualResult(event.target.value)} rows={3} />
                </label>
                <label>
                  失败原因
                  <textarea value={failureReason} onChange={(event) => setFailureReason(event.target.value)} rows={2} />
                </label>
                <label>
                  缺陷链接
                  <textarea value={defectLinksText} onChange={(event) => setDefectLinksText(event.target.value)} rows={2} />
                </label>
                <button className="primary-button small" type="submit" disabled={busy || !selectedExecutionItemId}>
                  保存执行结果
                </button>
              </form>

              <form className="stack-form evidence-form" onSubmit={handleUploadEvidence}>
                <div className="form-row">
                  <label>
                    证据文件
                    <input type="file" onChange={(event) => setEvidenceFile(event.target.files?.[0] ?? null)} />
                  </label>
                  <label>
                    说明
                    <input value={evidenceNote} onChange={(event) => setEvidenceNote(event.target.value)} />
                  </label>
                </div>
                <button className="ghost-button" type="submit" disabled={busy || !selectedExecutionItemId || !evidenceFile}>
                  上传证据
                </button>
              </form>

              <div className="data-list">
                {selectedExecutionItem.evidence.map((item) => (
                  <div className="data-row wide" key={item.id}>
                    <div>
                      <strong>{item.file_name}</strong>
                      <span>{item.note || "无说明"} · {Math.round(item.size_bytes / 1024)} KB · {item.uploaded_by}</span>
                    </div>
                  </div>
                ))}
                {selectedExecutionItem.evidence.length === 0 ? <p className="empty-state">暂无执行证据</p> : null}
              </div>
            </div>
          ) : (
            <p className="empty-state">选择计划项后录入执行结果</p>
          )}
        </section>
      </div>
    </section>
  );
}
