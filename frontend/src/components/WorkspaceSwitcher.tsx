import { ChevronDown, Plus } from "lucide-react";
import { FormEvent, useState } from "react";
import { createWorkspace, Session, WorkspaceRecord } from "../api";

export function WorkspaceSwitcher({
  workspaces,
  currentWorkspaceId,
  session,
  busy,
  onSwitch,
  onCreated
}: {
  workspaces: WorkspaceRecord[];
  currentWorkspaceId: string;
  session: Session;
  busy: boolean;
  onSwitch: (workspaceId: string) => void;
  onCreated: (workspace: WorkspaceRecord) => void;
}) {
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("New Workspace");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const current = workspaces.find((w) => w.id === currentWorkspaceId);

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      const created = await createWorkspace({
        name: name.trim(),
        owner_email: session.user.email,
        owner_display_name: session.user.display_name
      });
      onCreated(created);
      setCreating(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Workspace 创建失败");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="workspace-switcher">
      <label className="switcher-select">
        <span className="eyebrow">Workspace</span>
        <div className="switcher-row">
          <select
            value={currentWorkspaceId}
            onChange={(event) => onSwitch(event.target.value)}
            disabled={busy || workspaces.length === 0}
          >
            {workspaces.map((workspace) => (
              <option value={workspace.id} key={workspace.id}>
                {workspace.name}
              </option>
            ))}
          </select>
          <ChevronDown size={14} aria-hidden="true" />
        </div>
      </label>
      <button
        className="ghost-button small"
        type="button"
        onClick={() => setCreating((v) => !v)}
        title={creating ? "取消" : "新建 Workspace"}
      >
        <Plus size={14} aria-hidden="true" />
        新建
      </button>
      {creating ? (
        <form className="switcher-dialog" onSubmit={handleCreate}>
          <label>
            名称
            <input value={name} onChange={(event) => setName(event.target.value)} required autoFocus />
          </label>
          {error ? <p className="form-error">{error}</p> : null}
          <div className="form-row compact">
            <button className="ghost-button small" type="button" onClick={() => setCreating(false)} disabled={pending}>
              取消
            </button>
            <button className="primary-button small" type="submit" disabled={pending || !name.trim()}>
              {pending ? "创建中" : "创建"}
            </button>
          </div>
          <small className="helper-copy">当前用户 {session.user.email} 将成为 Owner</small>
        </form>
      ) : null}
      {current ? (
        <small className="helper-copy">Owner {current.owner_email}</small>
      ) : null}
    </div>
  );
}
