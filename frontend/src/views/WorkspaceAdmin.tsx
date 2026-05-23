import { FormEvent, useEffect, useState } from "react";
import { FolderKanban, History, PencilLine, Plus, Trash2, UserPlus } from "lucide-react";
import {
  addMember,
  AuditLogRecord,
  createProject,
  createWorkspace,
  listAuditLogs,
  listMembers,
  listProjects,
  listWorkspaces,
  MemberRecord,
  ProjectRecord,
  removeMember,
  Session,
  updateProject,
  WorkspaceRecord
} from "../api";
import { Pagination } from "../components/Pagination";
import { usePagination } from "../hooks/usePagination";
import { statusLabel } from "../lib/labels";

export type WorkspaceSection = "projects" | "members" | "audit" | "all";

const sectionTitles: Record<WorkspaceSection, string> = {
  all: "成员、项目和审计",
  projects: "项目",
  members: "团队成员",
  audit: "审计日志"
};

export function WorkspaceAdmin({
  session,
  section = "all"
}: {
  session: Session;
  section?: WorkspaceSection;
}) {
  const actorEmail = session.user.email;
  const [workspaces, setWorkspaces] = useState<WorkspaceRecord[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState("");
  const [members, setMembers] = useState<MemberRecord[]>([]);
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLogRecord[]>([]);
  const [workspaceName, setWorkspaceName] = useState(session.workspace.name);
  const [memberEmail, setMemberEmail] = useState("tester@qualiforge.local");
  const [memberName, setMemberName] = useState("Tester");
  const [memberRole, setMemberRole] = useState<"WorkspaceOwner" | "WorkspaceMember">("WorkspaceMember");
  const [projectName, setProjectName] = useState("Checkout");
  const [projectKey, setProjectKey] = useState("CHECKOUT");
  const [projectDescription, setProjectDescription] = useState("Checkout regression surface");
  const [projectStatus, setProjectStatus] = useState<"active" | "archived">("active");
  const [editingProjectId, setEditingProjectId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const auditPagination = usePagination(auditLogs, 8);

  async function refreshWorkspaces(preferredWorkspaceId?: string) {
    setBusy(true);
    setMessage(null);
    try {
      const nextWorkspaces = await listWorkspaces(actorEmail);
      setWorkspaces(nextWorkspaces);
      const nextSelectedId = preferredWorkspaceId || selectedWorkspaceId || nextWorkspaces[0]?.id || "";
      setSelectedWorkspaceId(nextSelectedId);
      if (nextSelectedId) {
        await refreshWorkspaceDetails(nextSelectedId);
      } else {
        setMembers([]);
        setProjects([]);
        setAuditLogs([]);
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Workspace 数据加载失败");
    } finally {
      setBusy(false);
    }
  }

  async function refreshWorkspaceDetails(workspaceId: string) {
    const [nextMembers, nextProjects, nextAuditLogs] = await Promise.all([
      listMembers(workspaceId),
      listProjects(workspaceId),
      listAuditLogs(workspaceId)
    ]);
    setMembers(nextMembers);
    setProjects(nextProjects);
    setAuditLogs(nextAuditLogs);
  }

  useEffect(() => {
    void refreshWorkspaces();
  }, []);

  async function handleCreateWorkspace(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const workspace = await createWorkspace({
        name: workspaceName,
        owner_email: actorEmail,
        owner_display_name: session.user.display_name
      });
      setMessage(`已创建 Workspace：${workspace.name}`);
      await refreshWorkspaces(workspace.id);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Workspace 创建失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleWorkspaceSwitch(workspaceId: string) {
    setSelectedWorkspaceId(workspaceId);
    setBusy(true);
    setMessage(null);
    try {
      await refreshWorkspaceDetails(workspaceId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Workspace 切换失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleAddMember(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedWorkspaceId) return;
    setBusy(true);
    setMessage(null);
    try {
      const member = await addMember(selectedWorkspaceId, actorEmail, {
        email: memberEmail,
        display_name: memberName,
        role: memberRole
      });
      setMessage(`已添加成员：${member.email}`);
      await refreshWorkspaceDetails(selectedWorkspaceId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "成员添加失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleRemoveMember(memberId: string) {
    if (!selectedWorkspaceId) return;
    setBusy(true);
    setMessage(null);
    try {
      await removeMember(selectedWorkspaceId, memberId, actorEmail);
      setMessage("已移除成员");
      await refreshWorkspaceDetails(selectedWorkspaceId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "成员移除失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedWorkspaceId) return;
    setBusy(true);
    setMessage(null);
    try {
      if (editingProjectId) {
        const project = await updateProject(selectedWorkspaceId, editingProjectId, actorEmail, {
          name: projectName,
          description: projectDescription,
          status: projectStatus
        });
        setMessage(`已更新项目：${project.key}`);
      } else {
        const project = await createProject(selectedWorkspaceId, actorEmail, {
          name: projectName,
          key: projectKey,
          description: projectDescription
        });
        setMessage(`已创建项目：${project.key}`);
      }
      clearProjectForm();
      await refreshWorkspaceDetails(selectedWorkspaceId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "项目保存失败");
    } finally {
      setBusy(false);
    }
  }

  function editProject(project: ProjectRecord) {
    setEditingProjectId(project.id);
    setProjectName(project.name);
    setProjectKey(project.key);
    setProjectDescription(project.description);
    setProjectStatus(project.status);
  }

  function clearProjectForm() {
    setEditingProjectId(null);
    setProjectName("");
    setProjectKey("");
    setProjectDescription("");
    setProjectStatus("active");
  }

  const selectedWorkspace = workspaces.find((workspace) => workspace.id === selectedWorkspaceId);

  return (
    <section className="section-block workspace-admin">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Workspace</span>
          <h2>{sectionTitles[section]}</h2>
        </div>
        <FolderKanban size={20} aria-hidden="true" />
      </div>

      <div className="admin-body">
        {message ? <div className="inline-notice">{message}</div> : null}

        <div className="admin-toolbar">
          <form className="compact-form" onSubmit={handleCreateWorkspace}>
            <label>
              Workspace 名称
              <input value={workspaceName} onChange={(event) => setWorkspaceName(event.target.value)} required />
            </label>
            <button className="primary-button small" type="submit" disabled={busy}>
              <Plus size={16} aria-hidden="true" />
              <span>创建</span>
            </button>
          </form>

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
        </div>

        <div className="admin-context">
          <strong>{selectedWorkspace?.name ?? "尚未创建 Workspace"}</strong>
          <span>{selectedWorkspace ? `Owner ${selectedWorkspace.owner_email}` : "先创建 Workspace，然后添加成员和项目。"}</span>
        </div>

        <div className="admin-grid">
          {section === "all" || section === "members" ? (
          <section className="admin-pane" aria-label="成员管理">
            <div className="pane-heading">
              <div>
                <span className="eyebrow">Members</span>
                <h3>成员</h3>
              </div>
              <UserPlus size={18} aria-hidden="true" />
            </div>
            <form className="stack-form" onSubmit={handleAddMember}>
              <div className="form-row">
                <label>
                  邮箱
                  <input value={memberEmail} onChange={(event) => setMemberEmail(event.target.value)} required />
                </label>
                <label>
                  显示名称
                  <input value={memberName} onChange={(event) => setMemberName(event.target.value)} required />
                </label>
              </div>
              <div className="form-row compact">
                <label>
                  角色
                  <select value={memberRole} onChange={(event) => setMemberRole(event.target.value as "WorkspaceOwner" | "WorkspaceMember")}>
                    <option value="WorkspaceMember">WorkspaceMember</option>
                    <option value="WorkspaceOwner">WorkspaceOwner</option>
                  </select>
                </label>
                <button className="ghost-button" type="submit" disabled={busy || !selectedWorkspaceId}>
                  添加成员
                </button>
              </div>
            </form>
            <div className="data-list">
              {members.map((member) => (
                <div className="data-row" key={member.id}>
                  <div>
                    <strong>{member.display_name}</strong>
                    <span>{member.email} · {member.role}</span>
                  </div>
                  <button
                    className="icon-button subtle"
                    type="button"
                    disabled={busy || member.role === "WorkspaceOwner"}
                    onClick={() => void handleRemoveMember(member.id)}
                    title="移除成员"
                  >
                    <Trash2 size={16} aria-hidden="true" />
                  </button>
                </div>
              ))}
            </div>
          </section>
          ) : null}

          {section === "all" || section === "projects" ? (
          <section className="admin-pane" aria-label="项目管理">
            <div className="pane-heading">
              <div>
                <span className="eyebrow">Projects</span>
                <h3>项目</h3>
              </div>
              <PencilLine size={18} aria-hidden="true" />
            </div>
            <form className="stack-form" onSubmit={handleSaveProject}>
              <div className="form-row">
                <label>
                  名称
                  <input value={projectName} onChange={(event) => setProjectName(event.target.value)} required />
                </label>
                <label>
                  Key
                  <input
                    value={projectKey}
                    onChange={(event) => setProjectKey(event.target.value.toUpperCase())}
                    disabled={Boolean(editingProjectId)}
                    required
                  />
                </label>
              </div>
              <label>
                描述
                <input value={projectDescription} onChange={(event) => setProjectDescription(event.target.value)} />
              </label>
              <div className="form-row compact">
                <label>
                  状态
                  <select value={projectStatus} onChange={(event) => setProjectStatus(event.target.value as "active" | "archived")}>
                    <option value="active">active</option>
                    <option value="archived">archived</option>
                  </select>
                </label>
                <button className="ghost-button" type="submit" disabled={busy || !selectedWorkspaceId}>
                  {editingProjectId ? "保存项目" : "创建项目"}
                </button>
                {editingProjectId ? (
                  <button className="ghost-button" type="button" onClick={clearProjectForm}>
                    取消
                  </button>
                ) : null}
              </div>
            </form>
            <div className="data-list">
              {projects.map((project) => (
                <div className="data-row" key={project.id}>
                  <div>
                    <strong>{project.key} · {project.name}</strong>
                    <span>{project.description || "无描述"} · {statusLabel[project.status]}</span>
                  </div>
                  <button className="icon-button subtle" type="button" onClick={() => editProject(project)} title="编辑项目">
                    <PencilLine size={16} aria-hidden="true" />
                  </button>
                </div>
              ))}
            </div>
          </section>
          ) : null}
        </div>

        {section === "all" || section === "audit" ? (
        <section className="audit-pane" aria-label="审计日志">
          <div className="pane-heading">
            <div>
              <span className="eyebrow">Audit</span>
              <h3>最近审计</h3>
            </div>
            <History size={18} aria-hidden="true" />
          </div>
          <div className="audit-list">
            {auditPagination.currentItems.map((entry) => (
              <div className="audit-row" key={entry.id}>
                <span>{entry.action}</span>
                <strong>{entry.summary}</strong>
                <small>{entry.actor_email}</small>
              </div>
            ))}
            {auditLogs.length === 0 ? <p className="empty-state">暂无审计记录</p> : null}
          </div>
          <Pagination
            currentPage={auditPagination.currentPage}
            totalPages={auditPagination.totalPages}
            totalItems={auditPagination.totalItems}
            onPageChange={auditPagination.goToPage}
            itemsPerPage={8}
          />
        </section>
        ) : null}
      </div>
    </section>
  );
}
