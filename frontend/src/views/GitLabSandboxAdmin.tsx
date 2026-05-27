import { FormEvent, useEffect, useState } from "react";
import { GitBranch, GitCommitHorizontal, KeyRound } from "lucide-react";
import { useParams } from "react-router-dom";
import {
  bindRepository, getGitLabToken, type GitLabTokenRecord, type GitRepositoryRecord,
  type JobRecord, listJobs, listRepositories, syncRepository, upsertGitLabToken
} from "@/api/git";
import { listProjects, type ProjectRecord } from "@/api/workspace";
import { useCurrentWorkspace } from "@/stores/workspace-store";
import { useSessionStore } from "@/stores/session-store";
import { Pagination } from "@/components/Pagination";
import { usePagination } from "@/hooks/usePagination";
import { statusLabel } from "@/lib/labels";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export function GitLabSandboxAdmin() {
  const session = useSessionStore((s) => s.session);
  const ws = useCurrentWorkspace();
  const actorEmail = session?.user.email ?? "";
  const wid = ws?.id ?? "";

  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [tokenConfig, setTokenConfig] = useState<GitLabTokenRecord | null>(null);
  const [repositories, setRepositories] = useState<GitRepositoryRecord[]>([]);
  const [jobs, setJobs] = useState<JobRecord[]>([]);
  const [gitlabBaseUrl, setGitlabBaseUrl] = useState("https://gitlab.example.com");
  const [gitlabToken, setGitlabToken] = useState("");
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [repositoryName, setRepositoryName] = useState("Checkout API");
  const [remoteUrl, setRemoteUrl] = useState("https://gitlab.example.com/team/checkout-api.git");
  const [defaultBranch, setDefaultBranch] = useState("main");
  const [repoSizeLimitMb, setRepoSizeLimitMb] = useState("1024");
  const [diffFileLimit, setDiffFileLimit] = useState("500");
  const [syncTimeoutSeconds, setSyncTimeoutSeconds] = useState("120");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const jobsPagination = usePagination(jobs, 8);

  async function refresh() {
    if (!wid) return;
    const [token, ps, repos, js] = await Promise.all([getGitLabToken(wid), listProjects(wid), listRepositories(wid), listJobs(wid)]);
    setTokenConfig(token); if (token) setGitlabBaseUrl(token.gitlab_base_url);
    setProjects(ps); setRepositories(repos); setJobs(js);
    if (!selectedProjectId && ps[0]) setSelectedProjectId(ps[0].id);
  }

  useEffect(() => { void refresh(); }, [wid]);

  async function handleTokenSave(e: FormEvent) {
    e.preventDefault();
    if (!wid) return;
    setBusy(true); setMessage(null);
    try {
      const t = await upsertGitLabToken(wid, actorEmail, { gitlab_base_url: gitlabBaseUrl, token: gitlabToken });
      setTokenConfig(t); setGitlabToken(""); setMessage(`已保存 GitLab token：${t.token_masked}`);
      await refresh();
    } catch (err) { setMessage(err instanceof Error ? err.message : "Token 保存失败"); }
    finally { setBusy(false); }
  }

  async function handleRepositoryBind(e: FormEvent) {
    e.preventDefault();
    if (!wid || !selectedProjectId) return;
    setBusy(true); setMessage(null);
    try {
      const r = await bindRepository(wid, actorEmail, { project_id: selectedProjectId, name: repositoryName, remote_url: remoteUrl, default_branch: defaultBranch, repo_size_limit_mb: Number(repoSizeLimitMb), diff_file_limit: Number(diffFileLimit), sync_timeout_seconds: Number(syncTimeoutSeconds) });
      setMessage(`已绑定仓库：${r.name}`); await refresh();
    } catch (err) { setMessage(err instanceof Error ? err.message : "仓库绑定失败"); }
    finally { setBusy(false); }
  }

  async function handleSync(repositoryId: string) {
    if (!wid) return;
    setBusy(true); setMessage(null);
    try {
      const job = await syncRepository(wid, repositoryId, actorEmail);
      setMessage(`已创建同步 Job：${job.status}`); await refresh();
    } catch (err) { setMessage(err instanceof Error ? err.message : "同步失败"); }
    finally { setBusy(false); }
  }

  const f = "flex flex-col gap-1.5";

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)] mb-1">GitLab</p>
          <h1 className="font-heading text-2xl font-bold">只读仓库和 Git Sandbox</h1>
        </div>
        <GitCommitHorizontal size={20} className="text-[var(--muted-foreground)]" />
      </div>
      {message && <Alert><AlertDescription>{message}</AlertDescription></Alert>}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><KeyRound size={16} />Workspace GitLab Token</CardTitle></CardHeader>
          <CardContent>
            <form onSubmit={handleTokenSave} className="flex flex-col gap-3">
              <div className={f}><Label>GitLab Base URL</Label><Input value={gitlabBaseUrl} onChange={(e) => setGitlabBaseUrl(e.target.value)} required /></div>
              <div className={f}><Label>Token</Label><Input type="password" value={gitlabToken} onChange={(e) => setGitlabToken(e.target.value)} required /></div>
              <Button type="submit" disabled={busy || !wid} className="self-start">保存 Token</Button>
            </form>
            {tokenConfig && <p className="mt-3 text-xs text-[var(--muted-foreground)]">{tokenConfig.gitlab_base_url} · token {tokenConfig.token_masked} · updated by {tokenConfig.updated_by}</p>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><GitBranch size={16} />项目仓库绑定</CardTitle></CardHeader>
          <CardContent>
            <form onSubmit={handleRepositoryBind} className="flex flex-col gap-3">
              <div className={f}>
                <Label>Project</Label>
                <Select value={selectedProjectId} onValueChange={setSelectedProjectId} disabled={projects.length === 0}>
                  <SelectTrigger><SelectValue placeholder="选择 Project" /></SelectTrigger>
                  <SelectContent>{projects.map((p) => <SelectItem key={p.id} value={p.id}>{p.key} · {p.name}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className={f}><Label>仓库名称</Label><Input value={repositoryName} onChange={(e) => setRepositoryName(e.target.value)} required /></div>
                <div className={f}><Label>默认分支</Label><Input value={defaultBranch} onChange={(e) => setDefaultBranch(e.target.value)} required /></div>
              </div>
              <div className={f}><Label>Remote URL</Label><Input value={remoteUrl} onChange={(e) => setRemoteUrl(e.target.value)} required /></div>
              <div className="grid grid-cols-3 gap-3">
                <div className={f}><Label>大小限制 MB</Label><Input value={repoSizeLimitMb} onChange={(e) => setRepoSizeLimitMb(e.target.value)} /></div>
                <div className={f}><Label>Diff 文件数</Label><Input value={diffFileLimit} onChange={(e) => setDiffFileLimit(e.target.value)} /></div>
                <div className={f}><Label>超时秒数</Label><Input value={syncTimeoutSeconds} onChange={(e) => setSyncTimeoutSeconds(e.target.value)} /></div>
              </div>
              <Button type="submit" disabled={busy || !wid || !selectedProjectId} className="self-start">绑定仓库</Button>
            </form>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle>仓库工作副本</CardTitle></CardHeader>
        <CardContent className="p-0">
          {repositories.map((r) => (
            <div key={r.id} className="flex items-center justify-between gap-3 px-5 py-3 border-b last:border-0">
              <div className="min-w-0">
                <p className="text-sm font-semibold">{r.name} · {statusLabel[r.status]}</p>
                <p className="text-xs text-[var(--muted-foreground)] truncate">{r.remote_url}</p>
                <p className="text-xs font-mono text-[var(--muted-foreground)] truncate">{r.mirror_path}</p>
              </div>
              <Button variant="outline" size="sm" disabled={busy} onClick={() => void handleSync(r.id)}>同步</Button>
            </div>
          ))}
          {repositories.length === 0 && <p className="px-5 py-4 text-sm text-[var(--muted-foreground)]">暂无仓库</p>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Jobs</CardTitle></CardHeader>
        <CardContent className="p-0">
          {jobsPagination.currentItems.map((job) => (
            <div key={job.id} className="flex items-center justify-between gap-3 px-5 py-3 border-b last:border-0">
              <div className="min-w-0">
                <p className="text-sm font-semibold truncate">{job.input_summary}</p>
                <p className="text-xs text-[var(--muted-foreground)]">{job.input_summary} · {statusLabel[job.status]}</p>
              </div>
              <span className="text-xs text-[var(--muted-foreground)] shrink-0">{new Date(job.created_at).toLocaleString()}</span>
            </div>
          ))}
          {jobs.length === 0 && <p className="px-5 py-4 text-sm text-[var(--muted-foreground)]">暂无 Jobs</p>}
          <div className="px-5"><Pagination currentPage={jobsPagination.currentPage} totalPages={jobsPagination.totalPages} totalItems={jobsPagination.totalItems} onPageChange={jobsPagination.goToPage} itemsPerPage={8} /></div>
        </CardContent>
      </Card>
    </div>
  );
}
