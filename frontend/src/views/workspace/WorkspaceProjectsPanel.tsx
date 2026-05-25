import { FormEvent, useState } from "react";
import { Archive, FolderKanban, PencilLine } from "lucide-react";
import { createProject, ProjectRecord, updateProject } from "../../api";
import { useWorkspaceContext } from "../../hooks/useWorkspaceContext";
import { statusLabel } from "../../lib/labels";

export function WorkspaceProjectsPanel() {
  const { actorEmail, currentWorkspace, projects, refreshProjects } = useWorkspaceContext();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [name, setName] = useState("Checkout");
  const [key, setKey] = useState("CHECKOUT");
  const [description, setDescription] = useState("Checkout regression surface");
  const [projStatus, setProjStatus] = useState<"active" | "archived">("active");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  function reset() {
    setEditingId(null);
    setName("");
    setKey("");
    setDescription("");
    setProjStatus("active");
  }

  function edit(project: ProjectRecord) {
    setEditingId(project.id);
    setName(project.name);
    setKey(project.key);
    setDescription(project.description);
    setProjStatus(project.status);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!currentWorkspace) return;
    setBusy(true);
    setMessage(null);
    try {
      if (editingId) {
        await updateProject(currentWorkspace.id, editingId, actorEmail, {
          name,
          description,
          status: projStatus
        });
        setMessage(`已更新项目 ${key}`);
      } else {
        await createProject(currentWorkspace.id, actorEmail, { name, key, description });
        setMessage(`已创建项目 ${key}`);
      }
      reset();
      await refreshProjects();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "项目保存失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel">
      <header className="panel-head">
        <div>
          <span className="eyebrow">Projects</span>
          <h2>项目</h2>
          <p className="panel-sub">在 {currentWorkspace?.name ?? "当前 Workspace"} 下管理项目生命周期。</p>
        </div>
        <FolderKanban size={20} aria-hidden="true" />
      </header>
      {message ? <div className="inline-notice">{message}</div> : null}

      <form className="card-form" onSubmit={handleSubmit}>
        <h3>{editingId ? "编辑项目" : "新建项目"}</h3>
        <div className="form-row">
          <label>
            名称
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </label>
          <label>
            Key
            <input
              value={key}
              onChange={(e) => setKey(e.target.value.toUpperCase())}
              disabled={Boolean(editingId)}
              required
            />
          </label>
        </div>
        <label>
          描述
          <input value={description} onChange={(e) => setDescription(e.target.value)} />
        </label>
        {editingId ? (
          <label>
            状态
            <select value={projStatus} onChange={(e) => setProjStatus(e.target.value as "active" | "archived")}>
              <option value="active">Active</option>
              <option value="archived">Archived</option>
            </select>
          </label>
        ) : null}
        <div className="form-row compact">
          <button className="primary-button" type="submit" disabled={busy || !currentWorkspace}>
            {editingId ? "保存" : "创建项目"}
          </button>
          {editingId ? (
            <button className="ghost-button" type="button" onClick={reset}>
              取消
            </button>
          ) : null}
        </div>
      </form>

      <div className="card-list">
        {projects.map((project) => (
          <article className="member-card" key={project.id}>
            <div>
              <strong>
                {project.key} · {project.name}
              </strong>
              <span>{project.description || "无描述"}</span>
              <small>
                {statusLabel[project.status]} · 创建于 {new Date(project.created_at).toLocaleDateString()}
              </small>
            </div>
            <button className="icon-button subtle" type="button" onClick={() => edit(project)} title="编辑项目">
              <PencilLine size={16} aria-hidden="true" />
            </button>
            {project.status === "archived" ? <Archive size={16} aria-hidden="true" /> : null}
          </article>
        ))}
        {projects.length === 0 ? <p className="empty-state">尚无项目</p> : null}
      </div>
    </section>
  );
}
