import { FormEvent, useEffect, useState } from "react";
import { Trash2, UserPlus } from "lucide-react";
import { addMember, listMembers, MemberRecord, removeMember } from "../../api/workspace";
import { useWorkspaceContext } from "../../hooks/useWorkspaceContext";

export function WorkspaceMembersPanel() {
  const { actorEmail, currentWorkspace } = useWorkspaceContext();
  const [members, setMembers] = useState<MemberRecord[]>([]);
  const [email, setEmail] = useState("tester@qualiforge.local");
  const [displayName, setDisplayName] = useState("Tester");
  const [role, setRole] = useState<"WorkspaceOwner" | "WorkspaceMember">("WorkspaceMember");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function refresh() {
    if (!currentWorkspace) return;
    setBusy(true);
    try {
      setMembers(await listMembers(currentWorkspace.id));
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "成员加载失败");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentWorkspace?.id]);

  async function handleAdd(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!currentWorkspace) return;
    setBusy(true);
    setMessage(null);
    try {
      const member = await addMember(currentWorkspace.id, actorEmail, { email, display_name: displayName, role });
      setMessage(`已添加成员 ${member.email}`);
      await refresh();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "添加成员失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleRemove(memberId: string) {
    if (!currentWorkspace) return;
    setBusy(true);
    setMessage(null);
    try {
      await removeMember(currentWorkspace.id, memberId, actorEmail);
      setMessage("已移除成员");
      await refresh();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "移除成员失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel">
      <header className="panel-head">
        <div>
          <span className="eyebrow">Members</span>
          <h2>团队成员</h2>
          <p className="panel-sub">为 {currentWorkspace?.name ?? "当前 Workspace"} 添加或移除成员，调整角色。</p>
        </div>
        <UserPlus size={20} aria-hidden="true" />
      </header>
      {message ? <div className="inline-notice">{message}</div> : null}

      <form className="card-form" onSubmit={handleAdd}>
        <h3>添加成员</h3>
        <div className="form-row">
          <label>
            邮箱
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </label>
          <label>
            显示名称
            <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} required />
          </label>
          <label>
            角色
            <select value={role} onChange={(e) => setRole(e.target.value as typeof role)}>
              <option value="WorkspaceMember">成员</option>
              <option value="WorkspaceOwner">Owner</option>
            </select>
          </label>
        </div>
        <button className="primary-button" type="submit" disabled={busy || !currentWorkspace}>
          添加成员
        </button>
      </form>

      <div className="card-list">
        {members.map((member) => (
          <article className="member-card" key={member.id}>
            <div>
              <strong>{member.display_name}</strong>
              <span>{member.email}</span>
              <small>{member.role === "WorkspaceOwner" ? "Owner" : "成员"} · 加入于 {new Date(member.created_at).toLocaleDateString()}</small>
            </div>
            <button
              className="icon-button subtle"
              type="button"
              onClick={() => void handleRemove(member.id)}
              disabled={busy || member.role === "WorkspaceOwner"}
              title={member.role === "WorkspaceOwner" ? "Owner 不可移除" : "移除成员"}
            >
              <Trash2 size={16} aria-hidden="true" />
            </button>
          </article>
        ))}
        {members.length === 0 ? <p className="empty-state">尚无成员</p> : null}
      </div>
    </section>
  );
}
