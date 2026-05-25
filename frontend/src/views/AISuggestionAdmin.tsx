import { useEffect, useState } from "react";
import { BrainCircuit, CheckCircle2, ChevronRight, ClipboardCheck, MessageSquare, Plus, Sparkles, XCircle } from "lucide-react";
import {
  AISuggestionRecord,
  createCandidateFromSuggestion,
  createSuggestionPlanItems,
  DiffAnalysisRecord,
  listDiffAnalyses,
  generateAISuggestions,
  listAISuggestions,
  listTestPlans,
  listTestCases,
  PlanItemRecord,
  Session,
  TestPlanRecord,
  TestCaseRecord,
  updateAISuggestion
} from "../api";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";
import { statusLabel, riskLabel, suggestionTypeLabel } from "../lib/labels";

export function AISuggestionAdmin(_: { session: Session }) {
  const { actorEmail, currentWorkspace, currentProject } = useWorkspaceContext();
  const wid = currentWorkspace?.id ?? "";
  const pid = currentProject?.id ?? "";

  const [analyses, setAnalyses] = useState<DiffAnalysisRecord[]>([]);
  const [selectedAnalysisId, setSelectedAnalysisId] = useState("");
  const [suggestions, setSuggestions] = useState<AISuggestionRecord[]>([]);
  const [selectedSuggestionId, setSelectedSuggestionId] = useState("");
  const [approvedCases, setApprovedCases] = useState<TestCaseRecord[]>([]);
  const [selectedCaseIds, setSelectedCaseIds] = useState<string[]>([]);
  const [plans, setPlans] = useState<TestPlanRecord[]>([]);
  const [selectedPlanId, setSelectedPlanId] = useState("");
  const [feedbackText, setFeedbackText] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [recentPlanItems, setRecentPlanItems] = useState<PlanItemRecord[]>([]);

  const selectedAnalysis = analyses.find((a) => a.id === selectedAnalysisId);
  const selectedSuggestion = suggestions.find((s) => s.id === selectedSuggestionId);
  const relatedCases = selectedSuggestion
    ? approvedCases.filter((c) => selectedSuggestion.related_case_ids.includes(c.id))
    : [];

  async function loadProjectData() {
    if (!wid || !pid) {
      setAnalyses([]);
      setApprovedCases([]);
      setPlans([]);
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      const [nextAnalyses, nextCases, nextPlans] = await Promise.all([
        listDiffAnalyses(wid, pid),
        listTestCases(wid, pid, undefined, "approved"),
        listTestPlans(wid, pid)
      ]);
      setAnalyses(nextAnalyses);
      setApprovedCases(nextCases);
      setPlans(nextPlans);
      const aid = nextAnalyses[0]?.id ?? "";
      setSelectedAnalysisId(aid);
      const planId = nextPlans[0]?.id ?? "";
      setSelectedPlanId(planId);
      if (aid) await loadSuggestions(aid);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "AI 智能推荐数据加载失败");
    } finally {
      setBusy(false);
    }
  }

  async function loadSuggestions(analysisId: string) {
    if (!wid || !pid || !analysisId) {
      setSuggestions([]);
      setSelectedSuggestionId("");
      return;
    }
    const list = await listAISuggestions(wid, pid, analysisId);
    setSuggestions(list);
    const sid = list[0]?.id ?? "";
    setSelectedSuggestionId(sid);
    setSelectedCaseIds(list.find((s) => s.id === sid)?.selected_case_ids ?? []);
  }

  useEffect(() => {
    void loadProjectData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wid, pid]);

  function pickSuggestion(s: AISuggestionRecord) {
    setSelectedSuggestionId(s.id);
    setSelectedCaseIds(s.selected_case_ids);
    setFeedbackText("");
  }

  async function generate() {
    if (!wid || !pid || !selectedAnalysisId) return;
    setBusy(true);
    setMessage(null);
    try {
      const next = await generateAISuggestions(wid, pid, selectedAnalysisId, actorEmail);
      setMessage(`已生成 ${next.length} 条建议`);
      await loadSuggestions(selectedAnalysisId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "AI 建议生成失败");
    } finally {
      setBusy(false);
    }
  }

  async function feedback(status: "accepted" | "ignored" | "modified") {
    if (!wid || !pid || !selectedSuggestion) return;
    setBusy(true);
    setMessage(null);
    try {
      const updated = await updateAISuggestion(wid, pid, selectedSuggestion.id, actorEmail, {
        status,
        feedback_comment: feedbackText || undefined,
        selected_case_ids: selectedSuggestion.suggestion_type === "regression" ? selectedCaseIds : undefined
      });
      setMessage(`已反馈：${statusLabel[updated.status]}`);
      await loadSuggestions(selectedAnalysisId);
      pickSuggestion(updated);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "AI 建议反馈失败");
    } finally {
      setBusy(false);
    }
  }

  async function createCandidate() {
    if (!wid || !pid || !selectedSuggestion) return;
    setBusy(true);
    try {
      const result = await createCandidateFromSuggestion(wid, pid, selectedSuggestion.id, actorEmail);
      setMessage(`已创建 AI 候选草稿 "${result.test_case.title}"`);
      await loadSuggestions(selectedAnalysisId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "创建 AI 候选失败");
    } finally {
      setBusy(false);
    }
  }

  async function addToPlan(includeAICandidate: boolean) {
    if (!wid || !pid || !selectedSuggestion || !selectedAnalysis) return;
    setBusy(true);
    try {
      const result = await createSuggestionPlanItems(wid, pid, selectedSuggestion.id, actorEmail, {
        plan_id: selectedPlanId || undefined,
        version_ref: selectedAnalysis.target_ref,
        test_case_ids: includeAICandidate ? [] : selectedCaseIds,
        include_ai_candidate: includeAICandidate
      });
      setRecentPlanItems(result.items);
      setMessage(`已加入计划：${result.items.length} 项`);
      await loadSuggestions(selectedAnalysisId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "加入计划失败");
    } finally {
      setBusy(false);
    }
  }

  if (!currentProject) {
    return <p className="empty-state">尚未选择项目。</p>;
  }

  return (
    <section className="panel ai-suggestion-panel">
      <header className="panel-head">
        <div>
          <span className="eyebrow">AI Suggestions</span>
          <h2>AI 智能推荐</h2>
          <p className="panel-sub">基于 Diff 分析为本次发布生成回归用例和候选用例，仍需人工评审入库。</p>
        </div>
        <BrainCircuit size={20} aria-hidden="true" />
      </header>

      {message ? <div className="inline-notice">{message}</div> : null}

      <ol className="wizard">
        <li className="wizard-step">
          <header className="wizard-step-head">
            <span className="wizard-num">1</span>
            <div>
              <h3>选择 Diff 分析</h3>
              <p>从已经完成的 Diff 分析中选一份作为推荐输入。</p>
            </div>
          </header>
          <div className="wizard-step-body">
            {analyses.length === 0 ? (
              <p className="empty-state">尚无 Diff 分析。请先到「Diff 分析」生成一份。</p>
            ) : (
              <div className="diff-radio-list">
                {analyses.map((a) => (
                  <label className={selectedAnalysisId === a.id ? "diff-radio-row selected" : "diff-radio-row"} key={a.id}>
                    <input
                      type="radio"
                      name="diff-analysis"
                      checked={selectedAnalysisId === a.id}
                      onChange={() => {
                        setSelectedAnalysisId(a.id);
                        void loadSuggestions(a.id);
                      }}
                    />
                    <div>
                      <strong>
                        {a.base_ref} → {a.target_ref}
                      </strong>
                      <small>
                        风险 {riskLabel[a.risk_level]} · {a.module_impacts.length} 个模块受影响 ·{" "}
                        {new Date(a.created_at).toLocaleDateString()}
                      </small>
                    </div>
                  </label>
                ))}
              </div>
            )}
            <button className="primary-button small" type="button" onClick={() => void generate()} disabled={busy || !selectedAnalysisId}>
              <Sparkles size={14} aria-hidden="true" />
              {suggestions.length ? "重新生成 AI 建议" : "生成 AI 建议"}
            </button>
          </div>
        </li>

        <li className={`wizard-step ${suggestions.length === 0 ? "disabled" : ""}`}>
          <header className="wizard-step-head">
            <span className="wizard-num">2</span>
            <div>
              <h3>查看建议并反馈</h3>
              <p>左侧选择一条建议，右侧查看证据，标记采纳 / 修改 / 忽略。</p>
            </div>
          </header>
          <div className="wizard-step-body">
            <div className="suggestion-split">
              <ol className="suggestion-list">
                {suggestions.map((s) => (
                  <li key={s.id}>
                    <button
                      className={selectedSuggestionId === s.id ? "suggestion-row active" : "suggestion-row"}
                      type="button"
                      onClick={() => pickSuggestion(s)}
                    >
                      <ChevronRight size={14} aria-hidden="true" />
                      <div>
                        <strong>
                          {suggestionTypeLabel[s.suggestion_type]} · {s.title}
                        </strong>
                        <small>
                          模块 {s.module_key} · 置信度 {s.confidence}% · {statusLabel[s.status]}
                        </small>
                      </div>
                    </button>
                  </li>
                ))}
                {suggestions.length === 0 ? <p className="empty-state">点击上方「生成 AI 建议」</p> : null}
              </ol>

              <div className="suggestion-detail">
                {selectedSuggestion ? (
                  <>
                    <h4>{selectedSuggestion.title}</h4>
                    <p className="rationale">{selectedSuggestion.rationale}</p>
                    {selectedSuggestion.code_paths.length ? (
                      <p>
                        <small>代码路径：{selectedSuggestion.code_paths.slice(0, 5).join(" · ")}</small>
                      </p>
                    ) : null}
                    {selectedSuggestion.interfaces.length ? (
                      <p>
                        <small>接口：{selectedSuggestion.interfaces.slice(0, 5).join(" · ")}</small>
                      </p>
                    ) : null}
                    <label>
                      反馈意见（可选）
                      <textarea
                        rows={2}
                        value={feedbackText}
                        onChange={(e) => setFeedbackText(e.target.value)}
                        placeholder="例：建议增加超时分支用例"
                      />
                    </label>
                    <div className="form-row compact">
                      <button className="primary-button small" type="button" onClick={() => void feedback("accepted")} disabled={busy}>
                        <CheckCircle2 size={14} aria-hidden="true" /> 采纳
                      </button>
                      <button className="ghost-button small" type="button" onClick={() => void feedback("modified")} disabled={busy}>
                        <MessageSquare size={14} aria-hidden="true" /> 标记修改
                      </button>
                      <button className="ghost-button small" type="button" onClick={() => void feedback("ignored")} disabled={busy}>
                        <XCircle size={14} aria-hidden="true" /> 忽略
                      </button>
                    </div>
                  </>
                ) : (
                  <p className="empty-state">从左侧选择一条建议。</p>
                )}
              </div>
            </div>
          </div>
        </li>

        <li className={`wizard-step ${selectedSuggestion ? "" : "disabled"}`}>
          <header className="wizard-step-head">
            <span className="wizard-num">3</span>
            <div>
              <h3>采纳到正式用例或本次计划</h3>
              <p>回归建议命中正式用例 → 勾选后入计划；候选建议 → 创建草稿等待评审，或直接加为临时计划项。</p>
            </div>
          </header>
          <div className="wizard-step-body">
            {selectedSuggestion?.suggestion_type === "regression" ? (
              <>
                <h5>命中的正式用例</h5>
                {relatedCases.length === 0 ? (
                  <p className="empty-state">建议未命中已通过评审的正式用例。</p>
                ) : (
                  <div className="case-checklist">
                    {relatedCases.map((c) => (
                      <label key={c.id}>
                        <input
                          type="checkbox"
                          checked={selectedCaseIds.includes(c.id)}
                          onChange={(e) =>
                            setSelectedCaseIds((cur) =>
                              e.target.checked ? Array.from(new Set([...cur, c.id])) : cur.filter((x) => x !== c.id)
                            )
                          }
                        />
                        <strong>{c.title}</strong>
                        <small>{c.module_path_label || "未归属"}</small>
                      </label>
                    ))}
                  </div>
                )}
              </>
            ) : null}

            {selectedSuggestion?.suggestion_type === "case_candidate" ? (
              <div className="card-form">
                <h5>AI 候选</h5>
                <p className="panel-sub">
                  {selectedSuggestion.candidate_case_id ? "已创建候选草稿，请到评审队列处理。" : "尚未创建草稿。"}
                </p>
                <div className="form-row compact">
                  <button
                    className="ghost-button small"
                    type="button"
                    disabled={busy || !!selectedSuggestion.candidate_case_id}
                    onClick={() => void createCandidate()}
                  >
                    <Plus size={14} aria-hidden="true" /> 创建候选草稿（走评审）
                  </button>
                </div>
              </div>
            ) : null}

            <div className="card-form">
              <h5>加入计划</h5>
              <label>
                目标 TestPlan
                <select value={selectedPlanId} onChange={(e) => setSelectedPlanId(e.target.value)} disabled={busy || plans.length === 0}>
                  <option value="">自动创建 release plan</option>
                  {plans.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} · {p.version_ref || "无版本"}
                    </option>
                  ))}
                </select>
              </label>
              <div className="form-row compact">
                {selectedSuggestion?.suggestion_type === "regression" ? (
                  <button
                    className="primary-button small"
                    type="button"
                    onClick={() => void addToPlan(false)}
                    disabled={busy || selectedCaseIds.length === 0}
                  >
                    <ClipboardCheck size={14} aria-hidden="true" /> 选中用例加入计划
                  </button>
                ) : null}
                {selectedSuggestion?.suggestion_type === "case_candidate" ? (
                  <button
                    className="primary-button small"
                    type="button"
                    onClick={() => void addToPlan(true)}
                    disabled={busy}
                  >
                    <ClipboardCheck size={14} aria-hidden="true" /> 加入临时计划项
                  </button>
                ) : null}
              </div>
            </div>

            {recentPlanItems.length ? (
              <div className="card-list">
                {recentPlanItems.map((item) => (
                  <article className="member-card" key={item.id}>
                    <div>
                      <strong>{item.title}</strong>
                      <small>
                        {statusLabel[item.source_type]} · {statusLabel[item.status]}
                      </small>
                    </div>
                  </article>
                ))}
              </div>
            ) : null}
          </div>
        </li>
      </ol>
    </section>
  );
}
