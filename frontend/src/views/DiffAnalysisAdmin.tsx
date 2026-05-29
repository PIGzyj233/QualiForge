import { FormEvent, useEffect, useState } from "react";
import { ChevronDown, ChevronRight, GitCommitHorizontal, Network, ShieldAlert } from "lucide-react";
import { useParams } from "react-router-dom";
import { createDiffAnalysis, type DiffAnalysisRecord, listDiffAnalyses } from "@/api/cases";
import { type GitRepositoryRecord, listRepositories } from "@/api/git";
import { useCurrentWorkspace, useCurrentProject } from "@/stores/workspace-store";
import { useSessionStore } from "@/stores/session-store";
import { statusLabel, riskLabel, changeTypeLabel } from "@/lib/labels";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";

function diffLineClass(line: string) {
  if (line.startsWith("+")) return "text-green-700 dark:text-green-400 bg-green-50 dark:bg-green-900/20";
  if (line.startsWith("-")) return "text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-900/20";
  if (line.startsWith("@@")) return "text-blue-700 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/20";
  return "text-[var(--muted-foreground)]";
}

const riskVariant: Record<string, "destructive" | "warning" | "success" | "secondary"> = {
  critical: "destructive", high: "destructive", medium: "warning", low: "success", none: "secondary"
};

function formatDateTime(value: string | null) {
  return value ? new Date(value).toLocaleString() : "尚未同步";
}

export function DiffAnalysisAdmin() {
  const session = useSessionStore((s) => s.session);
  const ws = useCurrentWorkspace();
  const proj = useCurrentProject();
  const { wid = "", pid = "" } = useParams<{ wid: string; pid: string }>();
  const actorEmail = session?.user.email ?? "";
  const wid_ = (wid || ws?.id) ?? "";
  const pid_ = (pid || proj?.id) ?? "";

  const [repositories, setRepositories] = useState<GitRepositoryRecord[]>([]);
  const [selectedRepositoryId, setSelectedRepositoryId] = useState("");
  const [analyses, setAnalyses] = useState<DiffAnalysisRecord[]>([]);
  const [selectedAnalysisId, setSelectedAnalysisId] = useState("");
  const [baseRef, setBaseRef] = useState("v1");
  const [targetRef, setTargetRef] = useState("v2");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [expandedPaths, setExpandedPaths] = useState<string[]>([]);

  async function refresh() {
    if (!wid_ || !pid_) return;
    const [repos, anals] = await Promise.all([listRepositories(wid_, pid_), listDiffAnalyses(wid_, pid_)]);
    setRepositories(repos); setAnalyses(anals);
    const synced = repos.find((r) => r.status === "synced");
    if (!selectedRepositoryId && synced) setSelectedRepositoryId(synced.id);
    if (!selectedAnalysisId && anals[0]) setSelectedAnalysisId(anals[0].id);
  }

  useEffect(() => { void refresh(); }, [wid_, pid_]);

  async function handleRunDiff(e: FormEvent) {
    e.preventDefault();
    if (!wid_ || !pid_ || !selectedRepositoryId) return;
    setBusy(true); setMessage(null);
    try {
      const a = await createDiffAnalysis(wid_, pid_, actorEmail, { repository_id: selectedRepositoryId, base_ref: baseRef, target_ref: targetRef });
      await refresh();
      setSelectedAnalysisId(a.id);
      if (a.status === "failed") {
        setMessage(`Diff 分析失败：${a.error_summary || "请查看任务日志"}`);
      } else {
        setMessage(`已完成 Diff 分析：${riskLabel[a.risk_level]} · ${a.file_changes.length} files`);
      }
    } catch (err) { setMessage(err instanceof Error ? err.message : "Diff 分析失败"); }
    finally { setBusy(false); }
  }

  const selectedAnalysis = analyses.find((a) => a.id === selectedAnalysisId);
  const selectedRepository = repositories.find((r) => r.id === selectedRepositoryId);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)] mb-1">Diff Decision</p>
          <h1 className="font-heading text-2xl font-bold">Tag Diff 模块影响分析</h1>
        </div>
        <Network size={20} className="text-[var(--muted-foreground)]" />
      </div>
      {message && <Alert><AlertDescription>{message}</AlertDescription></Alert>}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><GitCommitHorizontal size={16} />运行 DiffAnalysis</CardTitle></CardHeader>
          <CardContent>
            <form onSubmit={handleRunDiff} className="flex flex-col gap-3">
              <div className="flex flex-col gap-1.5">
                <Label>Repository</Label>
                <Select value={selectedRepositoryId} onValueChange={setSelectedRepositoryId} disabled={repositories.length === 0}>
                  <SelectTrigger><SelectValue placeholder="选择 Repository" /></SelectTrigger>
                  <SelectContent>{repositories.map((r) => <SelectItem key={r.id} value={r.id}>{r.name} · {statusLabel[r.status]}</SelectItem>)}</SelectContent>
                </Select>
                {selectedRepository && (
                  <p className="text-xs text-[var(--muted-foreground)]">
                    上次同步：{formatDateTime(selectedRepository.last_synced_at)}。运行前会自动刷新远端 tag/ref。
                  </p>
                )}
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="flex flex-col gap-1.5"><Label>Base ref/tag</Label><Input value={baseRef} onChange={(e) => setBaseRef(e.target.value)} required /></div>
                <div className="flex flex-col gap-1.5"><Label>Target ref/tag</Label><Input value={targetRef} onChange={(e) => setTargetRef(e.target.value)} required /></div>
              </div>
              <Button type="submit" disabled={busy || !selectedRepositoryId} className="self-start">运行 Diff</Button>
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2"><ShieldAlert size={16} />推荐测试范围</CardTitle>
              {selectedAnalysis && (
                <Badge variant={selectedAnalysis.status === "failed" ? "destructive" : (riskVariant[selectedAnalysis.risk_level] ?? "secondary")}>
                  {selectedAnalysis.status === "failed" ? statusLabel[selectedAnalysis.status] : riskLabel[selectedAnalysis.risk_level]}
                </Badge>
              )}
            </div>
          </CardHeader>
          <CardContent>
            {selectedAnalysis ? (
              <div className="flex flex-col gap-2">
                <div className="flex gap-2 flex-wrap">
                  <Select value={selectedAnalysisId} onValueChange={setSelectedAnalysisId}>
                    <SelectTrigger className="w-auto"><SelectValue /></SelectTrigger>
                    <SelectContent>{analyses.map((a) => <SelectItem key={a.id} value={a.id}>{a.base_ref} → {a.target_ref}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                <p className="text-sm font-semibold">{selectedAnalysis.summary}</p>
                <p className="text-xs text-[var(--muted-foreground)]">{selectedAnalysis.base_ref} → {selectedAnalysis.target_ref} · {statusLabel[selectedAnalysis.status]}</p>
                {selectedAnalysis.status === "failed" ? (
                  <div className="flex flex-col gap-1 mt-1">
                    <p className="text-sm text-[var(--destructive)]">{selectedAnalysis.error_summary || "Diff 分析失败"}</p>
                    {selectedAnalysis.key_logs.slice(-6).map((log, index) => (
                      <p key={`${selectedAnalysis.id}-log-${index}`} className="text-xs font-mono text-[var(--muted-foreground)] truncate">{log}</p>
                    ))}
                  </div>
                ) : (
                  <ul className="flex flex-col gap-1 mt-1">
                    {selectedAnalysis.recommended_scope.slice(0, 5).map((s) => <li key={s} className="text-sm text-[var(--muted-foreground)]">· {s}</li>)}
                  </ul>
                )}
              </div>
            ) : <p className="text-sm text-[var(--muted-foreground)]">暂无 Diff 分析结果</p>}
          </CardContent>
        </Card>
      </div>

      {selectedAnalysis && (
        <>
          <Card>
            <CardHeader><CardTitle>模块影响和风险</CardTitle></CardHeader>
            <CardContent className="p-0">
              {selectedAnalysis.module_impacts.map((impact) => (
                <div key={`${impact.module_key}-${impact.risk_level}`} className="flex items-center justify-between gap-3 px-5 py-3 border-b last:border-0">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold">{impact.module_key} · {impact.module_name}</p>
                    <p className="text-xs text-[var(--muted-foreground)]">{impact.changed_file_count} files · confidence {impact.confidence}%</p>
                    <p className="text-xs text-[var(--muted-foreground)]">{impact.recommended_tests.join(" · ")}</p>
                  </div>
                  <Badge variant={riskVariant[impact.risk_level] ?? "secondary"}>{riskLabel[impact.risk_level]}</Badge>
                </div>
              ))}
              {selectedAnalysis.module_impacts.length === 0 && <p className="px-5 py-4 text-sm text-[var(--muted-foreground)]">暂无模块影响</p>}
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>文件和结构证据</CardTitle></CardHeader>
            <CardContent className="p-0">
              {selectedAnalysis.file_changes.map((fc) => {
                const key = fc.path;
                const expanded = expandedPaths.includes(key);
                return (
                  <div key={key} className="border-b last:border-0">
                    <button
                      type="button"
                      onClick={() => setExpandedPaths((p) => expanded ? p.filter((x) => x !== key) : [...p, key])}
                      className="w-full flex items-center gap-2 px-5 py-3 text-left hover:bg-[var(--muted)]/40 transition-colors"
                    >
                      {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                      <span className="font-mono text-xs flex-1 truncate">{fc.path}</span>
                      <Badge variant="outline" className="shrink-0">{changeTypeLabel[fc.change_type] ?? fc.change_type}</Badge>
                    </button>
                    {expanded && (fc.diff_hunks ?? []).length > 0 && (
                      <pre className="px-5 pb-3 text-xs font-mono overflow-x-auto bg-[var(--muted)]/30">
                        {(fc.diff_hunks ?? []).flatMap((h) => h.lines).map((line, i) => (
                          <div key={i} className={diffLineClass(line)}>{line}</div>
                        ))}
                      </pre>
                    )}
                  </div>
                );
              })}
              {selectedAnalysis.file_changes.length === 0 && <p className="px-5 py-4 text-sm text-[var(--muted-foreground)]">暂无文件证据</p>}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
