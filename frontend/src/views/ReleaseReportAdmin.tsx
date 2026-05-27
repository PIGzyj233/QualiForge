import { FormEvent, useEffect, useState } from "react";
import { FileText, ShieldCheck, Sparkles } from "lucide-react";
import { useParams } from "react-router-dom";
import {
  confirmReleaseReportDecision, createReleaseReportDraft, exportReleaseReportMarkdown,
  listReleaseReports, listTestPlans, type ReleaseReportRecord, type TestPlanRecord
} from "@/api/planning";
import { useCurrentWorkspace, useCurrentProject } from "@/stores/workspace-store";
import { useSessionStore } from "@/stores/session-store";
import { statusLabel } from "@/lib/labels";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";

export function ReleaseReportAdmin() {
  const session = useSessionStore((s) => s.session);
  const ws = useCurrentWorkspace();
  const proj = useCurrentProject();
  const { wid = "", pid = "" } = useParams<{ wid: string; pid: string }>();
  const actorEmail = session?.user.email ?? "";
  const wid_ = (wid || ws?.id) ?? "";
  const pid_ = (pid || proj?.id) ?? "";

  const [plans, setPlans] = useState<TestPlanRecord[]>([]);
  const [selectedPlanId, setSelectedPlanId] = useState("");
  const [reports, setReports] = useState<ReleaseReportRecord[]>([]);
  const [selectedReportId, setSelectedReportId] = useState("");
  const [releaseDecision, setReleaseDecision] = useState("hold_release");
  const [decisionComment, setDecisionComment] = useState("Release decision pending owner review.");
  const [markdownExport, setMarkdownExport] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function loadReports(planId: string, preferredId?: string) {
    if (!planId) { setReports([]); setSelectedReportId(""); return; }
    const rs = await listReleaseReports(wid_, pid_, planId);
    setReports(rs);
    const r = rs.find((x) => x.id === preferredId) ?? rs[0];
    setSelectedReportId(r?.id ?? "");
    if (r) {
      setReleaseDecision(r.release_decision === "pending_owner_confirmation" ? r.release_suggestion : r.release_decision);
      setDecisionComment(r.decision_comment || "Release decision pending owner review.");
    }
  }

  useEffect(() => {
    if (!wid_ || !pid_) return;
    void (async () => {
      setBusy(true);
      try {
        const ps = await listTestPlans(wid_, pid_);
        setPlans(ps);
        const pid = ps[0]?.id ?? "";
        setSelectedPlanId(pid);
        await loadReports(pid);
      } catch (err) { setMessage(err instanceof Error ? err.message : "加载失败"); }
      finally { setBusy(false); }
    })();
  }, [wid_, pid_]);

  async function handleGenerateDraft() {
    if (!wid_ || !pid_ || !selectedPlanId) return;
    setBusy(true); setMessage(null);
    try {
      const r = await createReleaseReportDraft(wid_, pid_, selectedPlanId, actorEmail);
      setMessage(`已生成报告草稿：${r.title}`);
      await loadReports(selectedPlanId, r.id);
    } catch (err) { setMessage(err instanceof Error ? err.message : "生成失败"); }
    finally { setBusy(false); }
  }

  async function handleConfirmDecision(e: FormEvent) {
    e.preventDefault();
    if (!wid_ || !pid_ || !selectedReportId) return;
    setBusy(true); setMessage(null);
    try {
      const r = await confirmReleaseReportDecision(wid_, pid_, selectedReportId, actorEmail, { release_decision: releaseDecision, decision_comment: decisionComment });
      setMessage(`已确认发布结论：${statusLabel[r.release_decision] ?? r.release_decision}`);
      await loadReports(selectedPlanId, r.id);
    } catch (err) { setMessage(err instanceof Error ? err.message : "确认失败"); }
    finally { setBusy(false); }
  }

  async function handleExportMarkdown() {
    if (!wid_ || !pid_ || !selectedReportId) return;
    setBusy(true); setMessage(null);
    try {
      setMarkdownExport(await exportReleaseReportMarkdown(wid_, pid_, selectedReportId));
      setMessage("Markdown 报告已生成");
    } catch (err) { setMessage(err instanceof Error ? err.message : "导出失败"); }
    finally { setBusy(false); }
  }

  const selectedReport = reports.find((r) => r.id === selectedReportId);
  const sections = (selectedReport?.sections ?? {}) as Record<string, unknown>;
  const summary = (sections.summary ?? {}) as Record<string, unknown>;
  const stats = (sections.execution_statistics ?? {}) as Record<string, unknown>;
  const counts = (stats.counts ?? {}) as Record<string, number>;
  const risk = (sections.risk_assessment ?? {}) as Record<string, unknown>;
  const failedBlocked = Array.isArray(sections.failed_blocked_items) ? (sections.failed_blocked_items as Array<Record<string, unknown>>) : [];

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)] mb-1">Release Report</p>
          <h1 className="font-heading text-2xl font-bold">发布报告</h1>
        </div>
        <FileText size={20} className="text-[var(--muted-foreground)]" />
      </div>
      {message && <Alert><AlertDescription>{message}</AlertDescription></Alert>}

      <div className="flex flex-wrap gap-3 items-end">
        <div className="flex flex-col gap-1.5 min-w-[200px]">
          <Label>测试计划</Label>
          <Select value={selectedPlanId} onValueChange={(v) => { setSelectedPlanId(v); void loadReports(v); }} disabled={plans.length === 0}>
            <SelectTrigger><SelectValue placeholder="选择计划" /></SelectTrigger>
            <SelectContent>{plans.map((p) => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        {reports.length > 0 && (
          <div className="flex flex-col gap-1.5 min-w-[200px]">
            <Label>报告</Label>
            <Select value={selectedReportId} onValueChange={(v) => { setSelectedReportId(v); const r = reports.find((x) => x.id === v); if (r) { setReleaseDecision(r.release_decision === "pending_owner_confirmation" ? r.release_suggestion : r.release_decision); setDecisionComment(r.decision_comment || ""); setMarkdownExport(""); } }}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>{reports.map((r) => <SelectItem key={r.id} value={r.id}>{r.title}</SelectItem>)}</SelectContent>
            </Select>
          </div>
        )}
        <Button disabled={busy || !selectedPlanId} onClick={handleGenerateDraft}><Sparkles size={14} />生成报告草稿</Button>
      </div>

      {selectedReport && (
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-5 items-start">
          <div className="flex flex-col gap-4">
            <Card>
              <CardHeader><CardTitle>{selectedReport.title}</CardTitle></CardHeader>
              <CardContent className="flex flex-col gap-3">
                {Boolean(summary.overview) && <p className="text-sm">{String(summary.overview)}</p>}
                {Boolean(summary.key_findings) && Array.isArray(summary.key_findings) && (
                  <ul className="flex flex-col gap-1">{(summary.key_findings as string[]).map((f, i) => <li key={i} className="text-sm text-[var(--muted-foreground)]">· {f}</li>)}</ul>
                )}
                {Object.keys(counts).length > 0 && (
                  <div className="grid grid-cols-3 gap-2 mt-1">
                    {Object.entries(counts).map(([k, v]) => (
                      <div key={k} className="rounded-[var(--radius-sm)] border bg-[var(--muted)]/40 px-3 py-2 text-center">
                        <p className="text-lg font-bold">{v}</p>
                        <p className="text-xs text-[var(--muted-foreground)]">{k}</p>
                      </div>
                    ))}
                  </div>
                )}
                {Boolean(risk.summary) && <p className="text-sm text-[var(--muted-foreground)]">{String(risk.summary)}</p>}
              </CardContent>
            </Card>

            {failedBlocked.length > 0 && (
              <Card>
                <CardHeader><CardTitle className="text-sm">失败/阻塞项</CardTitle></CardHeader>
                <CardContent className="p-0">
                  {failedBlocked.map((item, i) => (
                    <div key={i} className="px-5 py-3 border-b last:border-0">
                      <p className="text-sm font-semibold">{String(item.title ?? "")}</p>
                      <p className="text-xs text-[var(--muted-foreground)]">{String(item.failure_reason ?? item.status ?? "")}</p>
                    </div>
                  ))}
                </CardContent>
              </Card>
            )}

            {markdownExport && (
              <Card>
                <CardHeader><CardTitle className="text-sm">Markdown 导出</CardTitle></CardHeader>
                <CardContent><pre className="text-xs font-mono whitespace-pre-wrap overflow-x-auto max-h-96">{markdownExport}</pre></CardContent>
              </Card>
            )}
          </div>

          <div className="flex flex-col gap-4">
            <Card>
              <CardHeader><CardTitle className="flex items-center gap-2"><ShieldCheck size={16} />确认发布结论</CardTitle></CardHeader>
              <CardContent>
                <form onSubmit={handleConfirmDecision} className="flex flex-col gap-3">
                  <div className="flex flex-col gap-1.5">
                    <Label>发布决策</Label>
                    <Select value={releaseDecision} onValueChange={setReleaseDecision}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="approved_for_release">批准发布</SelectItem>
                        <SelectItem value="conditional_release">有条件发布</SelectItem>
                        <SelectItem value="hold_release">暂缓发布</SelectItem>
                        <SelectItem value="rejected">拒绝发布</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label>决策说明</Label>
                    <Textarea value={decisionComment} onChange={(e) => setDecisionComment(e.target.value)} rows={3} />
                  </div>
                  <Button type="submit" disabled={busy}>确认结论</Button>
                </form>
              </CardContent>
            </Card>
            <Button variant="outline" disabled={busy || !selectedReportId} onClick={handleExportMarkdown}>导出 Markdown</Button>
          </div>
        </div>
      )}
    </div>
  );
}
