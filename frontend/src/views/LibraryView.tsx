import { FormEvent, useEffect, useMemo, useState } from "react";
import { FilePlus2, GitCompareArrows, RefreshCcw } from "lucide-react";
import { useParams } from "react-router-dom";
import {
  addressReviewChanges, type CaseDraftRecord, type CaseStep, createActiveEditDraft,
  createTestCase, getTestCase, listModules, listModuleTree, listTestCases,
  type ProjectModuleRecord, submitCaseDraftReview, type TestCasePayload,
  type TestCaseRecord, updateCaseDraft
} from "@/api/cases";
import { useCurrentWorkspace, useCurrentProject } from "@/stores/workspace-store";
import { useSessionStore } from "@/stores/session-store";
import { CaseDraftEditor } from "@/components/CaseDraftEditor";
import { CaseRevisionViewer } from "@/components/CaseRevisionViewer";
import { CaseStatusBadge } from "@/components/CaseStatusBadge";
import { ModuleTree } from "@/components/ModuleTree";
import { ReviewStatusBadge } from "@/components/ReviewStatusBadge";
import { StepsEditor } from "@/components/StepsEditor";
import { statusLabel } from "@/lib/labels";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";

const detailTabs = ["基本信息", "草稿/正式", "对比", "评审记录", "版本历史"] as const;

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

function draftOrRevision(tc: TestCaseRecord) {
  const draft = tc.active_draft;
  const snap = tc.current_revision?.content_snapshot;
  return {
    title: draft?.title ?? String(snap?.title ?? tc.title),
    steps: draft?.steps ?? normalizeSteps(snap?.steps),
    priority: draft?.priority ?? String(snap?.priority ?? "P2"),
    risk: draft?.risk ?? String(snap?.risk ?? "medium"),
    tags: draft?.tags ?? (Array.isArray(snap?.tags) ? snap.tags.map(String) : [])
  };
}

export function LibraryView() {
  const session = useSessionStore((s) => s.session);
  const ws = useCurrentWorkspace();
  const proj = useCurrentProject();
  const { wid = "", pid = "" } = useParams<{ wid: string; pid: string }>();
  const actorEmail = session?.user.email ?? "";
  const wid_ = (wid || ws?.id) ?? "";
  const pid_ = (pid || proj?.id) ?? "";

  const [modules, setModules] = useState<ProjectModuleRecord[]>([]);
  const [moduleTree, setModuleTree] = useState<Awaited<ReturnType<typeof listModuleTree>>>([]);
  const [selectedModuleId, setSelectedModuleId] = useState("");
  const [cases, setCases] = useState<TestCaseRecord[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState("");
  const [selectedCase, setSelectedCase] = useState<TestCaseRecord | null>(null);
  const [lifecycleFilter, setLifecycleFilter] = useState("");
  const [reviewFilter, setReviewFilter] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [search, setSearch] = useState("");
  const [activeTab, setActiveTab] = useState<(typeof detailTabs)[number]>("基本信息");
  const [newTitle, setNewTitle] = useState("新的测试用例");
  const [newModuleId, setNewModuleId] = useState("");
  const [newSteps, setNewSteps] = useState<CaseStep[]>([{ action: "打开目标功能", expected: "进入对应界面" }]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [createDraftOpen, setCreateDraftOpen] = useState(false);

  async function refreshDetail(caseId: string) {
    if (!caseId) { setSelectedCase(null); return; }
    setSelectedCase(await getTestCase(wid_, pid_, caseId));
  }

  async function refreshCases(preferredCaseId?: string, moduleOverride = selectedModuleId) {
    if (!wid_ || !pid_) return;
    const [mods, tree, cs] = await Promise.all([
      listModules(wid_, pid_),
      listModuleTree(wid_, pid_),
      listTestCases(wid_, pid_, moduleOverride || undefined, (reviewFilter || lifecycleFilter || undefined) as TestCaseRecord["lifecycle_status"] | "approved" | "pending_review" | "changes_requested" | undefined, { sourceType: sourceFilter || undefined, search: search || undefined })
    ]);
    setModules(mods); setModuleTree(tree); setCases(cs);
    if (!newModuleId && mods[0]) setNewModuleId(mods[0].id);
    const caseId = preferredCaseId ?? cs.find((c) => c.id === selectedCaseId)?.id ?? cs[0]?.id ?? "";
    setSelectedCaseId(caseId);
    await refreshDetail(caseId);
  }

  useEffect(() => {
    setBusy(true);
    refreshCases().finally(() => setBusy(false));
  }, [wid_, pid_]);

  async function handleCreateCase(e: FormEvent) {
    e.preventDefault();
    if (!wid_ || !pid_) return;
    setBusy(true); setMessage(null);
    try {
      const payload: TestCasePayload = { module_id: newModuleId || null, title: newTitle, steps: newSteps.filter((s) => s.action.trim() || s.expected.trim()), priority: "P2", risk: "medium", tags: ["manual"], custom_fields: {} };
      const created = await createTestCase(wid_, pid_, actorEmail, payload);
      setMessage(`已创建草稿：${created.title}`);
      setCreateDraftOpen(false);
      await refreshCases(created.id);
    } catch (err) { setMessage(err instanceof Error ? err.message : "创建失败"); }
    finally { setBusy(false); }
  }

  async function saveDraft(draft: CaseDraftRecord, payload: Partial<TestCasePayload>) {
    if (!wid_ || !pid_) return;
    setBusy(true); setMessage(null);
    try {
      await updateCaseDraft(wid_, pid_, draft.id, actorEmail, payload);
      setMessage("草稿已保存");
      await refreshCases(draft.test_case_id);
    } catch (err) { setMessage(err instanceof Error ? err.message : "保存失败"); }
    finally { setBusy(false); }
  }

  async function submitDraft(draft: CaseDraftRecord) {
    if (!wid_ || !pid_) return;
    setBusy(true); setMessage(null);
    try {
      await submitCaseDraftReview(wid_, pid_, draft.id, actorEmail);
      setMessage("已提交评审");
      await refreshCases(draft.test_case_id);
    } catch (err) { setMessage(err instanceof Error ? err.message : "提交失败"); }
    finally { setBusy(false); }
  }

  async function addressChanges(comment: string) {
    if (!wid_ || !pid_ || !selectedCase?.open_cycle) return;
    setBusy(true); setMessage(null);
    try {
      await addressReviewChanges(wid_, pid_, selectedCase.open_cycle.id, actorEmail, { comment });
      setMessage("已提交复审");
      await refreshCases(selectedCase.id);
    } catch (err) { setMessage(err instanceof Error ? err.message : "提交失败"); }
    finally { setBusy(false); }
  }

  async function createEditDraft() {
    if (!wid_ || !pid_ || !selectedCase) return;
    setBusy(true); setMessage(null);
    try {
      await createActiveEditDraft(wid_, pid_, selectedCase.id, actorEmail);
      setMessage("已创建正式用例编辑稿");
      await refreshCases(selectedCase.id);
    } catch (err) { setMessage(err instanceof Error ? err.message : "创建失败"); }
    finally { setBusy(false); }
  }

  const selectedContent = selectedCase ? draftOrRevision(selectedCase) : null;
  const moduleById = useMemo(() => new Map(modules.map((m) => [m.id, m])), [modules]);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)] mb-1">Case Library</p>
          <h1 className="font-heading text-2xl font-bold">用例库</h1>
          <p className="mt-1 text-sm text-[var(--muted-foreground)]">{cases.length} cases · 模块选择默认包含后代模块</p>
        </div>
        <Button variant="outline" size="icon" onClick={() => { setBusy(true); refreshCases().finally(() => setBusy(false)); }}><RefreshCcw size={16} /></Button>
      </div>
      {message && <Alert><AlertDescription>{message}</AlertDescription></Alert>}

      {/* Filter bar */}
      <form onSubmit={(e) => { e.preventDefault(); setBusy(true); refreshCases().finally(() => setBusy(false)); }} className="flex flex-wrap gap-2">
        <Select value={lifecycleFilter || "__none__"} onValueChange={(v) => setLifecycleFilter(v === "__none__" ? "" : v)}>
          <SelectTrigger className="w-32 h-8 text-xs"><SelectValue placeholder="全部资产" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="__none__">全部资产</SelectItem>
            <SelectItem value="draft">草稿</SelectItem>
            <SelectItem value="active">正式</SelectItem>
            <SelectItem value="archived">归档</SelectItem>
          </SelectContent>
        </Select>
        <Select value={reviewFilter || "__none__"} onValueChange={(v) => setReviewFilter(v === "__none__" ? "" : v)}>
          <SelectTrigger className="w-32 h-8 text-xs"><SelectValue placeholder="全部评审" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="__none__">全部评审</SelectItem>
            <SelectItem value="pending_review">待评审</SelectItem>
            <SelectItem value="changes_requested">要求修改</SelectItem>
          </SelectContent>
        </Select>
        <Select value={sourceFilter || "__none__"} onValueChange={(v) => setSourceFilter(v === "__none__" ? "" : v)}>
          <SelectTrigger className="w-28 h-8 text-xs"><SelectValue placeholder="全部来源" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="__none__">全部来源</SelectItem>
            <SelectItem value="manual">手工</SelectItem>
            <SelectItem value="import">导入</SelectItem>
            <SelectItem value="ai_suggestion">AI</SelectItem>
          </SelectContent>
        </Select>
        <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="搜索标题" className="h-8 text-xs w-40" />
        <Button type="submit" variant="outline" size="sm" className="h-8" disabled={busy}>筛选</Button>
      </form>

      <div className="grid grid-cols-1 gap-5 items-start xl:grid-cols-[minmax(180px,240px)_minmax(300px,0.9fr)_minmax(360px,1.2fr)]">
        {/* Module tree */}
        <Card className="min-w-0">
          <CardContent className="p-3">
            <ModuleTree modules={moduleTree} selectedModuleId={selectedModuleId} onSelect={(id) => { setSelectedModuleId(id); setBusy(true); refreshCases(undefined, id).finally(() => setBusy(false)); }} />
          </CardContent>
        </Card>

        {/* Case list + create */}
        <div className="flex min-w-0 flex-col gap-3 min-h-0">
          <div className="flex items-center justify-between gap-2">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">Cases</p>
              <h2 className="font-heading text-sm font-bold">用例列表</h2>
            </div>
            <Dialog open={createDraftOpen} onOpenChange={setCreateDraftOpen}>
              <DialogTrigger asChild>
                <Button type="button" variant="outline" size="sm" className="h-8 shrink-0">
                  <FilePlus2 size={14} />
                  新建草稿
                </Button>
              </DialogTrigger>
              <DialogContent className="max-h-[90vh] max-w-lg overflow-y-auto">
                <DialogHeader>
                  <DialogTitle>新建草稿</DialogTitle>
                </DialogHeader>
                <form onSubmit={handleCreateCase} className="flex flex-col gap-3">
                  <Input value={newTitle} onChange={(e) => setNewTitle(e.target.value)} placeholder="新用例标题" required className="h-8 text-sm" />
                  <Select value={newModuleId || "__none__"} onValueChange={(v) => setNewModuleId(v === "__none__" ? "" : v)}>
                    <SelectTrigger className="h-8 text-xs"><SelectValue placeholder="未归属" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__none__">未归属</SelectItem>
                      {modules.map((m) => <SelectItem key={m.id} value={m.id}>{m.path_label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                  <StepsEditor steps={newSteps} onChange={setNewSteps} disabled={busy} compact />
                  <Button type="submit" size="sm" disabled={busy || !wid_}>创建草稿</Button>
                </form>
              </DialogContent>
            </Dialog>
          </div>
          <Card className="flex min-h-0 flex-col overflow-hidden max-h-[min(680px,calc(100vh-320px))]">
            <CardContent className="min-h-0 flex-1 overflow-y-auto p-0">
              {cases.map((tc) => (
                <button key={tc.id} type="button" onClick={() => { setSelectedCaseId(tc.id); void refreshDetail(tc.id); }}
                  className={`w-full text-left px-4 py-3 border-b last:border-0 transition-colors hover:bg-[var(--muted)]/40 ${selectedCaseId === tc.id ? "bg-[var(--accent)]" : ""}`}>
                  <p className="text-sm font-semibold truncate">{tc.title}</p>
                  <p className="text-xs text-[var(--muted-foreground)] truncate">{tc.module_path_label || moduleById.get(tc.module_id ?? "")?.path_label || "未归属"}</p>
                  <p className="text-xs text-[var(--muted-foreground)]">{statusLabel[tc.lifecycle_status]} · rev {tc.current_revision_number}</p>
                </button>
              ))}
              {cases.length === 0 && <p className="px-4 py-3 text-sm text-[var(--muted-foreground)]">暂无用例</p>}
            </CardContent>
          </Card>
        </div>

        {/* Detail panel */}
        {selectedCase && selectedContent ? (
          <div className="flex min-w-0 flex-col gap-3">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="text-xs text-[var(--muted-foreground)] mb-0.5">{selectedCase.module_path_label}</p>
                <h2 className="font-heading text-lg font-bold truncate">{selectedContent.title}</h2>
              </div>
              <div className="flex gap-1.5 shrink-0">
                <CaseStatusBadge status={selectedCase.lifecycle_status} />
                <ReviewStatusBadge status={selectedCase.review_status ?? ""} />
              </div>
            </div>
            <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as typeof activeTab)}>
              <TabsList className="flex-wrap h-auto">{detailTabs.map((t) => <TabsTrigger key={t} value={t} className="text-xs">{t}</TabsTrigger>)}</TabsList>
            </Tabs>
            <Card>
              <CardContent className="pt-5">
                {activeTab === "基本信息" && (
                  <div className="flex flex-col gap-3">
                    <div className="flex flex-wrap gap-2 text-xs text-[var(--muted-foreground)]">
                      <span>{selectedContent.priority}</span><span>{selectedContent.risk}</span>
                      <span>{selectedCase.source_type}</span><span>rev {selectedCase.current_revision_number}</span>
                    </div>
                    <ol className="flex flex-col gap-2">
                      {selectedContent.steps.map((step, i) => (
                        <li key={i} className="text-sm">
                          <span className="font-medium">{step.action || "(空步骤)"}</span>
                          {step.expected && <span className="text-[var(--muted-foreground)]"> → {step.expected}</span>}
                        </li>
                      ))}
                    </ol>
                    <p className="text-xs text-[var(--muted-foreground)]">{selectedContent.tags.join(", ") || "无标签"}</p>
                  </div>
                )}
                {activeTab === "草稿/正式" && (
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
                    <div className="flex flex-col gap-3">
                      <CaseRevisionViewer revision={selectedCase.current_revision} />
                      {selectedCase.lifecycle_status === "active" && (
                        <Button variant="outline" size="sm" disabled={busy} onClick={() => void createEditDraft()}>
                          <GitCompareArrows size={14} />创建编辑稿
                        </Button>
                      )}
                    </div>
                  )
                )}
                {activeTab === "对比" && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div><p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)] mb-2">当前正式版</p><CaseRevisionViewer revision={selectedCase.current_revision} /></div>
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)] mb-2">草稿</p>
                      {selectedCase.active_draft ? (
                        <ol className="flex flex-col gap-2">{selectedCase.active_draft.steps.map((step, i) => <li key={i} className="text-sm"><span className="font-medium">{step.action}</span>{step.expected && <span className="text-[var(--muted-foreground)]"> → {step.expected}</span>}</li>)}</ol>
                      ) : <p className="text-sm text-[var(--muted-foreground)]">暂无待对比草稿</p>}
                    </div>
                  </div>
                )}
                {activeTab === "评审记录" && (
                  <div className="flex flex-col gap-2">
                    {(selectedCase.review_events ?? []).map((ev) => (
                      <div key={ev.id} className="flex flex-col gap-0.5 border-b pb-2 last:border-0">
                        <div className="flex items-center gap-2"><span className="text-xs font-mono bg-[var(--muted)] px-1.5 py-0.5 rounded">{statusLabel[ev.action] ?? ev.action}</span><p className="text-sm">{ev.comment || ev.actor_email}</p></div>
                        <p className="text-xs text-[var(--muted-foreground)]">{ev.actor_email} · {new Date(ev.created_at).toLocaleString()}</p>
                      </div>
                    ))}
                    {(selectedCase.review_events ?? []).length === 0 && <p className="text-sm text-[var(--muted-foreground)]">暂无评审记录</p>}
                  </div>
                )}
                {activeTab === "版本历史" && (
                  <div className="flex flex-col gap-2">
                    {(selectedCase.revisions ?? []).map((rev) => (
                      <div key={rev.id} className="flex items-center justify-between border-b pb-2 last:border-0">
                        <div><p className="text-sm font-semibold">Rev {rev.revision_number}</p><p className="text-xs text-[var(--muted-foreground)]">{rev.created_by} · {new Date(rev.created_at).toLocaleString()}</p></div>
                      </div>
                    ))}
                    {(selectedCase.revisions ?? []).length === 0 && <p className="text-sm text-[var(--muted-foreground)]">暂无版本历史</p>}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        ) : (
          <Card className="min-w-0 min-h-[420px]">
            <CardContent className="flex min-h-[420px] flex-col items-center justify-center gap-2 p-8 text-center">
              <p className="text-sm font-medium">从左侧选择一个用例查看详情</p>
              <p className="text-sm text-[var(--muted-foreground)]">或点击「新建草稿」创建第一条用例</p>
              <Button type="button" variant="outline" size="sm" className="mt-2" onClick={() => setCreateDraftOpen(true)}>
                <FilePlus2 size={14} />
                新建草稿
              </Button>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
