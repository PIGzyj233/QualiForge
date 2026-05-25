import { useEffect, useState } from "react";
import { Mail, Shield } from "lucide-react";
import { listMembers, MemberRecord } from "../../api";
import { useWorkspaceContext } from "../../hooks/useWorkspaceContext";

export function ProjectTeamPanel() {
  const { currentWorkspace } = useWorkspaceContext();
  const [members, setMembers] = useState<MemberRecord[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!currentWorkspace) return;
    listMembers(currentWorkspace.id)
      .then(setMembers)
      .catch((err) => setError(err instanceof Error ? err.message : "成员加载失败"));
  }, [currentWorkspace?.id]);

  return (
    <section className="panel">
      <header className="panel-head">
        <div>
          <span className="eyebrow">Team</span>
          <h2>项目团队</h2>
          <p className="panel-sub">该项目所在 Workspace 的成员（添加成员请前往 Workspace 管理 → 成员）。</p>
        </div>
      </header>
      {error ? <div className="inline-notice">{error}</div> : null}
      <div className="card-list">
        {members.map((member) => (
          <article className="member-card" key={member.id}>
            <div>
              <strong>{member.display_name}</strong>
              <span>
                <Mail size={12} aria-hidden="true" /> {member.email}
              </span>
              <small>
                <Shield size={12} aria-hidden="true" /> {member.role === "WorkspaceOwner" ? "Workspace Owner" : "Workspace 成员"}
              </small>
            </div>
          </article>
        ))}
        {members.length === 0 ? <p className="empty-state">尚无成员</p> : null}
      </div>
    </section>
  );
}
