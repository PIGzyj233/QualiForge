import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, FileSearch, MessageSquareWarning, XCircle } from "lucide-react";
import { useParams } from "react-router-dom";
import {
  approveReviewCycle, getTestCase, listModules, listReviewQueue,
  type ProjectModuleRecord, rejectReviewCycle, requestReviewChanges, type TestCaseRecord
} from "@/api/cases";
import { useCurrentWorkspace, useCurrentProject } from "@/stores/workspace-store";
import { useSessionStore } from "@/stores/session-store";
import { CaseRevisionViewer } from "@/components/CaseRevisionViewer";
import { ReviewStatusBadge } from "@/components/ReviewStatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";

export function ReviewQueueView() {
  const session = useSessionStore((s) => s.session);
  const ws = useCurrentWorkspace();
  const proj = useCurrentProject();
  const { wid = "", pid = "" } = useParams<{ wid: string; pid: string }>();
  const actorEmail = session?.user.email ?? "";
  const wid_ = (wid || ws?.id) ?? "";
  const pid_ = (pid || proj?.id) ?? "";

  const [modules, setModules] = useState<ProjectModuleRecord[]>([]);
  const [queue, setQueue] = useState<TestCaseRecord[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState("");
  const [selectedCase, setSelectedCase] = useState<TestCaseRecord | null>(null);
  const [reviewComment, setReviewComment] = useState("Looks good");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function refreshDetail(caseId: string) {
    if (!caseId) { setSelectedCase(null); return; }
    setSelectedCase(await getTestCase(wid_, pid_, caseId));
  }

  async function refreshQueue(preferredCaseId?: string) {
    if (!wid_ || !pid_) return;
    const [mods, q] = await Promise.all([listModules(wid_, pid_), listReviewQueue(wid_, pid_)]);
    setModules(mods); setQueue(q);
    const caseId = preferredCaseId ?? q[0]?.id ?? "";
    setSelectedCaseId(caseId);
    await refreshDetail(caseId);
  }

  useEffect(() => { void refreshQueue(); }, [wid_, pid_]);

  async function handleAction(action: "approve" | "changes" | "reject") {
    if (!selectedCase?.open_cycle) return;
    setBusy(true); setMessage(null);
    try {
      if (action === "approve") { await approveReviewCycle(wid_, pid_, selectedCase.open_cycle.id, actorEmail, reviewComment || "Approved"); setMessage("已通过评审"); }
      else if (action === "changes") { await requestReviewChanges(wid_, pid_, selectedCase.open_cycle.id, actorEmail, reviewComment); setMessage("已要求修改"); }
      else { await rejectReviewCycle(wid_, pid_, selectedCase.open_cycle.id, actorEmail, reviewComment || "Rejected"); setMessage("已驳回评审"); }
      await refreshQueue();
    } catch (err) { setMessage(err instanceof Error ? err.message : "评审操作失败"); }
    finally { setBusy(false); }
  }

  const moduleById = useMemo(() => new Map(modules.map((m) => [m.id, m])), [modules]);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)] mb-1">Review Queue</p>
          <h1 className="font-heading text-2xl font-bold">评审队列</h1>
        </div>
        <FileSearch size={20} className="text-[var(--muted-foreground)]" />
      </div>
      {message && <Alert><AlertDescription>{message}</AlertDescription></Alert>}
      <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-5 items-start">
        <Card>
          <CardHeader><CardTitle className="text-sm">待评审 ({queue.length})</CardTitle></CardHeader>
          <CardContent className="p-0">
            {queue.map((tc) => (
              <button
                key={tc.id}
                type="button"
                onClick={() => { setSelectedCaseId(tc.id); void refreshDetail(tc.id); }}
                className={`w-full text-left px-4 py-3 border-b last:border-0 transition-colors hover:bg-[var(--muted)]/40 ${selectedCaseId === tc.id ? "bg-[var(--accent)]" : ""}`}
              >
                <p className="text-sm font-semibold truncate">{tc.title}</p>
                <p className="text-xs text-[var(--muted-foreground)] truncate">{moduleById.get(tc.module_id ?? "")?.path_label ?? tc.module_path_label}</p>
                <p className="text-xs text-[var(--muted-foreground)]">{tc.active_draft?.source_type ?? tc.source_type} · {tc.open_cycle?.submitted_by ?? "unknown"}</p>
              </button>
            ))}
            {queue.length === 0 && <p className="px-4 py-3 text-sm text-[var(--muted-foreground)]">暂无待评审项</p>}
          </CardContent>
        </Card>

        <div className="flex flex-col gap-4">
          {selectedCase?.active_draft ? (
            <>
              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)] mb-0.5">Draft</p>
                      <CardTitle>{selectedCase.active_draft.title}</CardTitle>
                      <p className="text-xs text-[var(--muted-foreground)] mt-0.5">{selectedCase.module_path_label ?? ""}</p>
                    </div>
                    <ReviewStatusBadge status={selectedCase.review_status ?? ""} />
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)] mb-2">当前正式版</p>
                      <CaseRevisionViewer revision={selectedCase.current_revision} />
                    </div>
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)] mb-2">草稿</p>
                      <ol className="flex flex-col gap-2">
                        {selectedCase.active_draft.steps.map((step, i) => (
                          <li key={i} className="text-sm">
                            <span className="font-medium">{step.action || "(空步骤)"}</span>
                            {step.expected && <span className="text-[var(--muted-foreground)]"> → {step.expected}</span>}
                          </li>
                        ))}
                      </ol>
                    </div>
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-5 flex flex-col gap-3">
                  <div className="flex flex-col gap-1.5">
                    <Label>评审意见</Label>
                    <Textarea value={reviewComment} onChange={(e) => setReviewComment(e.target.value)} rows={3} />
                  </div>
                  <div className="flex gap-2">
                    <Button disabled={busy} onClick={() => void handleAction("approve")}><CheckCircle2 size={15} />通过</Button>
                    <Button variant="outline" disabled={busy || !reviewComment.trim()} onClick={() => void handleAction("changes")}><MessageSquareWarning size={15} />要求修改</Button>
                    <Button variant="outline" disabled={busy} onClick={() => void handleAction("reject")}><XCircle size={15} />驳回</Button>
                  </div>
                </CardContent>
              </Card>
            </>
          ) : (
            <p className="text-sm text-[var(--muted-foreground)]">评审队列只展示 pending_review 项。</p>
          )}
        </div>
      </div>
    </div>
  );
}
