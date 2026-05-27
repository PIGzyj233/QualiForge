import { FormEvent, useEffect, useState } from "react";
import { ClipboardCheck, FileText } from "lucide-react";
import { useParams } from "react-router-dom";
import {
  bulkImportTestCases, bulkUpdateImportDrafts, type CaseStep, type ImportBatchRecord,
  type ImportDraftRecord, listImportBatches, listImportDrafts, listModules,
  listTestCases, type ProjectModuleRecord, submitImportReview, type TestCaseRecord, uploadImportBatch
} from "@/api/cases";
import { useCurrentWorkspace, useCurrentProject } from "@/stores/workspace-store";
import { useSessionStore } from "@/stores/session-store";
import { Pagination } from "@/components/Pagination";
import { StepsEditor } from "@/components/StepsEditor";
import { usePagination } from "@/hooks/usePagination";
import { statusLabel } from "@/lib/labels";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { StatusPill } from "@/components/StatusPill";

export function CaseImportAdmin() {
  const session = useSessionStore((s) => s.session);
  const ws = useCurrentWorkspace();
  const proj = useCurrentProject();
  const { wid = "", pid = "" } = useParams<{ wid: string; pid: string }>();
  const actorEmail = session?.user.email ?? "";
  const wid_ = (wid || ws?.id) ?? "";
  const pid_ = (pid || proj?.id) ?? "";

  const [modules, setModules] = useState<ProjectModuleRecord[]>([]);
  const [batches, setBatches] = useState<ImportBatchRecord[]>([]);
  const [selectedBatchId, setSelectedBatchId] = useState("");
  const [drafts, setDrafts] = useState<ImportDraftRecord[]>([]);
  const [testCases, setTestCases] = useState<TestCaseRecord[]>([]);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [bulkTitle, setBulkTitle] = useState("");
  const [bulkModuleId, setBulkModuleId] = useState("");
  const [bulkSteps, setBulkSteps] = useState<CaseStep[]>([]);
  const [bulkPriority, setBulkPriority] = useState("P1");
  const [bulkRisk, setBulkRisk] = useState("high");
  const [bulkTags, setBulkTags] = useState("checkout, imported");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const draftsPagination = usePagination(drafts, 10);

  async function refresh(preferredBatchId?: string) {
    if (!wid_ || !pid_) return;
    const [mods, bs, cases] = await Promise.all([listModules(wid_, pid_), listImportBatches(wid_, pid_), listTestCases(wid_, pid_)]);
    setModules(mods); setBatches(bs); setTestCases(cases);
    const batchId = preferredBatchId ?? bs[0]?.id ?? "";
    setSelectedBatchId(batchId);
    if (!bulkModuleId && mods[0]) setBulkModuleId(mods[0].id);
    if (batchId) setDrafts(await listImportDrafts(wid_, pid_, batchId));
  }

  useEffect(() => { void refresh(); }, [wid_, pid_]);

  async function handleUpload(e: FormEvent) {
    e.preventDefault();
    if (!wid_ || !pid_ || !importFile) return;
    setBusy(true); setMessage(null);
    try {
      const batch = await uploadImportBatch(wid_, pid_, actorEmail, importFile);
      await new Promise((r) => window.setTimeout(r, 700));
      setMessage(`已上传：${batch.file_name}`); setImportFile(null);
      await refresh(batch.id);
    } catch (err) { setMessage(err instanceof Error ? err.message : "上传失败"); }
    finally { setBusy(false); }
  }

  async function handleBulkUpdate() {
    if (!wid_ || !pid_ || !selectedBatchId) return;
    setBusy(true); setMessage(null);
    try {
      const payload: Record<string, unknown> = {};
      if (bulkTitle.trim()) payload.title = bulkTitle.trim();
      if (bulkModuleId) payload.module_id = bulkModuleId;
      const steps = bulkSteps.filter((s) => s.action.trim() || s.expected.trim());
      if (steps.length) payload.steps = steps;
      if (bulkPriority.trim()) payload.priority = bulkPriority.trim();
      if (bulkRisk.trim()) payload.risk = bulkRisk.trim();
      const tags = bulkTags.split(/[,，;；\s]+/).map((t) => t.trim()).filter(Boolean);
      if (tags.length) payload.tags = tags;
      await bulkUpdateImportDrafts(wid_, pid_, selectedBatchId, actorEmail, payload);
      setMessage("已批量修正导入草稿");
      await refresh(selectedBatchId);
    } catch (err) { setMessage(err instanceof Error ? err.message : "批量修正失败"); }
    finally { setBusy(false); }
  }

  async function handleSubmitReview() {
    if (!wid_ || !pid_ || !selectedBatchId) return;
    setBusy(true); setMessage(null);
    try {
      const batch = await submitImportReview(wid_, pid_, selectedBatchId, actorEmail);
      setMessage(`已提交评审：${statusLabel[batch.status]}`);
      await refresh(selectedBatchId);
    } catch (err) { setMessage(err instanceof Error ? err.message : "提交失败"); }
    finally { setBusy(false); }
  }

  async function handleBulkImport() {
    if (!wid_ || !pid_ || !selectedBatchId) return;
    setBusy(true); setMessage(null);
    try {
      const r = await bulkImportTestCases(wid_, pid_, selectedBatchId, actorEmail);
      setMessage(`已完成入库：${r.imported_count} 条`);
      await refresh(selectedBatchId);
    } catch (err) { setMessage(err instanceof Error ? err.message : "入库失败"); }
    finally { setBusy(false); }
  }

  const selectedBatch = batches.find((b) => b.id === selectedBatchId);
  const f = "flex flex-col gap-1.5";

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)] mb-1">Case Import</p>
          <h1 className="font-heading text-2xl font-bold">历史用例导入</h1>
          <p className="mt-1 text-sm text-[var(--muted-foreground)]">{batches.length} 批次 · {drafts.length} 草稿 · {testCases.length} 正式用例</p>
        </div>
        <ClipboardCheck size={20} className="text-[var(--muted-foreground)]" />
      </div>
      {message && <Alert><AlertDescription>{message}</AlertDescription></Alert>}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><FileText size={16} />上传 Excel / CSV</CardTitle></CardHeader>
          <CardContent>
            <form onSubmit={handleUpload} className="flex flex-col gap-3">
              <input type="file" accept=".csv,.xlsx" onChange={(e) => setImportFile(e.target.files?.[0] ?? null)} className="text-sm" />
              <Button type="submit" disabled={busy || !wid_ || !pid_ || !importFile} className="self-start">上传并解析</Button>
            </form>
            {batches.length > 0 && (
              <div className="mt-4 flex flex-col gap-1.5">
                <Label>选择批次</Label>
                <Select value={selectedBatchId} onValueChange={async (v) => { setSelectedBatchId(v); if (wid_ && pid_ && v) setDrafts(await listImportDrafts(wid_, pid_, v)); }}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{batches.map((b) => <SelectItem key={b.id} value={b.id}>{b.file_name} · {statusLabel[b.status]}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>批量修正草稿</CardTitle></CardHeader>
          <CardContent className="flex flex-col gap-3">
            <div className="grid grid-cols-2 gap-3">
              <div className={f}><Label>标题（可选）</Label><Input value={bulkTitle} onChange={(e) => setBulkTitle(e.target.value)} placeholder="留空则不修改" /></div>
              <div className={f}>
                <Label>模块</Label>
                <Select value={bulkModuleId} onValueChange={setBulkModuleId} disabled={modules.length === 0}>
                  <SelectTrigger><SelectValue placeholder="选择模块" /></SelectTrigger>
                  <SelectContent>{modules.map((m) => <SelectItem key={m.id} value={m.id}>{m.path_label}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className={f}><Label>优先级</Label><Input value={bulkPriority} onChange={(e) => setBulkPriority(e.target.value)} /></div>
              <div className={f}><Label>风险</Label><Input value={bulkRisk} onChange={(e) => setBulkRisk(e.target.value)} /></div>
            </div>
            <div className={f}><Label>标签（逗号分隔）</Label><Input value={bulkTags} onChange={(e) => setBulkTags(e.target.value)} /></div>
            <StepsEditor steps={bulkSteps} onChange={setBulkSteps} />
            <div className="flex gap-2 flex-wrap">
              <Button variant="outline" disabled={busy || !selectedBatchId} onClick={handleBulkUpdate}>批量修正</Button>
              <Button variant="outline" disabled={busy || !selectedBatchId} onClick={handleSubmitReview}>提交评审</Button>
              <Button disabled={busy || !selectedBatchId} onClick={handleBulkImport}>完成入库</Button>
            </div>
          </CardContent>
        </Card>
      </div>

      {drafts.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-sm">导入草稿 ({drafts.length})</CardTitle></CardHeader>
          <CardContent className="p-0">
            {draftsPagination.currentItems.map((draft) => (
              <div key={draft.id} className="flex items-center justify-between gap-3 px-5 py-3 border-b last:border-0">
                <div className="min-w-0">
                  <p className="text-sm font-semibold truncate">{draft.title}</p>
                  <p className="text-xs text-[var(--muted-foreground)]">{draft.priority} · {draft.risk}</p>
                </div>
                <StatusPill status={draft.status} />
              </div>
            ))}
            <div className="px-5"><Pagination currentPage={draftsPagination.currentPage} totalPages={draftsPagination.totalPages} totalItems={draftsPagination.totalItems} onPageChange={draftsPagination.goToPage} itemsPerPage={10} /></div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
