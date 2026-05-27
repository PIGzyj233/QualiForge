import { FormEvent, useEffect, useMemo, useState } from "react";
import { ClipboardCheck, Plus } from "lucide-react";
import { useParams } from "react-router-dom";
import {
  createPlanItem, createTestPlan, listPlanItems, listTestPlans,
  type PlanItemRecord, type TestPlanRecord, updatePlanItemExecution, uploadPlanItemEvidence
} from "@/api/planning";
import { listTestCases, type TestCaseRecord } from "@/api/cases";
import { useCurrentWorkspace, useCurrentProject } from "@/stores/workspace-store";
import { useSessionStore } from "@/stores/session-store";
import { Pagination } from "@/components/Pagination";
import { usePagination } from "@/hooks/usePagination";
import { statusLabel, executionStatuses, type ExecutionStatus } from "@/lib/labels";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { StatusPill } from "@/components/StatusPill";

export function TestPlanAdmin() {
  const session = useSessionStore((s) => s.session);
  const ws = useCurrentWorkspace();
  const proj = useCurrentProject();
  const { wid = "", pid = "" } = useParams<{ wid: string; pid: string }>();
  const actorEmail = session?.user.email ?? "";
  const wid_ = (wid || ws?.id) ?? "";
  const pid_ = (pid || proj?.id) ?? "";

  const [plans, setPlans] = useState<TestPlanRecord[]>([]);
  const [selectedPlanId, setSelectedPlanId] = useState("");
  const [planItems, setPlanItems] = useState<PlanItemRecord[]>([]);
  const [approvedCases, setApprovedCases] = useState<TestCaseRecord[]>([]);
  const [planName, setPlanName] = useState("Release plan v2");
  const [planType, setPlanType] = useState<TestPlanRecord["plan_type"]>("release");
  const [versionRef, setVersionRef] = useState("v2");
  const [scopeSummary, setScopeSummary] = useState("Checkout payment and refund scope");
  const [ownerEmail, setOwnerEmail] = useState(actorEmail);
  const [itemSourceType, setItemSourceType] = useState<PlanItemRecord["source_type"]>("formal_case");
  const [selectedCaseId, setSelectedCaseId] = useState("");
  const [itemTitle, setItemTitle] = useState("Manual payment observability check");
  const [itemRationale, setItemRationale] = useState("Release scope item");
  const [itemSnapshot, setItemSnapshot] = useState('{"steps":["Open dashboard","Verify payment metrics"]}');
  const [executionFilter, setExecutionFilter] = useState<"all" | "failed_blocked" | ExecutionStatus>("all");
  const [selectedExecutionItemId, setSelectedExecutionItemId] = useState("");
  const [executionStatus, setExecutionStatus] = useState<ExecutionStatus>("not_run");
  const [executionAssignee, setExecutionAssignee] = useState(actorEmail);
  const [actualResult, setActualResult] = useState("");
  const [failureReason, setFailureReason] = useState("");
  const [defectLinksText, setDefectLinksText] = useState("");
  const [evidenceFile, setEvidenceFile] = useState<File | null>(null);
  const [evidenceNote, setEvidenceNote] = useState("Execution evidence");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  function setExecForm(item: PlanItemRecord | undefined) {
    if (!item) { setSelectedExecutionItemId(""); setExecutionStatus("not_run"); setActualResult(""); setFailureReason(""); setDefectLinksText(""); return; }
    setSelectedExecutionItemId(item.id);
    setExecutionStatus(executionStatuses.includes(item.status as ExecutionStatus) ? (item.status as ExecutionStatus) : "not_run");
    setExecutionAssignee(item.assignee_email || actorEmail);
    setActualResult(item.actual_result); setFailureReason(item.failure_reason);
    setDefectLinksText(item.defect_links.join("\n"));
  }

  async function loadItems(planId: string) {
    if (!planId) { setPlanItems([]); setExecForm(undefined); return; }
    const items = await listPlanItems(wid_, pid_, planId);
    setPlanItems(items);
    setExecForm(items.find((i) => i.id === selectedExecutionItemId) ?? items[0]);
  }

  useEffect(() => {
    if (!wid_ || !pid_) return;
    void (async () => {
      setBusy(true);
      try {
        const [ps, cases] = await Promise.all([listTestPlans(wid_, pid_), listTestCases(wid_, pid_, undefined, "approved")]);
        setPlans(ps); setApprovedCases(cases);
        const planId = ps[0]?.id ?? "";
        setSelectedPlanId(planId);
        if (!selectedCaseId && cases[0]) setSelectedCaseId(cases[0].id);
        await loadItems(planId);
      } catch (err) { setMessage(err instanceof Error ? err.message : "加载失败"); }
      finally { setBusy(false); }
    })();
  }, [wid_, pid_]);

  async function handleCreatePlan(e: FormEvent) {
    e.preventDefault();
    if (!wid_ || !pid_) return;
    setBusy(true); setMessage(null);
    try {
      const plan = await createTestPlan(wid_, pid_, actorEmail, { name: planName, plan_type: planType, scope_summary: scopeSummary, version_ref: versionRef, owner_email: ownerEmail });
      setMessage(`已创建测试计划：${plan.name}`);
      const ps = await listTestPlans(wid_, pid_); setPlans(ps); setSelectedPlanId(plan.id);
      await loadItems(plan.id);
    } catch (err) { setMessage(err instanceof Error ? err.message : "创建失败"); }
    finally { setBusy(false); }
  }

  async function handleCreatePlanItem(e: FormEvent) {
    e.preventDefault();
    if (!wid_ || !pid_ || !selectedPlanId) return;
    setBusy(true); setMessage(null);
    try {
      const snapshot = itemSourceType === "formal_case" ? undefined : (JSON.parse(itemSnapshot || "{}") as Record<string, unknown>);
      const item = await createPlanItem(wid_, pid_, selectedPlanId, actorEmail, { source_type: itemSourceType, source_id: itemSourceType === "formal_case" ? selectedCaseId : itemSourceType === "ai_temp" ? "manual-ai-temp" : null, title: itemSourceType === "formal_case" ? undefined : itemTitle, snapshot, rationale: itemRationale });
      setMessage(`已加入计划项：${item.title}`);
      await loadItems(selectedPlanId);
    } catch (err) { setMessage(err instanceof Error ? err.message : "创建失败"); }
    finally { setBusy(false); }
  }

  async function handleSaveExecution(e: FormEvent) {
    e.preventDefault();
    if (!wid_ || !pid_ || !selectedPlanId || !selectedExecutionItemId) return;
    setBusy(true); setMessage(null);
    try {
      const updated = await updatePlanItemExecution(wid_, pid_, selectedPlanId, selectedExecutionItemId, actorEmail, { status: executionStatus, assignee_email: executionAssignee, actual_result: actualResult, failure_reason: failureReason, defect_links: defectLinksText.split(/\r?\n|,/).map((l) => l.trim()).filter(Boolean) });
      setMessage(`已保存：${updated.title} · ${statusLabel[updated.status]}`);
      setExecForm(updated); await loadItems(selectedPlanId);
    } catch (err) { setMessage(err instanceof Error ? err.message : "保存失败"); }
    finally { setBusy(false); }
  }

  async function handleUploadEvidence(e: FormEvent) {
    e.preventDefault();
    if (!wid_ || !pid_ || !selectedPlanId || !selectedExecutionItemId || !evidenceFile) return;
    setBusy(true); setMessage(null);
    try {
      const updated = await uploadPlanItemEvidence(wid_, pid_, selectedPlanId, selectedExecutionItemId, actorEmail, evidenceFile, evidenceNote);
      setMessage(`已上传证据：${evidenceFile.name}`); setEvidenceFile(null); setExecForm(updated);
      await loadItems(selectedPlanId);
    } catch (err) { setMessage(err instanceof Error ? err.message : "上传失败"); }
    finally { setBusy(false); }
  }

  const filteredItems = useMemo(() => {
    if (executionFilter === "all") return planItems;
    if (executionFilter === "failed_blocked") return planItems.filter((i) => i.status === "failed" || i.status === "blocked");
    return planItems.filter((i) => i.status === executionFilter);
  }, [executionFilter, planItems]);
  const pagination = usePagination(filteredItems, 10);
  const progress = useMemo(() => {
    const total = planItems.length;
    const finished = planItems.filter((i) => ["passed", "failed", "blocked", "skipped"].includes(i.status)).length;
    return { total, finished, percent: total ? Math.round((finished / total) * 100) : 0 };
  }, [planItems]);
  const selectedItem = planItems.find((i) => i.id === selectedExecutionItemId);
  const f = "flex flex-col gap-1.5";

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)] mb-1">Test Planning</p>
          <h1 className="font-heading text-2xl font-bold">发布测试计划</h1>
        </div>
        <ClipboardCheck size={20} className="text-[var(--muted-foreground)]" />
      </div>
      {message && <Alert><AlertDescription>{message}</AlertDescription></Alert>}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><Plus size={16} />新建测试计划</CardTitle></CardHeader>
          <CardContent>
            <form onSubmit={handleCreatePlan} className="flex flex-col gap-3">
              <div className="grid grid-cols-2 gap-3">
                <div className={f}><Label>计划名称</Label><Input value={planName} onChange={(e) => setPlanName(e.target.value)} required /></div>
                <div className={f}>
                  <Label>类型</Label>
                  <Select value={planType} onValueChange={(v) => setPlanType(v as typeof planType)}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {["release", "regression", "smoke", "feature", "custom"].map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className={f}><Label>版本 Ref</Label><Input value={versionRef} onChange={(e) => setVersionRef(e.target.value)} /></div>
                <div className={f}><Label>负责人邮箱</Label><Input value={ownerEmail} onChange={(e) => setOwnerEmail(e.target.value)} /></div>
              </div>
              <div className={f}><Label>范围摘要</Label><Input value={scopeSummary} onChange={(e) => setScopeSummary(e.target.value)} /></div>
              <Button type="submit" disabled={busy || !wid_} className="self-start">创建计划</Button>
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>添加计划项</CardTitle></CardHeader>
          <CardContent>
            <form onSubmit={handleCreatePlanItem} className="flex flex-col gap-3">
              <div className={f}>
                <Label>计划</Label>
                <Select value={selectedPlanId} onValueChange={(v) => { setSelectedPlanId(v); void loadItems(v); }} disabled={plans.length === 0}>
                  <SelectTrigger><SelectValue placeholder="选择计划" /></SelectTrigger>
                  <SelectContent>{plans.map((p) => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className={f}>
                <Label>来源类型</Label>
                <Select value={itemSourceType} onValueChange={(v) => setItemSourceType(v as typeof itemSourceType)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="formal_case">正式用例</SelectItem>
                    <SelectItem value="ai_temp">AI 临时</SelectItem>
                    <SelectItem value="manual">手动</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {itemSourceType === "formal_case" ? (
                <div className={f}>
                  <Label>用例</Label>
                  <Select value={selectedCaseId} onValueChange={setSelectedCaseId} disabled={approvedCases.length === 0}>
                    <SelectTrigger><SelectValue placeholder="选择用例" /></SelectTrigger>
                    <SelectContent>{approvedCases.map((c) => <SelectItem key={c.id} value={c.id}>{c.title}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
              ) : (
                <>
                  <div className={f}><Label>标题</Label><Input value={itemTitle} onChange={(e) => setItemTitle(e.target.value)} /></div>
                  <div className={f}><Label>Snapshot JSON</Label><Textarea value={itemSnapshot} onChange={(e) => setItemSnapshot(e.target.value)} rows={2} /></div>
                </>
              )}
              <div className={f}><Label>理由</Label><Input value={itemRationale} onChange={(e) => setItemRationale(e.target.value)} /></div>
              <Button type="submit" disabled={busy || !selectedPlanId} className="self-start">添加计划项</Button>
            </form>
          </CardContent>
        </Card>
      </div>

      {selectedPlanId && (
        <>
          {progress.total > 0 && (
            <Card>
              <CardContent className="pt-5">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-semibold">执行进度</span>
                  <span className="text-sm text-[var(--muted-foreground)]">{progress.finished}/{progress.total} · {progress.percent}%</span>
                </div>
                <div className="h-2 rounded-full bg-[var(--muted)] overflow-hidden">
                  <div className="h-full bg-[var(--primary)] transition-all" style={{ width: `${progress.percent}%` }} />
                </div>
              </CardContent>
            </Card>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-5 items-start">
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm">计划项 ({filteredItems.length})</CardTitle>
                  <Select value={executionFilter} onValueChange={(v) => setExecutionFilter(v as typeof executionFilter)}>
                    <SelectTrigger className="w-32 h-7 text-xs"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">全部</SelectItem>
                      <SelectItem value="failed_blocked">失败/阻塞</SelectItem>
                      {executionStatuses.map((s) => <SelectItem key={s} value={s}>{statusLabel[s] ?? s}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              </CardHeader>
              <CardContent className="p-0">
                {pagination.currentItems.map((item) => (
                  <button key={item.id} type="button" onClick={() => setExecForm(item)}
                    className={`w-full text-left flex items-center justify-between gap-3 px-5 py-3 border-b last:border-0 transition-colors hover:bg-[var(--muted)]/40 ${selectedExecutionItemId === item.id ? "bg-[var(--accent)]" : ""}`}>
                    <div className="min-w-0">
                      <p className="text-sm font-semibold truncate">{item.title}</p>
                      <p className="text-xs text-[var(--muted-foreground)]">{item.source_type} · {item.assignee_email || "未分配"}</p>
                    </div>
                    <StatusPill status={item.status} />
                  </button>
                ))}
                {filteredItems.length === 0 && <p className="px-5 py-4 text-sm text-[var(--muted-foreground)]">暂无计划项</p>}
                <div className="px-5"><Pagination currentPage={pagination.currentPage} totalPages={pagination.totalPages} totalItems={pagination.totalItems} onPageChange={pagination.goToPage} itemsPerPage={10} /></div>
              </CardContent>
            </Card>

            {selectedItem && (
              <div className="flex flex-col gap-4">
                <Card>
                  <CardHeader><CardTitle className="text-sm">{selectedItem.title}</CardTitle></CardHeader>
                  <CardContent>
                    <form onSubmit={handleSaveExecution} className="flex flex-col gap-3">
                      <div className={f}>
                        <Label>执行状态</Label>
                        <Select value={executionStatus} onValueChange={(v) => setExecutionStatus(v as ExecutionStatus)}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>{executionStatuses.map((s) => <SelectItem key={s} value={s}>{statusLabel[s] ?? s}</SelectItem>)}</SelectContent>
                        </Select>
                      </div>
                      <div className={f}><Label>负责人</Label><Input value={executionAssignee} onChange={(e) => setExecutionAssignee(e.target.value)} /></div>
                      <div className={f}><Label>实际结果</Label><Textarea value={actualResult} onChange={(e) => setActualResult(e.target.value)} rows={2} /></div>
                      <div className={f}><Label>失败原因</Label><Input value={failureReason} onChange={(e) => setFailureReason(e.target.value)} /></div>
                      <div className={f}><Label>缺陷链接</Label><Textarea value={defectLinksText} onChange={(e) => setDefectLinksText(e.target.value)} rows={2} /></div>
                      <Button type="submit" disabled={busy}>保存执行结果</Button>
                    </form>
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader><CardTitle className="text-sm">上传证据</CardTitle></CardHeader>
                  <CardContent>
                    <form onSubmit={handleUploadEvidence} className="flex flex-col gap-3">
                      <input type="file" onChange={(e) => setEvidenceFile(e.target.files?.[0] ?? null)} className="text-sm" />
                      <div className={f}><Label>备注</Label><Input value={evidenceNote} onChange={(e) => setEvidenceNote(e.target.value)} /></div>
                      <Button type="submit" disabled={busy || !evidenceFile} className="self-start">上传</Button>
                    </form>
                  </CardContent>
                </Card>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
