import { useEffect, useState } from "react";
import { BrainCircuit, ClipboardCheck, History, PencilLine, Plus, Sparkles } from "lucide-react";
import {
  AISuggestionRecord,
  createCandidateFromSuggestion,
  createSuggestionPlanItems,
  DiffAnalysisRecord,
  listDiffAnalyses,
  generateAISuggestions,
  listAISuggestions,
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
  updateAISuggestion,
  WorkspaceRecord
} from "../api";
import { Pagination } from "../components/Pagination";
import { usePagination } from "../hooks/usePagination";
import { statusLabel, riskLabel, suggestionTypeLabel } from "../lib/labels";

export function AISuggestionAdmin({ session }: { session: Session }) {
  const actorEmail = session.user.email;
  const [workspaces, setWorkspaces] = useState<WorkspaceRecord[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState("");
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [analyses, setAnalyses] = useState<DiffAnalysisRecord[]>([]);
  const [selectedAnalysisId, setSelectedAnalysisId] = useState("");
  const [suggestions, setSuggestions] = useState<AISuggestionRecord[]>([]);
  const [selectedSuggestionId, setSelectedSuggestionId] = useState("");
  const [approvedCases, setApprovedCases] = useState<TestCaseRecord[]>([]);
  const [selectedCaseIds, setSelectedCaseIds] = useState<string[]>([]);
  const [plans, setPlans] = useState<TestPlanRecord[]>([]);
  const [selectedPlanId, setSelectedPlanId] = useState("");
  const [planItems, setPlanItems] = useState<PlanItemRecord[]>([]);
  const [feedbackText, setFeedbackText] = useState("Keep this recommendation");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const planItemsPagination = usePagination(planItems, 10);

  function compactList(items: string[], fallback: string): string {
    return items.length ? items.slice(0, 4).join(" · ") : fallback;
  }

  async function refreshSuggestionDetails(workspaceId: string, projectId: string, analysisId: string, preferredSuggestionId?: string) {
    if (!analysisId) {
      setSuggestions([]);
      setSelectedSuggestionId("");
      return;
    }
    const nextSuggestions = await listAISuggestions(workspaceId, projectId, analysisId);
    setSuggestions(nextSuggestions);
    const nextSuggestionId = preferredSuggestionId || selectedSuggestionId || nextSuggestions[0]?.id || "";
    setSelectedSuggestionId(nextSuggestionId);
    const nextSuggestion = nextSuggestions.find((item) => item.id === nextSuggestionId);
    setSelectedCaseIds(nextSuggestion?.selected_case_ids ?? []);
  }

  async function refreshPlanItems(workspaceId: string, projectId: string, planId: string) {
    if (!planId) {
      setPlanItems([]);
      return;
    }
    setPlanItems(await listPlanItems(workspaceId, projectId, planId));
  }

  async function refreshAIProject(workspaceId: string, projectId: string, preferredAnalysisId?: string, preferredSuggestionId?: string, preferredPlanId?: string) {
    const [nextAnalyses, nextCases, nextPlans] = await Promise.all([
      listDiffAnalyses(workspaceId, projectId),
      listTestCases(workspaceId, projectId, undefined, "approved"),
      listTestPlans(workspaceId, projectId)
    ]);
    setAnalyses(nextAnalyses);
    setApprovedCases(nextCases);
    setPlans(nextPlans);
    const nextAnalysisId = preferredAnalysisId || selectedAnalysisId || nextAnalyses[0]?.id || "";
    const nextPlanId = preferredPlanId || selectedPlanId || nextPlans[0]?.id || "";
    setSelectedAnalysisId(nextAnalysisId);
    setSelectedPlanId(nextPlanId);
    await refreshSuggestionDetails(workspaceId, projectId, nextAnalysisId, preferredSuggestionId);
    await refreshPlanItems(workspaceId, projectId, nextPlanId);
  }

  async function refreshAIWorkspaces(preferredWorkspaceId?: string, preferredProjectId?: string) {
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
        await refreshAIProject(nextWorkspaceId, nextProjectId);
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "AI 建议数据加载失败");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void refreshAIWorkspaces();
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
        await refreshAIProject(workspaceId, nextProjectId);
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "AI 建议 Workspace 切换失败");
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
      await refreshAIProject(selectedWorkspaceId, projectId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "AI 建议 Project 切换失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleAnalysisSwitch(analysisId: string) {
    setSelectedAnalysisId(analysisId);
    if (!selectedWorkspaceId || !selectedProjectId) return;
    setBusy(true);
    setMessage(null);
    try {
      await refreshSuggestionDetails(selectedWorkspaceId, selectedProjectId, analysisId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "AI 建议加载失败");
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

  function handleSelectSuggestion(suggestion: AISuggestionRecord) {
    setSelectedSuggestionId(suggestion.id);
    setSelectedCaseIds(suggestion.selected_case_ids);
  }

  async function handleGenerateSuggestions() {
    if (!selectedWorkspaceId || !selectedProjectId || !selectedAnalysisId) return;
    setBusy(true);
    setMessage(null);
    try {
      const nextSuggestions = await generateAISuggestions(selectedWorkspaceId, selectedProjectId, selectedAnalysisId, actorEmail);
      const firstSuggestion = nextSuggestions[0];
      setMessage(`已生成 AI 建议：${nextSuggestions.length} 条`);
      await refreshAIProject(selectedWorkspaceId, selectedProjectId, selectedAnalysisId, firstSuggestion?.id);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "AI 建议生成失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleFeedback(status: "accepted" | "ignored" | "modified") {
    if (!selectedWorkspaceId || !selectedProjectId || !selectedSuggestion) return;
    setBusy(true);
    setMessage(null);
    try {
      const updated = await updateAISuggestion(selectedWorkspaceId, selectedProjectId, selectedSuggestion.id, actorEmail, {
        status,
        feedback_comment: feedbackText,
        selected_case_ids: selectedSuggestion.suggestion_type === "regression" ? selectedCaseIds : undefined
      });
      setMessage(`已反馈建议：${statusLabel[updated.status]}`);
      await refreshAIProject(selectedWorkspaceId, selectedProjectId, selectedAnalysisId, updated.id, selectedPlanId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "AI 建议反馈失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateCandidate() {
    if (!selectedWorkspaceId || !selectedProjectId || !selectedSuggestion) return;
    setBusy(true);
    setMessage(null);
    try {
      const result = await createCandidateFromSuggestion(selectedWorkspaceId, selectedProjectId, selectedSuggestion.id, actorEmail);
      setMessage(`已创建 AI 候选草稿：${result.test_case.title}`);
      await refreshAIProject(selectedWorkspaceId, selectedProjectId, selectedAnalysisId, result.suggestion.id, selectedPlanId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "创建 AI 候选失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleCreatePlanItems(includeAICandidate: boolean) {
    if (!selectedWorkspaceId || !selectedProjectId || !selectedSuggestion || !selectedAnalysis) return;
    setBusy(true);
    setMessage(null);
    try {
      const result = await createSuggestionPlanItems(selectedWorkspaceId, selectedProjectId, selectedSuggestion.id, actorEmail, {
        plan_id: selectedPlanId || undefined,
        version_ref: selectedAnalysis.target_ref,
        test_case_ids: includeAICandidate ? [] : selectedCaseIds,
        include_ai_candidate: includeAICandidate
      });
      setMessage(`已加入计划：${result.items.length} 项`);
      await refreshAIProject(selectedWorkspaceId, selectedProjectId, selectedAnalysisId, result.suggestion.id, result.plan.id);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "加入计划失败");
    } finally {
      setBusy(false);
    }
  }

  const selectedProject = projects.find((project) => project.id === selectedProjectId);
  const selectedAnalysis = analyses.find((analysis) => analysis.id === selectedAnalysisId);
  const selectedSuggestion = suggestions.find((suggestion) => suggestion.id === selectedSuggestionId);
  const relatedCases = selectedSuggestion ? approvedCases.filter((testCase) => selectedSuggestion.related_case_ids.includes(testCase.id)) : [];

  return (
    <section className="section-block ai-suggestion-admin">
      <div className="section-heading">
        <div>
          <span className="eyebrow">AI Suggestions</span>
          <h2>Diff AI 测试建议</h2>
        </div>
        <BrainCircuit size={20} aria-hidden="true" />
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
          <span>{selectedAnalysis ? `${selectedAnalysis.base_ref} → ${selectedAnalysis.target_ref} · ${riskLabel[selectedAnalysis.risk_level]}` : "先运行 DiffAnalysis"}</span>
        </div>

        <div className="admin-grid">
          <section className="admin-pane" aria-label="生成 AI 测试建议">
            <div className="pane-heading">
              <div>
                <span className="eyebrow">Source Diff</span>
                <h3>生成建议</h3>
              </div>
              <Sparkles size={18} aria-hidden="true" />
            </div>
            <div className="stack-form">
              <label>
                DiffAnalysis
                <select value={selectedAnalysisId} onChange={(event) => void handleAnalysisSwitch(event.target.value)} disabled={busy || analyses.length === 0}>
                  <option value="">未选择</option>
                  {analyses.map((analysis) => (
                    <option value={analysis.id} key={analysis.id}>
                      {analysis.base_ref} → {analysis.target_ref} · {riskLabel[analysis.risk_level]}
                    </option>
                  ))}
                </select>
              </label>
              <button className="primary-button small" type="button" onClick={() => void handleGenerateSuggestions()} disabled={busy || !selectedAnalysisId}>
                生成 AI 建议
              </button>
              <span className="helper-copy">{suggestions.length} suggestions · {approvedCases.length} approved cases</span>
            </div>
          </section>

          <section className="admin-pane" aria-label="AI 建议人工反馈">
            <div className="pane-heading">
              <div>
                <span className="eyebrow">Human Feedback</span>
                <h3>反馈和采纳</h3>
              </div>
              <PencilLine size={18} aria-hidden="true" />
            </div>
            <div className="stack-form">
              <div className="admin-context compact-context">
                <strong>{selectedSuggestion?.title ?? "尚未选择建议"}</strong>
                <span>{selectedSuggestion ? `${statusLabel[selectedSuggestion.status]} · confidence ${selectedSuggestion.confidence}%` : "从建议列表选择一条。"}</span>
              </div>
              <label>
                反馈
                <input value={feedbackText} onChange={(event) => setFeedbackText(event.target.value)} />
              </label>
              <div className="form-row compact ai-action-row">
                <button className="ghost-button" type="button" onClick={() => void handleFeedback("accepted")} disabled={busy || !selectedSuggestion}>
                  采纳
                </button>
                <button className="ghost-button" type="button" onClick={() => void handleFeedback("modified")} disabled={busy || !selectedSuggestion}>
                  标记修改
                </button>
                <button className="ghost-button" type="button" onClick={() => void handleFeedback("ignored")} disabled={busy || !selectedSuggestion}>
                  忽略
                </button>
              </div>
            </div>
          </section>
        </div>

        <section className="audit-pane" aria-label="AI 建议列表">
          <div className="pane-heading">
            <div>
              <span className="eyebrow">Suggestions</span>
              <h3>建议、理由和证据</h3>
            </div>
            <BrainCircuit size={18} aria-hidden="true" />
          </div>
          <div className="data-list">
            {suggestions.map((suggestion) => (
              <div className="data-row module-row" key={suggestion.id}>
                <div>
                  <strong>{suggestion.title} · {suggestionTypeLabel[suggestion.suggestion_type]}</strong>
                  <span>{suggestion.module_key} · confidence {suggestion.confidence}% · {statusLabel[suggestion.status]}</span>
                  <small>{suggestion.rationale}</small>
                  <small>{compactList([...suggestion.interfaces, ...suggestion.config_keys, ...suggestion.code_paths], "暂无结构证据")}</small>
                </div>
                <button className="ghost-button" type="button" onClick={() => handleSelectSuggestion(suggestion)}>
                  查看
                </button>
              </div>
            ))}
            {suggestions.length === 0 ? <p className="empty-state">暂无 AI 建议</p> : null}
          </div>
        </section>

        <div className="admin-grid">
          <section className="admin-pane" aria-label="选择正式回归用例">
            <div className="pane-heading">
              <div>
                <span className="eyebrow">Formal Cases</span>
                <h3>推荐回归用例</h3>
              </div>
              <ClipboardCheck size={18} aria-hidden="true" />
            </div>
            <div className="stack-form">
              {relatedCases.map((testCase) => (
                <label className="checkbox-label" key={testCase.id}>
                  <input
                    type="checkbox"
                    checked={selectedCaseIds.includes(testCase.id)}
                    onChange={(event) => {
                      setSelectedCaseIds((current) =>
                        event.target.checked ? [...new Set([...current, testCase.id])] : current.filter((id) => id !== testCase.id)
                      );
                    }}
                  />
                  {testCase.title}
                </label>
              ))}
              {relatedCases.length === 0 ? <p className="empty-state">当前建议没有命中正式用例</p> : null}
              <button className="ghost-button" type="button" onClick={() => void handleCreatePlanItems(false)} disabled={busy || !selectedSuggestion || selectedSuggestion.suggestion_type !== "regression" || selectedCaseIds.length === 0}>
                回归用例入计划
              </button>
            </div>
          </section>

          <section className="admin-pane" aria-label="AI 候选用例和临时计划项">
            <div className="pane-heading">
              <div>
                <span className="eyebrow">Candidate</span>
                <h3>AI 候选和临时项</h3>
              </div>
              <Plus size={18} aria-hidden="true" />
            </div>
            <div className="stack-form">
              <div className="admin-context compact-context">
                <strong>{selectedSuggestion?.candidate_payload?.title ?? "选择 AI 候选建议"}</strong>
                <span>{selectedSuggestion?.candidate_case_id ? "已创建候选草稿" : "正式入库前必须提交并通过评审。"}</span>
              </div>
              <button className="ghost-button" type="button" onClick={() => void handleCreateCandidate()} disabled={busy || !selectedSuggestion || selectedSuggestion.suggestion_type !== "case_candidate"}>
                创建候选草稿
              </button>
              <button className="primary-button small" type="button" onClick={() => void handleCreatePlanItems(true)} disabled={busy || !selectedSuggestion || selectedSuggestion.suggestion_type !== "case_candidate"}>
                加入临时计划项
              </button>
            </div>
          </section>
        </div>

        <section className="audit-pane" aria-label="AI 建议计划项">
          <div className="pane-heading">
            <div>
              <span className="eyebrow">Plan Items</span>
              <h3>建议沉淀到计划</h3>
            </div>
            <History size={18} aria-hidden="true" />
          </div>
          <div className="admin-toolbar">
            <label className="select-label">
              当前 TestPlan
              <select value={selectedPlanId} onChange={(event) => void handlePlanSwitch(event.target.value)} disabled={busy || plans.length === 0}>
                <option value="">自动创建 release plan</option>
                {plans.map((plan) => (
                  <option value={plan.id} key={plan.id}>
                    {plan.name} · {plan.version_ref || "no version"}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="data-list">
            {planItemsPagination.currentItems.map((item) => (
              <div className="data-row wide" key={item.id}>
                <div>
                  <strong>{item.title} · {statusLabel[item.source_type]}</strong>
                  <span>{statusLabel[item.status]} · source {item.source_id?.slice(0, 8) ?? "none"}</span>
                  <small>{item.rationale}</small>
                </div>
              </div>
            ))}
            {planItems.length === 0 ? <p className="empty-state">暂无计划项</p> : null}
          </div>
          <Pagination
            currentPage={planItemsPagination.currentPage}
            totalPages={planItemsPagination.totalPages}
            totalItems={planItemsPagination.totalItems}
            onPageChange={planItemsPagination.goToPage}
          />
        </section>
      </div>
    </section>
  );
}
