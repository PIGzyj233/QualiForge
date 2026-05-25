import { FormEvent, useEffect, useState } from "react";
import { FileText, FolderKanban, GitCommitHorizontal, History, Network, ShieldAlert } from "lucide-react";
import { useParams } from "react-router-dom";
import {
  createDiffAnalysis,
  DiffAnalysisRecord,
  GitRepositoryRecord,
  listDiffAnalyses,
  listProjects,
  listRepositories,
  listWorkspaces,
  ProjectRecord,
  Session,
  WorkspaceRecord
} from "../api";
import { statusLabel, riskLabel, changeTypeLabel } from "../lib/labels";
import { pickExistingId } from "../lib/selection";

export function DiffAnalysisAdmin({ session }: { session: Session }) {
  const actorEmail = session.user.email;
  const { wid: routeWorkspaceId = "", pid: routeProjectId = "" } = useParams<{ wid: string; pid: string }>();
  const [workspaces, setWorkspaces] = useState<WorkspaceRecord[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState("");
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [repositories, setRepositories] = useState<GitRepositoryRecord[]>([]);
  const [selectedRepositoryId, setSelectedRepositoryId] = useState("");
  const [analyses, setAnalyses] = useState<DiffAnalysisRecord[]>([]);
  const [selectedAnalysisId, setSelectedAnalysisId] = useState("");
  const [baseRef, setBaseRef] = useState("v1");
  const [targetRef, setTargetRef] = useState("v2");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function refreshDiffProject(workspaceId: string, projectId: string, preferredRepositoryId?: string, preferredAnalysisId?: string) {
    const [nextRepositories, nextAnalyses] = await Promise.all([
      listRepositories(workspaceId, projectId),
      listDiffAnalyses(workspaceId, projectId)
    ]);
    setRepositories(nextRepositories);
    setAnalyses(nextAnalyses);
    const syncedRepository = nextRepositories.find((repository) => repository.status === "synced");
    const nextRepositoryId = pickExistingId(nextRepositories, preferredRepositoryId || syncedRepository?.id, selectedRepositoryId);
    const nextAnalysisId = pickExistingId(nextAnalyses, preferredAnalysisId, selectedAnalysisId);
    setSelectedRepositoryId(nextRepositoryId);
    setSelectedAnalysisId(nextAnalysisId);
  }

  async function refreshDiffWorkspaces(preferredWorkspaceId?: string, preferredProjectId?: string, preferredAnalysisId?: string) {
    setBusy(true);
    setMessage(null);
    try {
      const nextWorkspaces = await listWorkspaces(actorEmail);
      setWorkspaces(nextWorkspaces);
      const nextWorkspaceId = pickExistingId(nextWorkspaces, preferredWorkspaceId, selectedWorkspaceId);
      setSelectedWorkspaceId(nextWorkspaceId);
      if (!nextWorkspaceId) return;
      const nextProjects = await listProjects(nextWorkspaceId);
      setProjects(nextProjects);
      const nextProjectId = pickExistingId(nextProjects, preferredProjectId, selectedProjectId);
      setSelectedProjectId(nextProjectId);
      if (nextProjectId) {
        await refreshDiffProject(nextWorkspaceId, nextProjectId, undefined, preferredAnalysisId);
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Diff 分析数据加载失败");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void refreshDiffWorkspaces(routeWorkspaceId || undefined, routeProjectId || undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routeWorkspaceId, routeProjectId]);

  async function handleWorkspaceSwitch(workspaceId: string) {
    setSelectedWorkspaceId(workspaceId);
    setBusy(true);
    setMessage(null);
    try {
      const nextProjects = await listProjects(workspaceId);
      setProjects(nextProjects);
      const nextProjectId = nextProjects[0]?.id ?? "";
      setSelectedProjectId(nextProjectId);
      if (nextProjectId) {
        await refreshDiffProject(workspaceId, nextProjectId);
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Diff Workspace 切换失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleProjectSwitch(projectId: string) {
    setSelectedProjectId(projectId);
    if (!selectedWorkspaceId || !projectId) return;
    setBusy(true);
    setMessage(null);
    try {
      await refreshDiffProject(selectedWorkspaceId, projectId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Diff Project 切换失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleRunDiff(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedWorkspaceId || !selectedProjectId || !selectedRepositoryId) return;
    setBusy(true);
    setMessage(null);
    try {
      const analysis = await createDiffAnalysis(selectedWorkspaceId, selectedProjectId, actorEmail, {
        repository_id: selectedRepositoryId,
        base_ref: baseRef,
        target_ref: targetRef
      });
      setMessage(`已完成 Diff 分析：${riskLabel[analysis.risk_level]} · ${analysis.file_changes.length} files`);
      await refreshDiffProject(selectedWorkspaceId, selectedProjectId, selectedRepositoryId, analysis.id);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Diff 分析失败");
    } finally {
      setBusy(false);
    }
  }

  const selectedProject = projects.find((project) => project.id === selectedProjectId);
  const selectedRepository = repositories.find((repository) => repository.id === selectedRepositoryId);
  const selectedAnalysis = analyses.find((analysis) => analysis.id === selectedAnalysisId);

  return (
    <section className="section-block diff-admin">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Diff Decision</span>
          <h2>Tag Diff 模块影响分析</h2>
        </div>
        <Network size={20} aria-hidden="true" />
      </div>
      <div className="admin-body">
        {message ? <div className="inline-notice">{message}</div> : null}

        <div className="admin-toolbar">
          <label className="select-label">
            当前 Workspace
            <select value={selectedWorkspaceId} onChange={(event) => void handleWorkspaceSwitch(event.target.value)} disabled={busy || workspaces.length === 0}>
              <option value="">未选择</option>
              {workspaces.map((workspace) => (
                <option value={workspace.id} key={workspace.id}>
                  {workspace.name}
                </option>
              ))}
            </select>
          </label>
          <label className="select-label">
            当前 Project
            <select value={selectedProjectId} onChange={(event) => void handleProjectSwitch(event.target.value)} disabled={busy || projects.length === 0}>
              <option value="">未选择</option>
              {projects.map((project) => (
                <option value={project.id} key={project.id}>
                  {project.key} · {project.name}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="admin-context">
          <strong>{selectedProject ? `${selectedProject.key} · ${selectedProject.name}` : "尚未选择 Project"}</strong>
          <span>{selectedRepository ? `${selectedRepository.name} · ${statusLabel[selectedRepository.status]}` : "先绑定并同步 Repository"}</span>
        </div>

        <div className="admin-grid">
          <section className="admin-pane" aria-label="创建 Diff 分析">
            <div className="pane-heading">
              <div>
                <span className="eyebrow">Job Input</span>
                <h3>运行 DiffAnalysis</h3>
              </div>
              <GitCommitHorizontal size={18} aria-hidden="true" />
            </div>
            <form className="stack-form" onSubmit={handleRunDiff}>
              <label>
                Repository
                <select value={selectedRepositoryId} onChange={(event) => setSelectedRepositoryId(event.target.value)} disabled={busy || repositories.length === 0}>
                  <option value="">未选择</option>
                  {repositories.map((repository) => (
                    <option value={repository.id} key={repository.id}>
                      {repository.name} · {statusLabel[repository.status]}
                    </option>
                  ))}
                </select>
              </label>
              <div className="form-row">
                <label>
                  Base ref/tag
                  <input value={baseRef} onChange={(event) => setBaseRef(event.target.value)} required />
                </label>
                <label>
                  Target ref/tag
                  <input value={targetRef} onChange={(event) => setTargetRef(event.target.value)} required />
                </label>
              </div>
              <button className="primary-button small" type="submit" disabled={busy || !selectedRepositoryId}>
                运行 Diff
              </button>
            </form>
          </section>

          <section className="admin-pane" aria-label="Diff 测试决策">
            <div className="pane-heading">
              <div>
                <span className="eyebrow">Testing Scope</span>
                <h3>推荐测试范围</h3>
              </div>
              <ShieldAlert size={18} aria-hidden="true" />
            </div>
            {selectedAnalysis ? (
              <div className="decision-panel">
                <div className={`risk-pill ${selectedAnalysis.risk_level}`}>{riskLabel[selectedAnalysis.risk_level]}</div>
                <strong>{selectedAnalysis.summary}</strong>
                <span>{selectedAnalysis.base_ref} → {selectedAnalysis.target_ref} · {statusLabel[selectedAnalysis.status]}</span>
                <ul>
                  {selectedAnalysis.recommended_scope.slice(0, 5).map((scope) => (
                    <li key={scope}>{scope}</li>
                  ))}
                </ul>
              </div>
            ) : (
              <p className="empty-state">暂无 Diff 分析结果</p>
            )}
          </section>
        </div>

        <section className="audit-pane" aria-label="Diff 模块影响">
          <div className="pane-heading">
            <div>
              <span className="eyebrow">Impacted Modules</span>
              <h3>模块影响和风险</h3>
            </div>
            <FolderKanban size={18} aria-hidden="true" />
          </div>
          <div className="data-list">
            {selectedAnalysis?.module_impacts.map((impact) => (
              <div className="impact-row" key={`${impact.module_key}-${impact.risk_level}`}>
                <div>
                  <strong>{impact.module_key} · {impact.module_name}</strong>
                  <span>{impact.changed_file_count} files · confidence {impact.confidence}%</span>
                  <small>{impact.recommended_tests.join(" · ")}</small>
                </div>
                <div className={`risk-pill ${impact.risk_level}`}>{riskLabel[impact.risk_level]}</div>
              </div>
            ))}
            {!selectedAnalysis || selectedAnalysis.module_impacts.length === 0 ? <p className="empty-state">暂无模块影响</p> : null}
          </div>
        </section>

        <section className="audit-pane" aria-label="Diff 文件证据">
          <div className="pane-heading">
            <div>
              <span className="eyebrow">Evidence</span>
              <h3>文件和结构证据</h3>
            </div>
            <FileText size={18} aria-hidden="true" />
          </div>
          <div className="data-list">
            {selectedAnalysis?.file_changes.map((file) => (
              <div className="data-row wide" key={`${file.change_type}-${file.path}`}>
                <div>
                  <strong>{changeTypeLabel[file.change_type]} · {file.path}</strong>
                  <span>{file.module_key ?? "UNMAPPED"} · {file.language} · {file.directory} · +{file.additions} -{file.deletions}</span>
                  <small>
                    {file.structure_changes.slice(0, 5).map((item) => `${item.type}:${item.name}`).join(" · ") || file.evidence.join(" · ")}
                  </small>
                </div>
              </div>
            ))}
            {!selectedAnalysis || selectedAnalysis.file_changes.length === 0 ? <p className="empty-state">暂无文件证据</p> : null}
          </div>
        </section>

        <section className="audit-pane" aria-label="Diff 分析历史">
          <div className="pane-heading">
            <div>
              <span className="eyebrow">History</span>
              <h3>DiffAnalysis Jobs</h3>
            </div>
            <History size={18} aria-hidden="true" />
          </div>
          <div className="data-list">
            {analyses.map((analysis) => (
              <div className="data-row module-row" key={analysis.id}>
                <div>
                  <strong>{analysis.base_ref} → {analysis.target_ref} · {riskLabel[analysis.risk_level]}</strong>
                  <span>{statusLabel[analysis.status]} · {analysis.file_changes.length} files · job {analysis.job_id.slice(0, 8)}</span>
                  <small>{analysis.summary || analysis.error_summary}</small>
                </div>
                <button className="ghost-button" type="button" onClick={() => setSelectedAnalysisId(analysis.id)}>
                  查看
                </button>
              </div>
            ))}
            {analyses.length === 0 ? <p className="empty-state">暂无 DiffAnalysis Job</p> : null}
          </div>
        </section>
      </div>
    </section>
  );
}
