import { FormEvent, useEffect, useState } from "react";
import { Database, GitBranch, GitCommitHorizontal, KeyRound } from "lucide-react";
import { useParams } from "react-router-dom";
import {
  bindRepository,
  getGitLabToken,
  GitLabTokenRecord,
  GitRepositoryRecord,
  JobRecord,
  listJobs,
  listProjects,
  listRepositories,
  listWorkspaces,
  ProjectRecord,
  Session,
  syncRepository,
  upsertGitLabToken,
  WorkspaceRecord
} from "../api";
import { Pagination } from "../components/Pagination";
import { usePagination } from "../hooks/usePagination";
import { statusLabel } from "../lib/labels";
import { pickExistingId } from "../lib/selection";

export function GitLabSandboxAdmin({ session }: { session: Session }) {
  const actorEmail = session.user.email;
  const { wid: routeWorkspaceId = "", pid: routeProjectId = "" } = useParams<{ wid: string; pid: string }>();
  const [workspaces, setWorkspaces] = useState<WorkspaceRecord[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState("");
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [tokenConfig, setTokenConfig] = useState<GitLabTokenRecord | null>(null);
  const [repositories, setRepositories] = useState<GitRepositoryRecord[]>([]);
  const [jobs, setJobs] = useState<JobRecord[]>([]);
  const [gitlabBaseUrl, setGitlabBaseUrl] = useState("https://gitlab.example.com");
  const [gitlabToken, setGitlabToken] = useState("");
  const [projectId, setProjectId] = useState("");
  const [repositoryName, setRepositoryName] = useState("Checkout API");
  const [remoteUrl, setRemoteUrl] = useState("https://gitlab.example.com/team/checkout-api.git");
  const [defaultBranch, setDefaultBranch] = useState("main");
  const [repoSizeLimitMb, setRepoSizeLimitMb] = useState("1024");
  const [diffFileLimit, setDiffFileLimit] = useState("500");
  const [syncTimeoutSeconds, setSyncTimeoutSeconds] = useState("120");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const jobsPagination = usePagination(jobs, 8);

  async function refreshGitWorkspaces(preferredWorkspaceId?: string, preferredProjectId?: string) {
    setBusy(true);
    setMessage(null);
    try {
      const nextWorkspaces = await listWorkspaces(actorEmail);
      setWorkspaces(nextWorkspaces);
      const nextSelectedId = pickExistingId(nextWorkspaces, preferredWorkspaceId, selectedWorkspaceId);
      setSelectedWorkspaceId(nextSelectedId);
      if (nextSelectedId) {
        await refreshGitConfig(nextSelectedId, preferredProjectId);
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "GitLab 配置加载失败");
    } finally {
      setBusy(false);
    }
  }

  async function refreshGitConfig(workspaceId: string, preferredProjectId?: string) {
    const [nextToken, nextProjects, nextRepositories, nextJobs] = await Promise.all([
      getGitLabToken(workspaceId),
      listProjects(workspaceId),
      listRepositories(workspaceId),
      listJobs(workspaceId)
    ]);
    setTokenConfig(nextToken);
    if (nextToken) {
      setGitlabBaseUrl(nextToken.gitlab_base_url);
    }
    setProjects(nextProjects);
    setRepositories(nextRepositories);
    setJobs(nextJobs);
    setProjectId(pickExistingId(nextProjects, preferredProjectId, projectId));
  }

  useEffect(() => {
    void refreshGitWorkspaces(routeWorkspaceId || undefined, routeProjectId || undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routeWorkspaceId, routeProjectId]);

  async function handleWorkspaceSwitch(workspaceId: string) {
    setSelectedWorkspaceId(workspaceId);
    setBusy(true);
    setMessage(null);
    try {
      await refreshGitConfig(workspaceId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Git Workspace 切换失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleTokenSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedWorkspaceId) return;
    setBusy(true);
    setMessage(null);
    try {
      const token = await upsertGitLabToken(selectedWorkspaceId, actorEmail, {
        gitlab_base_url: gitlabBaseUrl,
        token: gitlabToken
      });
      setTokenConfig(token);
      setGitlabToken("");
      setMessage(`已保存 GitLab token：${token.token_masked}`);
      await refreshGitConfig(selectedWorkspaceId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "GitLab token 保存失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleRepositoryBind(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedWorkspaceId || !projectId) return;
    setBusy(true);
    setMessage(null);
    try {
      const repository = await bindRepository(selectedWorkspaceId, actorEmail, {
        project_id: projectId,
        name: repositoryName,
        remote_url: remoteUrl,
        default_branch: defaultBranch,
        repo_size_limit_mb: Number(repoSizeLimitMb),
        diff_file_limit: Number(diffFileLimit),
        sync_timeout_seconds: Number(syncTimeoutSeconds)
      });
      setMessage(`已绑定仓库：${repository.name}`);
      await refreshGitConfig(selectedWorkspaceId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "仓库绑定失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleRepositorySync(repositoryId: string) {
    if (!selectedWorkspaceId) return;
    setBusy(true);
    setMessage(null);
    try {
      const job = await syncRepository(selectedWorkspaceId, repositoryId, actorEmail);
      setMessage(`已创建同步 Job：${job.status}`);
      await refreshGitConfig(selectedWorkspaceId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "仓库同步失败");
    } finally {
      setBusy(false);
    }
  }

  const selectedWorkspace = workspaces.find((workspace) => workspace.id === selectedWorkspaceId);

  return (
    <section className="section-block git-admin">
      <div className="section-heading">
        <div>
          <span className="eyebrow">GitLab</span>
          <h2>只读仓库和 Git Sandbox</h2>
        </div>
        <GitCommitHorizontal size={20} aria-hidden="true" />
      </div>
      <div className="admin-body">
        {message ? <div className="inline-notice">{message}</div> : null}

        <div className="admin-toolbar">
          <label className="select-label">
            当前 Workspace
            <select
              value={selectedWorkspaceId}
              onChange={(event) => void handleWorkspaceSwitch(event.target.value)}
              disabled={busy || workspaces.length === 0}
            >
              <option value="">未选择</option>
              {workspaces.map((workspace) => (
                <option value={workspace.id} key={workspace.id}>
                  {workspace.name}
                </option>
              ))}
            </select>
          </label>
          <div className="admin-context compact-context">
            <strong>{selectedWorkspace?.name ?? "尚未选择 Workspace"}</strong>
            <span>{tokenConfig ? `GitLab ${tokenConfig.gitlab_base_url} · token ${tokenConfig.token_masked}` : "保存 Workspace 级只读 GitLab token 后绑定项目仓库。"}</span>
          </div>
        </div>

        <div className="admin-grid">
          <section className="admin-pane" aria-label="GitLab token 配置">
            <div className="pane-heading">
              <div>
                <span className="eyebrow">Credential</span>
                <h3>Workspace GitLab Token</h3>
              </div>
              <KeyRound size={18} aria-hidden="true" />
            </div>
            <form className="stack-form" onSubmit={handleTokenSave}>
              <label>
                GitLab Base URL
                <input value={gitlabBaseUrl} onChange={(event) => setGitlabBaseUrl(event.target.value)} required />
              </label>
              <div className="form-row compact">
                <label>
                  Token
                  <input value={gitlabToken} onChange={(event) => setGitlabToken(event.target.value)} required />
                </label>
                <button className="ghost-button" type="submit" disabled={busy || !selectedWorkspaceId}>
                  保存 Token
                </button>
              </div>
            </form>
            <div className="data-list">
              {tokenConfig ? (
                <div className="data-row wide">
                  <div>
                    <strong>{tokenConfig.gitlab_base_url}</strong>
                    <span>token {tokenConfig.token_masked} · updated by {tokenConfig.updated_by}</span>
                  </div>
                </div>
              ) : (
                <p className="empty-state">暂无 GitLab token</p>
              )}
            </div>
          </section>

          <section className="admin-pane" aria-label="Repository 绑定">
            <div className="pane-heading">
              <div>
                <span className="eyebrow">Repositories</span>
                <h3>项目仓库绑定</h3>
              </div>
              <GitBranch size={18} aria-hidden="true" />
            </div>
            <form className="stack-form" onSubmit={handleRepositoryBind}>
              <label>
                Project
                <select value={projectId} onChange={(event) => setProjectId(event.target.value)} required>
                  <option value="">未选择</option>
                  {projects.map((project) => (
                    <option value={project.id} key={project.id}>
                      {project.key} · {project.name}
                    </option>
                  ))}
                </select>
              </label>
              <div className="form-row">
                <label>
                  仓库名称
                  <input value={repositoryName} onChange={(event) => setRepositoryName(event.target.value)} required />
                </label>
                <label>
                  默认分支
                  <input value={defaultBranch} onChange={(event) => setDefaultBranch(event.target.value)} required />
                </label>
              </div>
              <label>
                Remote URL
                <input value={remoteUrl} onChange={(event) => setRemoteUrl(event.target.value)} required />
              </label>
              <div className="form-row">
                <label>
                  大小限制 MB
                  <input value={repoSizeLimitMb} onChange={(event) => setRepoSizeLimitMb(event.target.value)} />
                </label>
                <label>
                  Diff 文件数限制
                  <input value={diffFileLimit} onChange={(event) => setDiffFileLimit(event.target.value)} />
                </label>
              </div>
              <div className="form-row compact">
                <label>
                  超时秒数
                  <input value={syncTimeoutSeconds} onChange={(event) => setSyncTimeoutSeconds(event.target.value)} />
                </label>
                <button className="ghost-button" type="submit" disabled={busy || !selectedWorkspaceId || projects.length === 0}>
                  绑定仓库
                </button>
              </div>
            </form>
          </section>
        </div>

        <section className="audit-pane" aria-label="Git Repository 列表">
          <div className="pane-heading">
            <div>
              <span className="eyebrow">Sandbox Checkouts</span>
              <h3>仓库工作副本</h3>
            </div>
            <GitCommitHorizontal size={18} aria-hidden="true" />
          </div>
          <div className="data-list">
            {repositories.map((repository) => (
              <div className="data-row git-row" key={repository.id}>
                <div>
                  <strong>{repository.name} · {statusLabel[repository.status]}</strong>
                  <span>{repository.remote_url}</span>
                  <small>{repository.mirror_path}</small>
                  <small>
                    {repository.repo_size_limit_mb} MB · diff {repository.diff_file_limit} files · timeout {repository.sync_timeout_seconds}s
                  </small>
                </div>
                <button className="ghost-button" type="button" disabled={busy} onClick={() => void handleRepositorySync(repository.id)}>
                  同步
                </button>
              </div>
            ))}
            {repositories.length === 0 ? <p className="empty-state">暂无仓库绑定</p> : null}
          </div>
        </section>

        <section className="audit-pane" aria-label="Git Sync Jobs">
          <div className="pane-heading">
            <div>
              <span className="eyebrow">Jobs</span>
              <h3>同步任务</h3>
            </div>
            <Database size={18} aria-hidden="true" />
          </div>
          <div className="audit-list">
            {jobsPagination.currentItems.map((job) => (
              <div className="audit-row" key={job.id}>
                <span>{statusLabel[job.status]}</span>
                <strong>{job.input_summary}</strong>
                <small>{job.error_summary || job.output_summary || job.key_logs[0]}</small>
              </div>
            ))}
            {jobs.length === 0 ? <p className="empty-state">暂无同步任务</p> : null}
          </div>
          <Pagination
            currentPage={jobsPagination.currentPage}
            totalPages={jobsPagination.totalPages}
            totalItems={jobsPagination.totalItems}
            onPageChange={jobsPagination.goToPage}
            itemsPerPage={8}
          />
        </section>
      </div>
    </section>
  );
}
