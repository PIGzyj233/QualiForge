import { useEffect, useState } from "react";
import { BrainCircuit, ChevronRight, Sparkles } from "lucide-react";
import {
  type AISuggestionRecord, createCandidateFromSuggestion, createSuggestionPlanItems,
  type DiffAnalysisRecord, generateAISuggestions, getAISuggestionStatus, listDiffAnalyses,
  listTestCases, type TestCaseRecord, updateAISuggestion
} from "@/api/cases";
import type { AgentRunRecord } from "@/api/agents";
import { listTestPlans, type TestPlanRecord } from "@/api/planning";
import { useCurrentWorkspace, useCurrentProject } from "@/stores/workspace-store";
import { useSessionStore } from "@/stores/session-store";
import { statusLabel, riskLabel, suggestionTypeLabel } from "@/lib/labels";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";

export function AISuggestionAdmin() {
  const session = useSessionStore((s) => s.session);
  const ws = useCurrentWorkspace();
  const proj = useCurrentProject();
  const actorEmail = session?.user.email ?? "";
  const wid = ws?.id ?? "";
  const pid = proj?.id ?? "";

  const [analyses, setAnalyses] = useState<DiffAnalysisRecord[]>([]);
  const [selectedAnalysisId, setSelectedAnalysisId] = useState("");
  const [suggestions, setSuggestions] = useState<AISuggestionRecord[]>([]);
  const [selectedSuggestionId, setSelectedSuggestionId] = useState("");
  const [approvedCases, setApprovedCases] = useState<TestCaseRecord[]>([]);
  const [selectedCaseIds, setSelectedCaseIds] = useState<string[]>([]);
  const [plans, setPlans] = useState<TestPlanRecord[]>([]);
  const [selectedPlanId, setSelectedPlanId] = useState("");
  const [feedbackText, setFeedbackText] = useState("");
  const [jobRun, setJobRun] = useState<AgentRunRecord | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const selectedSuggestion = suggestions.find((s) => s.id === selectedSuggestionId);
  const generationRunning = Boolean(
    jobRun &&
    ["queued", "running"].includes(jobRun.status) &&
    jobRun.budget_snapshot?.diff_analysis_id === selectedAnalysisId
  );

  function applySuggestions(list: AISuggestionRecord[]) {
    setSuggestions(list);
    const sid = list.some((s) => s.id === selectedSuggestionId) ? selectedSuggestionId : (list[0]?.id ?? "");
    setSelectedSuggestionId(sid);
    setSelectedCaseIds(list.find((s) => s.id === sid)?.selected_case_ids ?? []);
  }

  async function loadSuggestionStatus(analysisId: string) {
    if (!wid || !pid || !analysisId) {
      setSuggestions([]);
      setSelectedSuggestionId("");
      setJobRun(null);
      return;
    }
    const job = await getAISuggestionStatus(wid, pid, analysisId, actorEmail);
    setJobRun(job.agent_run);
    applySuggestions(job.suggestions);
    if (job.agent_run?.status === "failed") {
      setMessage(job.agent_run.failure_reason || job.message);
    } else if (job.agent_run?.status === "cancelled") {
      setMessage(job.agent_run.failure_reason || job.message);
    }
  }

  useEffect(() => {
    if (!wid || !pid) return;
    void (async () => {
      setBusy(true);
      try {
        const [anals, cases, ps] = await Promise.all([listDiffAnalyses(wid, pid), listTestCases(wid, pid, undefined, "approved"), listTestPlans(wid, pid)]);
        setAnalyses(anals); setApprovedCases(cases); setPlans(ps);
        const aid = anals[0]?.id ?? "";
        setSelectedAnalysisId(aid);
        setSelectedPlanId(ps[0]?.id ?? "");
        if (aid) await loadSuggestionStatus(aid);
      } catch (err) { setMessage(err instanceof Error ? err.message : "加载失败"); }
      finally { setBusy(false); }
    })();
  }, [wid, pid]);

  useEffect(() => {
    if (!generationRunning || !selectedAnalysisId) return;
    const timer = window.setInterval(() => {
      void loadSuggestionStatus(selectedAnalysisId);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [generationRunning, selectedAnalysisId, wid, pid, actorEmail]);

  async function generate() {
    if (!wid || !pid || !selectedAnalysisId) return;
    setBusy(true); setMessage(null);
    try {
      const job = await generateAISuggestions(wid, pid, selectedAnalysisId, actorEmail, { force: suggestions.length > 0 });
      setJobRun(job.agent_run);
      applySuggestions(job.suggestions);
      if (job.agent_run && ["queued", "running"].includes(job.agent_run.status)) {
        setMessage(job.reused_running ? "AI 建议已在后台生成中" : "AI 建议已提交后台生成");
      } else {
        setMessage(`已加载 ${job.suggestions.length} 条建议`);
      }
    } catch (err) { setMessage(err instanceof Error ? err.message : "生成失败"); }
    finally { setBusy(false); }
  }

  async function feedback(status: "accepted" | "ignored" | "modified") {
    if (!wid || !pid || !selectedSuggestion) return;
    setBusy(true); setMessage(null);
    try {
      const updated = await updateAISuggestion(wid, pid, selectedSuggestion.id, actorEmail, { status, feedback_comment: feedbackText || undefined, selected_case_ids: selectedSuggestion.suggestion_type === "regression" ? selectedCaseIds : undefined });
      setMessage(`已反馈：${statusLabel[updated.status]}`);
      await loadSuggestionStatus(selectedAnalysisId);
    } catch (err) { setMessage(err instanceof Error ? err.message : "反馈失败"); }
    finally { setBusy(false); }
  }

  async function createCandidate() {
    if (!wid || !pid || !selectedSuggestion) return;
    setBusy(true);
    try {
      const r = await createCandidateFromSuggestion(wid, pid, selectedSuggestion.id, actorEmail);
      setMessage(`已创建 AI 候选草稿 "${r.test_case.title}"`);
      await loadSuggestionStatus(selectedAnalysisId);
    } catch (err) { setMessage(err instanceof Error ? err.message : "创建失败"); }
    finally { setBusy(false); }
  }

  async function addToPlan(includeAICandidate: boolean) {
    if (!wid || !pid || !selectedSuggestion) return;
    const analysis = analyses.find((a) => a.id === selectedAnalysisId);
    setBusy(true);
    try {
      const r = await createSuggestionPlanItems(wid, pid, selectedSuggestion.id, actorEmail, { plan_id: selectedPlanId || undefined, version_ref: analysis?.target_ref ?? "", test_case_ids: includeAICandidate ? [] : selectedCaseIds, include_ai_candidate: includeAICandidate });
      setMessage(`已加入计划：${r.items.length} 项`);
    } catch (err) { setMessage(err instanceof Error ? err.message : "加入计划失败"); }
    finally { setBusy(false); }
  }

  if (!proj) return <p className="text-sm text-[var(--muted-foreground)]">尚未选择项目。</p>;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)] mb-1">AI Suggestions</p>
          <h1 className="font-heading text-2xl font-bold">AI 智能推荐</h1>
          <p className="mt-1 text-sm text-[var(--muted-foreground)]">基于 Diff 分析为本次发布生成回归用例和候选用例，仍需人工评审入库。</p>
        </div>
        <BrainCircuit size={20} className="text-[var(--muted-foreground)]" />
      </div>
      {message && <Alert><AlertDescription>{message}</AlertDescription></Alert>}

      {/* Step 1 */}
      <Card>
        <CardHeader><CardTitle className="text-sm font-semibold">1 · 选择 Diff 分析</CardTitle></CardHeader>
        <CardContent className="flex flex-col gap-3">
          {analyses.length === 0 ? (
            <p className="text-sm text-[var(--muted-foreground)]">尚无 Diff 分析。请先到「Diff 分析」生成一份。</p>
          ) : (
            <div className="flex flex-col gap-1.5">
              {analyses.map((a) => (
                <label key={a.id} className={`flex items-center gap-3 rounded-[var(--radius-sm)] border px-3 py-2.5 cursor-pointer transition-colors ${selectedAnalysisId === a.id ? "border-[var(--primary)] bg-[var(--accent)]" : "hover:bg-[var(--muted)]/40"}`}>
                  <input type="radio" name="diff" checked={selectedAnalysisId === a.id} onChange={() => { setSelectedAnalysisId(a.id); void loadSuggestionStatus(a.id); }} className="accent-[var(--primary)]" />
                  <div className="min-w-0">
                    <p className="text-sm font-semibold">{a.base_ref} → {a.target_ref}</p>
                    <p className="text-xs text-[var(--muted-foreground)]">风险 {riskLabel[a.risk_level]} · {a.module_impacts.length} 个模块受影响 · {new Date(a.created_at).toLocaleDateString()}</p>
                  </div>
                </label>
              ))}
            </div>
          )}
          <div className="flex flex-wrap items-center gap-3">
            <Button disabled={busy || generationRunning || !selectedAnalysisId} onClick={generate} className="self-start">
              <Sparkles size={14} />{generationRunning ? "AI 建议生成中" : suggestions.length ? "重新生成 AI 建议" : "生成 AI 建议"}
            </Button>
            {jobRun && (
              <Badge variant={jobRun.status === "failed" ? "destructive" : "secondary"}>
                {jobRun.current_phase || jobRun.status}
              </Badge>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Step 2 */}
      {suggestions.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-5 items-start">
          <Card>
            <CardHeader><CardTitle className="text-sm">2 · 建议列表 ({suggestions.length})</CardTitle></CardHeader>
            <CardContent className="p-0">
              {suggestions.map((s) => (
                <button key={s.id} type="button" onClick={() => { setSelectedSuggestionId(s.id); setSelectedCaseIds(s.selected_case_ids); setFeedbackText(""); }}
                  className={`w-full text-left flex items-start gap-2 px-4 py-3 border-b last:border-0 transition-colors hover:bg-[var(--muted)]/40 ${selectedSuggestionId === s.id ? "bg-[var(--accent)]" : ""}`}>
                  <ChevronRight size={14} className="mt-0.5 shrink-0" />
                  <div className="min-w-0">
                    <p className="text-sm font-semibold truncate">{suggestionTypeLabel[s.suggestion_type]} · {s.title}</p>
                    <p className="text-xs text-[var(--muted-foreground)]">模块 {s.module_key} · 置信度 {s.confidence}% · {statusLabel[s.status]}</p>
                  </div>
                </button>
              ))}
            </CardContent>
          </Card>

          {selectedSuggestion && (
            <div className="flex flex-col gap-4">
              <Card>
                <CardHeader><CardTitle>{selectedSuggestion.title}</CardTitle></CardHeader>
                <CardContent className="flex flex-col gap-3">
                  <p className="text-sm text-[var(--muted-foreground)]">{selectedSuggestion.rationale}</p>
                  {selectedSuggestion.mapping_evidence.length > 0 && (
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)] mb-1.5">证据</p>
                      <ul className="flex flex-col gap-1">{selectedSuggestion.mapping_evidence.slice(0, 6).map((e) => <li key={e} className="text-xs text-[var(--muted-foreground)]">· {e}</li>)}</ul>
                    </div>
                  )}
                  {selectedSuggestion.suggestion_type === "case_candidate" && Array.isArray(selectedSuggestion.candidate_payload.steps) && (
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)] mb-1.5">候选步骤</p>
                      <ol className="flex flex-col gap-1">{(selectedSuggestion.candidate_payload.steps as Array<{action: string; expected: string}>).slice(0, 5).map((step, i) => <li key={i} className="text-sm"><span className="font-medium">{step.action}</span>{step.expected && <span className="text-[var(--muted-foreground)]"> → {step.expected}</span>}</li>)}</ol>
                    </div>
                  )}
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-5 flex flex-col gap-3">
                  <div className="flex flex-col gap-1.5">
                    <Label>反馈意见</Label>
                    <Textarea value={feedbackText} onChange={(e) => setFeedbackText(e.target.value)} rows={2} placeholder="可选" />
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button disabled={busy} onClick={() => void feedback("accepted")}>采纳</Button>
                    <Button variant="outline" disabled={busy} onClick={() => void feedback("modified")}>修改后采纳</Button>
                    <Button variant="outline" disabled={busy} onClick={() => void feedback("ignored")}>忽略</Button>
                    {selectedSuggestion.suggestion_type === "case_candidate" && (
                      <Button variant="outline" disabled={busy} onClick={createCandidate}>创建 AI 候选草稿</Button>
                    )}
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardHeader><CardTitle className="text-sm">3 · 加入测试计划</CardTitle></CardHeader>
                <CardContent className="flex flex-col gap-3">
                  <Select value={selectedPlanId} onValueChange={setSelectedPlanId} disabled={plans.length === 0}>
                    <SelectTrigger><SelectValue placeholder="选择计划" /></SelectTrigger>
                    <SelectContent>{plans.map((p) => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}</SelectContent>
                  </Select>
                  <div className="flex gap-2">
                    <Button disabled={busy || !selectedPlanId} onClick={() => void addToPlan(false)}>加入已选用例</Button>
                    <Button variant="outline" disabled={busy || !selectedPlanId} onClick={() => void addToPlan(true)}>加入 AI 候选</Button>
                  </div>
                </CardContent>
              </Card>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
