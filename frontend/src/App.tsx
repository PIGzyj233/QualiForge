import {
  Activity,
  AlertCircle,
  BrainCircuit,
  CheckCircle2,
  ClipboardCheck,
  Database,
  FileText,
  FolderKanban,
  GitBranch,
  GitCommitHorizontal,
  History,
  KeyRound,
  LayoutDashboard,
  LogIn,
  Network,
  PencilLine,
  Plus,
  RefreshCcw,
  Settings2,
  ShieldCheck,
  ShieldAlert,
  Sparkles,
  Trash2,
  UserPlus,
  Users
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  addMember,
  AIDataPolicy,
  AIInvocationRecord,
  AIPurpose,
  AISettingsRecord,
  AuditLogRecord,
  bindRepository,
  bulkImportTestCases,
  bulkUpdateImportDrafts,
  CaseReviewAction,
  CaseReviewRecord,
  CaseRevisionRecord,
  completeAIInvocation,
  createMappingRule,
  createLLMProvider,
  createModule,
  createProject,
  createDiffAnalysis,
  createTestCase,
  createWorkspace,
  DashboardSummary,
  deleteMappingRule,
  deleteModule,
  getGitLabToken,
  getDashboardSummary,
  getHealth,
  getAISettings,
  DiffAnalysisRecord,
  GitLabTokenRecord,
  GitRepositoryRecord,
  getReviewSettings,
  HealthPayload,
  ImportBatchRecord,
  ImportDraftRecord,
  JobRecord,
  listImportBatches,
  listImportDrafts,
  listDiffAnalyses,
  listCaseReviews,
  listCaseRevisions,
  listMappingRules,
  listAuditLogs,
  listAIInvocations,
  listJobs,
  listLLMProviders,
  listMembers,
  listModelProfiles,
  listModules,
  listProjects,
  listRepositories,
  listTestCases,
  listWorkspaces,
  LLMProviderRecord,
  login,
  MappingRuleType,
  MappingSource,
  MemberRecord,
  ModelProfileRecord,
  ModuleMappingRuleRecord,
  ProjectRecord,
  ProjectModuleRecord,
  removeMember,
  ReviewSettingsRecord,
  reviewTestCase,
  Session,
  startAIInvocation,
  submitImportReview,
  submitTestCaseReview,
  syncRepository,
  TestCaseRecord,
  TestCasePayload,
  updateMappingRule,
  updateModule,
  updateReviewSettings,
  updateTestCase,
  updateProject,
  updateAISettings,
  uploadImportBatch,
  upsertGitLabToken,
  upsertModelProfile,
  WorkspaceRecord
} from "./api";

const SESSION_KEY = "qualiforge.session";

const navItems = [
  { label: "工作台", icon: LayoutDashboard, active: true },
  { label: "项目", icon: GitBranch, active: false },
  { label: "用例库", icon: ClipboardCheck, active: false },
  { label: "评审", icon: Users, active: false },
  { label: "报告", icon: FileText, active: false },
  { label: "设置", icon: ShieldCheck, active: false }
];

const statusLabel: Record<string, string> = {
  done: "已完成",
  in_progress: "进行中",
  next: "下一步",
  blocked: "等待依赖",
  ok: "正常",
  degraded: "降级",
  unavailable: "不可用",
  configured: "已配置",
  queued: "排队中",
  rejected: "已拒绝",
  succeeded: "成功",
  failed: "失败",
  active: "活跃",
  archived: "归档",
  pending: "待同步",
  synced: "已同步",
  sync_failed: "同步失败",
  running: "运行中",
  cancelled: "已取消",
  uploaded: "已上传",
  preview_ready: "可预览",
  review_submitted: "已提交评审",
  imported: "已入库",
  draft: "草稿",
  pending_review: "待评审",
  approved: "已通过",
  submitted: "已提交",
  changes_requested: "要求修改",
  commented: "已评论",
  edited: "已编辑"
};

const riskLabel: Record<string, string> = {
  low: "低风险",
  medium: "中风险",
  high: "高风险"
};

const changeTypeLabel: Record<string, string> = {
  added: "新增",
  modified: "修改",
  deleted: "删除",
  renamed: "重命名"
};

const purposeLabel: Record<AIPurpose, string> = {
  import_cleanup: "导入清洗",
  diff_analysis: "Diff 分析",
  case_generation: "用例生成",
  report_summary: "报告总结"
};

const policyLabel: Record<AIDataPolicy, string> = {
  ExternalAllowed: "ExternalAllowed",
  NoSourceCode: "NoSourceCode",
  InternalOnly: "InternalOnly",
  AIDisabled: "AIDisabled"
};

const mappingRuleTypeLabel: Record<MappingRuleType, string> = {
  directory: "目录",
  file: "文件",
  api: "接口",
  service: "服务",
  config_key: "配置 Key",
  database_migration: "数据库迁移",
  keyword: "关键词"
};

const mappingSourceLabel: Record<MappingSource, string> = {
  manual: "人工配置",
  ai_repository: "AI 仓库推断",
  ai_history: "AI 历史用例推断",
  diff_confirmation: "Diff 分析确认"
};

export function App() {
  const [session, setSession] = useState<Session | null>(() => {
    const stored = localStorage.getItem(SESSION_KEY);
    return stored ? (JSON.parse(stored) as Session) : null;
  });

  const handleSession = (nextSession: Session) => {
    localStorage.setItem(SESSION_KEY, JSON.stringify(nextSession));
    setSession(nextSession);
  };

  if (!session) {
    return <LoginView onSession={handleSession} />;
  }

  return (
    <Workbench
      session={session}
      onSignOut={() => {
        localStorage.removeItem(SESSION_KEY);
        setSession(null);
      }}
    />
  );
}

function LoginView({ onSession }: { onSession: (session: Session) => void }) {
  const [email, setEmail] = useState("owner@qualiforge.local");
  const [displayName, setDisplayName] = useState("Workspace Owner");
  const [workspaceName, setWorkspaceName] = useState("QualiForge Lab");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);

    try {
      const nextSession = await login({ email, display_name: displayName, workspace_name: workspaceName });
      onSession(nextSession);
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login-shell">
      <section className="login-panel" aria-label="QualiForge 登录">
        <div className="brand-mark">
          <Sparkles size={22} aria-hidden="true" />
          <span>QualiForge</span>
        </div>
        <div>
          <h1>私有化测试资产工作台</h1>
          <p>团队测试资产与发布决策的私有工作台。</p>
        </div>
        <form onSubmit={handleSubmit} className="login-form">
          <label>
            邮箱
            <input value={email} type="email" onChange={(event) => setEmail(event.target.value)} required />
          </label>
          <label>
            显示名称
            <input value={displayName} onChange={(event) => setDisplayName(event.target.value)} required />
          </label>
          <label>
            Workspace
            <input value={workspaceName} onChange={(event) => setWorkspaceName(event.target.value)} required />
          </label>
          {error ? <p className="form-error">{error}</p> : null}
          <button className="primary-button" type="submit" disabled={submitting}>
            <LogIn size={18} aria-hidden="true" />
            <span>{submitting ? "进入中" : "进入工作台"}</span>
          </button>
        </form>
      </section>
    </main>
  );
}

function Workbench({ session, onSignOut }: { session: Session; onSignOut: () => void }) {
  const [health, setHealth] = useState<HealthPayload | null>(null);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const [nextHealth, nextSummary] = await Promise.all([getHealth(), getDashboardSummary()]);
      setHealth(nextHealth);
      setSummary(nextSummary);
    } catch (err) {
      setError(err instanceof Error ? err.message : "工作台数据加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  const services = useMemo(() => {
    if (!health) return [];
    return Object.entries(health.services).map(([name, service]) => ({ name, ...service }));
  }, [health]);

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="主导航">
        <div className="brand-lockup">
          <div className="brand-icon">QF</div>
          <div>
            <strong>QualiForge</strong>
            <span>MVP Workbench</span>
          </div>
        </div>
        <nav>
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <button className={item.active ? "nav-button active" : "nav-button"} key={item.label} type="button">
                <Icon size={18} aria-hidden="true" />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div>
            <span className="eyebrow">{session.workspace.name}</span>
            <h1>工作台</h1>
          </div>
          <div className="topbar-actions">
            <StatusPill status={health?.status ?? "degraded"} />
            <button className="icon-button" type="button" onClick={() => void refresh()} title="刷新状态">
              <RefreshCcw size={18} aria-hidden="true" />
            </button>
            <button className="ghost-button" type="button" onClick={onSignOut}>
              退出
            </button>
          </div>
        </header>

        {error ? (
          <section className="notice error">
            <AlertCircle size={18} aria-hidden="true" />
            <span>{error}</span>
          </section>
        ) : null}

        <section className="status-grid" aria-label="服务状态">
          <StatusTile label="Backend API" status={health?.status ?? (loading ? "checking" : "degraded")} detail={health?.environment ?? "local"} />
          {services.map((service) => (
            <StatusTile key={service.name} label={service.name} status={service.status} detail={service.detail} />
          ))}
        </section>

        <section className="workbench-layout">
          <div className="main-column">
            <section className="section-block">
              <div className="section-heading">
                <div>
                  <span className="eyebrow">Issue Chain</span>
                  <h2>{summary?.mvp_stage ?? "基础平台"}</h2>
                </div>
                <Activity size={20} aria-hidden="true" />
              </div>
              <div className="issue-table" role="table" aria-label="MVP issue 队列">
                <div className="issue-row issue-head" role="row">
                  <span>Issue</span>
                  <span>标题</span>
                  <span>Owner</span>
                  <span>状态</span>
                </div>
                {(summary?.work_items ?? []).map((item) => (
                  <div className="issue-row" role="row" key={item.issue}>
                    <span className="issue-id">{item.issue}</span>
                    <span>{item.title}</span>
                    <span>{item.owner}</span>
                    <StatusPill status={item.status} />
                  </div>
                ))}
              </div>
            </section>

            <section className="section-block">
              <div className="section-heading">
                <div>
                  <span className="eyebrow">Jobs</span>
                  <h2>最近任务</h2>
                </div>
                <Database size={20} aria-hidden="true" />
              </div>
              <div className="job-list">
                {(summary?.recent_jobs ?? []).map((job) => (
                  <div className="job-row" key={`${job.type}-${job.created_at}`}>
                    <CheckCircle2 size={18} aria-hidden="true" />
                    <div>
                      <strong>{job.summary}</strong>
                      <span>{job.type} · {job.status}</span>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <WorkspaceAdmin session={session} />
            <GitLabSandboxAdmin session={session} />
            <ModuleMappingAdmin session={session} />
            <DiffAnalysisAdmin session={session} />
            <CaseImportAdmin session={session} />
            <CaseReviewAdmin session={session} />
            <AIConfigAdmin session={session} />
          </div>

          <aside className="side-column" aria-label="待办概览">
            {(summary?.queues ?? []).map((queue) => (
              <div className="metric-card" key={queue.label}>
                <span>{queue.label}</span>
                <strong>{queue.value}</strong>
                <small>{queue.trend}</small>
              </div>
            ))}
          </aside>
        </section>
      </main>
    </div>
  );
}

function WorkspaceAdmin({ session }: { session: Session }) {
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
          <h2>成员、项目和审计</h2>
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
        </div>

        <section className="audit-pane" aria-label="审计日志">
          <div className="pane-heading">
            <div>
              <span className="eyebrow">Audit</span>
              <h3>最近审计</h3>
            </div>
            <History size={18} aria-hidden="true" />
          </div>
          <div className="audit-list">
            {auditLogs.slice(0, 8).map((entry) => (
              <div className="audit-row" key={entry.id}>
                <span>{entry.action}</span>
                <strong>{entry.summary}</strong>
                <small>{entry.actor_email}</small>
              </div>
            ))}
            {auditLogs.length === 0 ? <p className="empty-state">暂无审计记录</p> : null}
          </div>
        </section>
      </div>
    </section>
  );
}

function GitLabSandboxAdmin({ session }: { session: Session }) {
  const actorEmail = session.user.email;
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

  async function refreshGitWorkspaces(preferredWorkspaceId?: string) {
    setBusy(true);
    setMessage(null);
    try {
      const nextWorkspaces = await listWorkspaces(actorEmail);
      setWorkspaces(nextWorkspaces);
      const nextSelectedId = preferredWorkspaceId || selectedWorkspaceId || nextWorkspaces[0]?.id || "";
      setSelectedWorkspaceId(nextSelectedId);
      if (nextSelectedId) {
        await refreshGitConfig(nextSelectedId);
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "GitLab 配置加载失败");
    } finally {
      setBusy(false);
    }
  }

  async function refreshGitConfig(workspaceId: string) {
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
    if (!projectId && nextProjects[0]) {
      setProjectId(nextProjects[0].id);
    }
  }

  useEffect(() => {
    void refreshGitWorkspaces();
  }, []);

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
              <span className="eyebrow">Sandbox Mirrors</span>
              <h3>仓库镜像</h3>
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
            {jobs.slice(0, 8).map((job) => (
              <div className="audit-row" key={job.id}>
                <span>{statusLabel[job.status]}</span>
                <strong>{job.input_summary}</strong>
                <small>{job.error_summary || job.output_summary || job.key_logs[0]}</small>
              </div>
            ))}
            {jobs.length === 0 ? <p className="empty-state">暂无同步任务</p> : null}
          </div>
        </section>
      </div>
    </section>
  );
}

function ModuleMappingAdmin({ session }: { session: Session }) {
  const actorEmail = session.user.email;
  const [workspaces, setWorkspaces] = useState<WorkspaceRecord[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState("");
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [modules, setModules] = useState<ProjectModuleRecord[]>([]);
  const [mappingRules, setMappingRules] = useState<ModuleMappingRuleRecord[]>([]);
  const [moduleKey, setModuleKey] = useState("PAYMENT");
  const [moduleName, setModuleName] = useState("支付与退款");
  const [moduleDescription, setModuleDescription] = useState("Checkout payment and refund behavior");
  const [moduleOwner, setModuleOwner] = useState("Checkout QA");
  const [editingModuleId, setEditingModuleId] = useState<string | null>(null);
  const [ruleModuleId, setRuleModuleId] = useState("");
  const [ruleType, setRuleType] = useState<MappingRuleType>("directory");
  const [rulePattern, setRulePattern] = useState("backend/app/payments/**");
  const [ruleSource, setRuleSource] = useState<MappingSource>("manual");
  const [ruleDescription, setRuleDescription] = useState("Payment implementation surface");
  const [ruleConfidence, setRuleConfidence] = useState("90");
  const [editingRuleId, setEditingRuleId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function refreshProjectModules(workspaceId: string, projectId: string) {
    const [nextModules, nextRules] = await Promise.all([listModules(workspaceId, projectId), listMappingRules(workspaceId, projectId)]);
    setModules(nextModules);
    setMappingRules(nextRules);
    if (!ruleModuleId || !nextModules.some((module) => module.id === ruleModuleId)) {
      setRuleModuleId(nextModules[0]?.id ?? "");
    }
  }

  async function refreshModuleWorkspaces(preferredWorkspaceId?: string, preferredProjectId?: string) {
    setBusy(true);
    setMessage(null);
    try {
      const nextWorkspaces = await listWorkspaces(actorEmail);
      setWorkspaces(nextWorkspaces);
      const nextWorkspaceId = preferredWorkspaceId || selectedWorkspaceId || nextWorkspaces[0]?.id || "";
      setSelectedWorkspaceId(nextWorkspaceId);
      if (!nextWorkspaceId) {
        setProjects([]);
        setModules([]);
        setMappingRules([]);
        return;
      }

      const nextProjects = await listProjects(nextWorkspaceId);
      setProjects(nextProjects);
      const nextProjectId = preferredProjectId || selectedProjectId || nextProjects[0]?.id || "";
      setSelectedProjectId(nextProjectId);
      if (nextProjectId) {
        await refreshProjectModules(nextWorkspaceId, nextProjectId);
      } else {
        setModules([]);
        setMappingRules([]);
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "模块配置加载失败");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void refreshModuleWorkspaces();
  }, []);

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
        await refreshProjectModules(workspaceId, nextProjectId);
      } else {
        setModules([]);
        setMappingRules([]);
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "模块 Workspace 切换失败");
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
      await refreshProjectModules(selectedWorkspaceId, projectId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "模块项目切换失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleModuleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedWorkspaceId || !selectedProjectId) return;
    setBusy(true);
    setMessage(null);
    try {
      if (editingModuleId) {
        const module = await updateModule(selectedWorkspaceId, selectedProjectId, editingModuleId, actorEmail, {
          name: moduleName,
          description: moduleDescription,
          owner: moduleOwner
        });
        setMessage(`已更新模块：${module.key}`);
      } else {
        const module = await createModule(selectedWorkspaceId, selectedProjectId, actorEmail, {
          key: moduleKey,
          name: moduleName,
          description: moduleDescription,
          owner: moduleOwner
        });
        setRuleModuleId(module.id);
        setMessage(`已创建模块：${module.key}`);
      }
      clearModuleForm();
      await refreshProjectModules(selectedWorkspaceId, selectedProjectId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "模块保存失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleModuleDelete(moduleId: string) {
    if (!selectedWorkspaceId || !selectedProjectId) return;
    setBusy(true);
    setMessage(null);
    try {
      await deleteModule(selectedWorkspaceId, selectedProjectId, moduleId, actorEmail);
      setMessage("已删除模块");
      await refreshProjectModules(selectedWorkspaceId, selectedProjectId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "模块删除失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleRuleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedWorkspaceId || !selectedProjectId || !ruleModuleId) return;
    setBusy(true);
    setMessage(null);
    try {
      if (editingRuleId) {
        const rule = await updateMappingRule(selectedWorkspaceId, selectedProjectId, ruleModuleId, editingRuleId, actorEmail, {
          rule_type: ruleType,
          pattern: rulePattern,
          source: ruleSource,
          description: ruleDescription,
          confidence: Number(ruleConfidence)
        });
        setMessage(`已更新映射规则：${mappingRuleTypeLabel[rule.rule_type]}`);
      } else {
        const rule = await createMappingRule(selectedWorkspaceId, selectedProjectId, ruleModuleId, actorEmail, {
          rule_type: ruleType,
          pattern: rulePattern,
          source: ruleSource,
          description: ruleDescription,
          confidence: Number(ruleConfidence)
        });
        setMessage(`已创建映射规则：${mappingRuleTypeLabel[rule.rule_type]}`);
      }
      clearRuleForm();
      await refreshProjectModules(selectedWorkspaceId, selectedProjectId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "映射规则保存失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleRuleDelete(rule: ModuleMappingRuleRecord) {
    if (!selectedWorkspaceId || !selectedProjectId) return;
    setBusy(true);
    setMessage(null);
    try {
      await deleteMappingRule(selectedWorkspaceId, selectedProjectId, rule.module_id, rule.id, actorEmail);
      setMessage("已删除映射规则");
      await refreshProjectModules(selectedWorkspaceId, selectedProjectId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "映射规则删除失败");
    } finally {
      setBusy(false);
    }
  }

  function editModule(module: ProjectModuleRecord) {
    setEditingModuleId(module.id);
    setModuleKey(module.key);
    setModuleName(module.name);
    setModuleDescription(module.description);
    setModuleOwner(module.owner);
  }

  function editRule(rule: ModuleMappingRuleRecord) {
    setEditingRuleId(rule.id);
    setRuleModuleId(rule.module_id);
    setRuleType(rule.rule_type);
    setRulePattern(rule.pattern);
    setRuleSource(rule.source);
    setRuleDescription(rule.description);
    setRuleConfidence(String(rule.confidence));
  }

  function clearModuleForm() {
    setEditingModuleId(null);
    setModuleKey("");
    setModuleName("");
    setModuleDescription("");
    setModuleOwner("");
  }

  function clearRuleForm() {
    setEditingRuleId(null);
    setRuleType("directory");
    setRulePattern("");
    setRuleSource("manual");
    setRuleDescription("");
    setRuleConfidence("90");
  }

  const selectedWorkspace = workspaces.find((workspace) => workspace.id === selectedWorkspaceId);
  const selectedProject = projects.find((project) => project.id === selectedProjectId);
  const moduleById = new Map(modules.map((module) => [module.id, module]));

  return (
    <section className="section-block module-admin">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Module Mapping</span>
          <h2>模块和映射规则</h2>
        </div>
        <Network size={20} aria-hidden="true" />
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
          <label className="select-label">
            当前 Project
            <select
              value={selectedProjectId}
              onChange={(event) => void handleProjectSwitch(event.target.value)}
              disabled={busy || projects.length === 0}
            >
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
          <strong>{selectedProject ? `${selectedProject.key} · ${selectedProject.name}` : selectedWorkspace?.name ?? "尚未选择 Project"}</strong>
          <span>{selectedProject ? `${modules.length} modules · ${mappingRules.length} mapping rules` : "先创建 Project，然后维护业务模块和技术映射。"}</span>
        </div>

        <div className="admin-grid">
          <section className="admin-pane" aria-label="模块管理">
            <div className="pane-heading">
              <div>
                <span className="eyebrow">Modules</span>
                <h3>模块/功能域</h3>
              </div>
              <FolderKanban size={18} aria-hidden="true" />
            </div>
            <form className="stack-form" onSubmit={handleModuleSave}>
              <div className="form-row">
                <label>
                  Key
                  <input
                    value={moduleKey}
                    onChange={(event) => setModuleKey(event.target.value.toUpperCase())}
                    disabled={Boolean(editingModuleId)}
                    required
                  />
                </label>
                <label>
                  名称
                  <input value={moduleName} onChange={(event) => setModuleName(event.target.value)} required />
                </label>
              </div>
              <label>
                描述
                <input value={moduleDescription} onChange={(event) => setModuleDescription(event.target.value)} />
              </label>
              <div className="form-row compact">
                <label>
                  Owner
                  <input value={moduleOwner} onChange={(event) => setModuleOwner(event.target.value)} />
                </label>
                <button className="ghost-button" type="submit" disabled={busy || !selectedWorkspaceId || !selectedProjectId}>
                  {editingModuleId ? "保存模块" : "创建模块"}
                </button>
                {editingModuleId ? (
                  <button className="ghost-button" type="button" onClick={clearModuleForm}>
                    取消
                  </button>
                ) : null}
              </div>
            </form>
            <div className="data-list">
              {modules.map((module) => (
                <div className="data-row module-row" key={module.id}>
                  <div>
                    <strong>{module.key} · {module.name}</strong>
                    <span>{module.description || "无描述"} · owner {module.owner || "none"} · {module.mapping_rules.length} rules</span>
                  </div>
                  <button className="icon-button subtle" type="button" onClick={() => editModule(module)} title="编辑模块">
                    <PencilLine size={16} aria-hidden="true" />
                  </button>
                  <button className="icon-button subtle" type="button" disabled={busy} onClick={() => void handleModuleDelete(module.id)} title="删除模块">
                    <Trash2 size={16} aria-hidden="true" />
                  </button>
                </div>
              ))}
              {modules.length === 0 ? <p className="empty-state">暂无模块</p> : null}
            </div>
          </section>

          <section className="admin-pane" aria-label="映射规则管理">
            <div className="pane-heading">
              <div>
                <span className="eyebrow">Mapping Rules</span>
                <h3>技术对象映射</h3>
              </div>
              <GitBranch size={18} aria-hidden="true" />
            </div>
            <form className="stack-form" onSubmit={handleRuleSave}>
              <label>
                模块
                <select
                  value={ruleModuleId}
                  onChange={(event) => setRuleModuleId(event.target.value)}
                  disabled={Boolean(editingRuleId)}
                  required
                >
                  <option value="">未选择</option>
                  {modules.map((module) => (
                    <option value={module.id} key={module.id}>
                      {module.key} · {module.name}
                    </option>
                  ))}
                </select>
              </label>
              <div className="form-row">
                <label>
                  类型
                  <select value={ruleType} onChange={(event) => setRuleType(event.target.value as MappingRuleType)}>
                    {(Object.keys(mappingRuleTypeLabel) as MappingRuleType[]).map((item) => (
                      <option value={item} key={item}>
                        {mappingRuleTypeLabel[item]}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  来源
                  <select value={ruleSource} onChange={(event) => setRuleSource(event.target.value as MappingSource)}>
                    {(Object.keys(mappingSourceLabel) as MappingSource[]).map((item) => (
                      <option value={item} key={item}>
                        {mappingSourceLabel[item]}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <label>
                Pattern
                <input value={rulePattern} onChange={(event) => setRulePattern(event.target.value)} required />
              </label>
              <div className="form-row compact">
                <label>
                  说明
                  <input value={ruleDescription} onChange={(event) => setRuleDescription(event.target.value)} />
                </label>
                <label>
                  置信度
                  <input type="number" min="0" max="100" value={ruleConfidence} onChange={(event) => setRuleConfidence(event.target.value)} />
                </label>
                <button className="ghost-button" type="submit" disabled={busy || !selectedWorkspaceId || !selectedProjectId || modules.length === 0}>
                  {editingRuleId ? "保存规则" : "添加规则"}
                </button>
                {editingRuleId ? (
                  <button className="ghost-button" type="button" onClick={clearRuleForm}>
                    取消
                  </button>
                ) : null}
              </div>
            </form>
          </section>
        </div>

        <section className="audit-pane" aria-label="Module Mapping 列表">
          <div className="pane-heading">
            <div>
              <span className="eyebrow">Reusable References</span>
              <h3>可引用映射规则</h3>
            </div>
            <FileText size={18} aria-hidden="true" />
          </div>
          <div className="data-list">
            {mappingRules.map((rule) => (
              <div className="data-row module-row" key={rule.id}>
                <div>
                  <strong>{moduleById.get(rule.module_id)?.key ?? "UNKNOWN"} · {mappingRuleTypeLabel[rule.rule_type]} · {rule.pattern}</strong>
                  <span>{mappingSourceLabel[rule.source]} · confidence {rule.confidence}% · id {rule.id}</span>
                  <small>{rule.description || "无说明"}</small>
                </div>
                <button className="icon-button subtle" type="button" onClick={() => editRule(rule)} title="编辑映射规则">
                  <PencilLine size={16} aria-hidden="true" />
                </button>
                <button className="icon-button subtle" type="button" disabled={busy} onClick={() => void handleRuleDelete(rule)} title="删除映射规则">
                  <Trash2 size={16} aria-hidden="true" />
                </button>
              </div>
            ))}
            {mappingRules.length === 0 ? <p className="empty-state">暂无映射规则</p> : null}
          </div>
        </section>
      </div>
    </section>
  );
}

function DiffAnalysisAdmin({ session }: { session: Session }) {
  const actorEmail = session.user.email;
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
    const nextRepositoryId = preferredRepositoryId || selectedRepositoryId || syncedRepository?.id || nextRepositories[0]?.id || "";
    const nextAnalysisId = preferredAnalysisId || selectedAnalysisId || nextAnalyses[0]?.id || "";
    setSelectedRepositoryId(nextRepositoryId);
    setSelectedAnalysisId(nextAnalysisId);
  }

  async function refreshDiffWorkspaces(preferredWorkspaceId?: string, preferredProjectId?: string, preferredAnalysisId?: string) {
    setBusy(true);
    setMessage(null);
    try {
      const nextWorkspaces = await listWorkspaces(actorEmail);
      setWorkspaces(nextWorkspaces);
      const nextWorkspaceId = preferredWorkspaceId || selectedWorkspaceId || nextWorkspaces[0]?.id || "";
      setSelectedWorkspaceId(nextWorkspaceId);
      if (!nextWorkspaceId) return;
      const nextProjects = await listProjects(nextWorkspaceId);
      setProjects(nextProjects);
      const nextProjectId = preferredProjectId || selectedProjectId || nextProjects[0]?.id || "";
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
    void refreshDiffWorkspaces();
  }, []);

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

function CaseImportAdmin({ session }: { session: Session }) {
  const actorEmail = session.user.email;
  const [workspaces, setWorkspaces] = useState<WorkspaceRecord[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState("");
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [modules, setModules] = useState<ProjectModuleRecord[]>([]);
  const [batches, setBatches] = useState<ImportBatchRecord[]>([]);
  const [selectedBatchId, setSelectedBatchId] = useState("");
  const [drafts, setDrafts] = useState<ImportDraftRecord[]>([]);
  const [testCases, setTestCases] = useState<TestCaseRecord[]>([]);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [bulkTitle, setBulkTitle] = useState("");
  const [bulkModuleId, setBulkModuleId] = useState("");
  const [bulkSteps, setBulkSteps] = useState("");
  const [bulkExpected, setBulkExpected] = useState("");
  const [bulkPriority, setBulkPriority] = useState("P1");
  const [bulkRisk, setBulkRisk] = useState("high");
  const [bulkTags, setBulkTags] = useState("checkout, imported");
  const [bulkCustomFields, setBulkCustomFields] = useState("{\"source\":\"legacy\"}");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function refreshImportProject(workspaceId: string, projectId: string, preferredBatchId?: string) {
    const [nextModules, nextBatches, nextTestCases] = await Promise.all([
      listModules(workspaceId, projectId),
      listImportBatches(workspaceId, projectId),
      listTestCases(workspaceId, projectId)
    ]);
    setModules(nextModules);
    setBatches(nextBatches);
    setTestCases(nextTestCases);
    const nextBatchId = preferredBatchId || selectedBatchId || nextBatches[0]?.id || "";
    setSelectedBatchId(nextBatchId);
    setDrafts(nextBatchId ? await listImportDrafts(workspaceId, projectId, nextBatchId) : []);
    if (!bulkModuleId && nextModules[0]) {
      setBulkModuleId(nextModules[0].id);
    }
  }

  async function refreshImportWorkspaces(preferredWorkspaceId?: string, preferredProjectId?: string, preferredBatchId?: string) {
    setBusy(true);
    setMessage(null);
    try {
      const nextWorkspaces = await listWorkspaces(actorEmail);
      setWorkspaces(nextWorkspaces);
      const nextWorkspaceId = preferredWorkspaceId || selectedWorkspaceId || nextWorkspaces[0]?.id || "";
      setSelectedWorkspaceId(nextWorkspaceId);
      if (!nextWorkspaceId) return;
      const nextProjects = await listProjects(nextWorkspaceId);
      setProjects(nextProjects);
      const nextProjectId = preferredProjectId || selectedProjectId || nextProjects[0]?.id || "";
      setSelectedProjectId(nextProjectId);
      if (nextProjectId) {
        await refreshImportProject(nextWorkspaceId, nextProjectId, preferredBatchId);
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "导入数据加载失败");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void refreshImportWorkspaces();
  }, []);

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
        await refreshImportProject(workspaceId, nextProjectId);
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "导入 Workspace 切换失败");
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
      await refreshImportProject(selectedWorkspaceId, projectId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "导入 Project 切换失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleBatchSelect(batchId: string) {
    setSelectedBatchId(batchId);
    if (!selectedWorkspaceId || !selectedProjectId || !batchId) return;
    setBusy(true);
    setMessage(null);
    try {
      setDrafts(await listImportDrafts(selectedWorkspaceId, selectedProjectId, batchId));
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "导入草稿加载失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedWorkspaceId || !selectedProjectId || !importFile) return;
    setBusy(true);
    setMessage(null);
    try {
      const batch = await uploadImportBatch(selectedWorkspaceId, selectedProjectId, actorEmail, importFile);
      await new Promise((resolve) => window.setTimeout(resolve, 700));
      setMessage(`已上传并创建导入 Job：${batch.file_name}`);
      setImportFile(null);
      await refreshImportProject(selectedWorkspaceId, selectedProjectId, batch.id);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "文件上传失败");
    } finally {
      setBusy(false);
    }
  }

  function parseTagsInput(value: string): string[] {
    return value.split(/[,，;；\s]+/).map((item) => item.trim()).filter(Boolean);
  }

  function parseStepsInput(value: string): string[] {
    return value.split(/\r?\n|;|；/).map((item) => item.trim()).filter(Boolean);
  }

  function buildBulkPayload() {
    const payload: Record<string, unknown> = {};
    if (bulkTitle.trim()) payload.title = bulkTitle.trim();
    if (bulkModuleId) payload.module_id = bulkModuleId;
    if (bulkSteps.trim()) payload.steps = parseStepsInput(bulkSteps);
    if (bulkExpected.trim()) payload.expected_result = bulkExpected.trim();
    if (bulkPriority.trim()) payload.priority = bulkPriority.trim();
    if (bulkRisk.trim()) payload.risk = bulkRisk.trim();
    const tags = parseTagsInput(bulkTags);
    if (tags.length) payload.tags = tags;
    if (bulkCustomFields.trim()) {
      payload.custom_fields = JSON.parse(bulkCustomFields) as Record<string, string>;
    }
    return payload;
  }

  async function handleBulkUpdate() {
    if (!selectedWorkspaceId || !selectedProjectId || !selectedBatchId) return;
    setBusy(true);
    setMessage(null);
    try {
      await bulkUpdateImportDrafts(selectedWorkspaceId, selectedProjectId, selectedBatchId, actorEmail, buildBulkPayload());
      setMessage("已批量修正导入草稿");
      await refreshImportProject(selectedWorkspaceId, selectedProjectId, selectedBatchId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "批量修正失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleSubmitReview() {
    if (!selectedWorkspaceId || !selectedProjectId || !selectedBatchId) return;
    setBusy(true);
    setMessage(null);
    try {
      const batch = await submitImportReview(selectedWorkspaceId, selectedProjectId, selectedBatchId, actorEmail);
      setMessage(`已提交评审：${statusLabel[batch.status]}`);
      await refreshImportProject(selectedWorkspaceId, selectedProjectId, selectedBatchId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "提交评审失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleBulkImport() {
    if (!selectedWorkspaceId || !selectedProjectId || !selectedBatchId) return;
    setBusy(true);
    setMessage(null);
    try {
      const result = await bulkImportTestCases(selectedWorkspaceId, selectedProjectId, selectedBatchId, actorEmail);
      setMessage(`已入库正式用例：${result.imported_count} 条`);
      await refreshImportProject(selectedWorkspaceId, selectedProjectId, selectedBatchId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "批量入库失败");
    } finally {
      setBusy(false);
    }
  }

  const selectedProject = projects.find((project) => project.id === selectedProjectId);
  const selectedBatch = batches.find((batch) => batch.id === selectedBatchId);
  const moduleById = new Map(modules.map((module) => [module.id, module]));

  return (
    <section className="section-block import-admin">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Case Import</span>
          <h2>历史用例导入</h2>
        </div>
        <ClipboardCheck size={20} aria-hidden="true" />
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
          <label className="select-label">
            当前 Project
            <select
              value={selectedProjectId}
              onChange={(event) => void handleProjectSwitch(event.target.value)}
              disabled={busy || projects.length === 0}
            >
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
          <span>{batches.length} import batches · {drafts.length} preview drafts · {testCases.length} formal cases</span>
        </div>

        <div className="admin-grid">
          <section className="admin-pane" aria-label="上传历史用例">
            <div className="pane-heading">
              <div>
                <span className="eyebrow">Upload</span>
                <h3>Excel / CSV</h3>
              </div>
              <FileText size={18} aria-hidden="true" />
            </div>
            <form className="stack-form" onSubmit={handleUpload}>
              <label>
                文件
                <input
                  type="file"
                  accept=".csv,.xlsx"
                  onChange={(event) => setImportFile(event.target.files?.[0] ?? null)}
                  required
                />
              </label>
              <button className="ghost-button" type="submit" disabled={busy || !selectedWorkspaceId || !selectedProjectId || !importFile}>
                上传并解析
              </button>
            </form>
            <div className="data-list">
              {batches.map((batch) => (
                <div className="data-row module-row" key={batch.id}>
                  <div>
                    <strong>{batch.file_name} · {statusLabel[batch.status]}</strong>
                    <span>{batch.row_count} rows · job {batch.job_id?.slice(0, 8) ?? "none"}</span>
                    <small>{batch.original_file_path}</small>
                  </div>
                  <button className="ghost-button" type="button" onClick={() => void handleBatchSelect(batch.id)}>
                    查看
                  </button>
                </div>
              ))}
              {batches.length === 0 ? <p className="empty-state">暂无导入批次</p> : null}
            </div>
          </section>

          <section className="admin-pane" aria-label="批量修正导入草稿">
            <div className="pane-heading">
              <div>
                <span className="eyebrow">Bulk Fix</span>
                <h3>预览批量修正</h3>
              </div>
              <PencilLine size={18} aria-hidden="true" />
            </div>
            <form className="stack-form" onSubmit={(event) => event.preventDefault()}>
              <div className="form-row">
                <label>
                  标题
                  <input value={bulkTitle} onChange={(event) => setBulkTitle(event.target.value)} />
                </label>
                <label>
                  模块
                  <select value={bulkModuleId} onChange={(event) => setBulkModuleId(event.target.value)}>
                    <option value="">不修改</option>
                    {modules.map((module) => (
                      <option value={module.id} key={module.id}>
                        {module.key} · {module.name}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <label>
                步骤
                <input value={bulkSteps} onChange={(event) => setBulkSteps(event.target.value)} />
              </label>
              <label>
                预期
                <input value={bulkExpected} onChange={(event) => setBulkExpected(event.target.value)} />
              </label>
              <div className="form-row">
                <label>
                  优先级
                  <input value={bulkPriority} onChange={(event) => setBulkPriority(event.target.value)} />
                </label>
                <label>
                  风险
                  <input value={bulkRisk} onChange={(event) => setBulkRisk(event.target.value)} />
                </label>
              </div>
              <label>
                标签
                <input value={bulkTags} onChange={(event) => setBulkTags(event.target.value)} />
              </label>
              <label>
                自定义字段 JSON
                <input value={bulkCustomFields} onChange={(event) => setBulkCustomFields(event.target.value)} />
              </label>
              <div className="form-row compact">
                <button className="ghost-button" type="button" onClick={() => void handleBulkUpdate()} disabled={busy || !selectedBatchId || drafts.length === 0}>
                  批量修正
                </button>
                <button className="ghost-button" type="button" onClick={() => void handleSubmitReview()} disabled={busy || !selectedBatchId || drafts.length === 0}>
                  提交评审
                </button>
                <button className="primary-button small" type="button" onClick={() => void handleBulkImport()} disabled={busy || !selectedBatchId || drafts.length === 0}>
                  批量入库
                </button>
              </div>
            </form>
          </section>
        </div>

        <section className="audit-pane" aria-label="导入草稿预览">
          <div className="pane-heading">
            <div>
              <span className="eyebrow">Preview</span>
              <h3>导入草稿</h3>
            </div>
            <ClipboardCheck size={18} aria-hidden="true" />
          </div>
          <div className="data-list">
            {drafts.map((draft) => (
              <div className="data-row wide" key={draft.id}>
                <div>
                  <strong>
                    #{draft.source_row_index} {draft.title} · {statusLabel[draft.status]}
                  </strong>
                  <span>
                    {moduleById.get(draft.module_id ?? "")?.key ?? "未归属"} · {draft.priority} · {draft.risk} · {draft.tags.join(", ") || "no tags"}
                  </span>
                  <small>{draft.steps.join(" / ")} → {draft.expected_result}</small>
                </div>
              </div>
            ))}
            {drafts.length === 0 ? <p className="empty-state">{selectedBatch ? "暂无草稿" : "选择或上传导入批次"}</p> : null}
          </div>
        </section>
      </div>
    </section>
  );
}

function CaseReviewAdmin({ session }: { session: Session }) {
  const actorEmail = session.user.email;
  const [workspaces, setWorkspaces] = useState<WorkspaceRecord[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState("");
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [modules, setModules] = useState<ProjectModuleRecord[]>([]);
  const [settings, setSettings] = useState<ReviewSettingsRecord | null>(null);
  const [testCases, setTestCases] = useState<TestCaseRecord[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState("");
  const [reviews, setReviews] = useState<CaseReviewRecord[]>([]);
  const [revisions, setRevisions] = useState<CaseRevisionRecord[]>([]);
  const [allowSelfReview, setAllowSelfReview] = useState(false);
  const [requireReviewOnUpdate, setRequireReviewOnUpdate] = useState(true);
  const [caseTitle, setCaseTitle] = useState("Checkout payment succeeds");
  const [caseModuleId, setCaseModuleId] = useState("");
  const [caseSteps, setCaseSteps] = useState("Open checkout\nPay order");
  const [caseExpected, setCaseExpected] = useState("Order is paid and receipt is visible");
  const [casePriority, setCasePriority] = useState("P1");
  const [caseRisk, setCaseRisk] = useState("high");
  const [caseTags, setCaseTags] = useState("checkout, review");
  const [caseCustomFields, setCaseCustomFields] = useState("{\"source\":\"manual\"}");
  const [reviewComment, setReviewComment] = useState("Looks good");
  const [editTitle, setEditTitle] = useState("Checkout payment succeeds after 3DS");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  function parseList(value: string): string[] {
    return value.split(/\r?\n|[,，;；]/).map((item) => item.trim()).filter(Boolean);
  }

  function buildCasePayload(): TestCasePayload {
    return {
      module_id: caseModuleId || null,
      title: caseTitle,
      steps: parseList(caseSteps),
      expected_result: caseExpected,
      priority: casePriority,
      risk: caseRisk,
      tags: parseList(caseTags),
      custom_fields: caseCustomFields.trim() ? (JSON.parse(caseCustomFields) as Record<string, string>) : {}
    };
  }

  async function refreshSelectedCase(workspaceId: string, projectId: string, caseId: string) {
    if (!caseId) {
      setReviews([]);
      setRevisions([]);
      return;
    }
    const [nextReviews, nextRevisions] = await Promise.all([
      listCaseReviews(workspaceId, projectId, caseId),
      listCaseRevisions(workspaceId, projectId, caseId)
    ]);
    setReviews(nextReviews);
    setRevisions(nextRevisions);
  }

  async function refreshCaseProject(workspaceId: string, projectId: string, preferredCaseId?: string) {
    const [nextModules, nextCases] = await Promise.all([listModules(workspaceId, projectId), listTestCases(workspaceId, projectId)]);
    setModules(nextModules);
    setTestCases(nextCases);
    if (!caseModuleId && nextModules[0]) {
      setCaseModuleId(nextModules[0].id);
    }
    const nextCaseId = preferredCaseId || selectedCaseId || nextCases[0]?.id || "";
    setSelectedCaseId(nextCaseId);
    await refreshSelectedCase(workspaceId, projectId, nextCaseId);
  }

  async function refreshCaseWorkspaces(preferredWorkspaceId?: string, preferredProjectId?: string, preferredCaseId?: string) {
    setBusy(true);
    setMessage(null);
    try {
      const nextWorkspaces = await listWorkspaces(actorEmail);
      setWorkspaces(nextWorkspaces);
      const nextWorkspaceId = preferredWorkspaceId || selectedWorkspaceId || nextWorkspaces[0]?.id || "";
      setSelectedWorkspaceId(nextWorkspaceId);
      if (!nextWorkspaceId) return;
      const nextSettings = await getReviewSettings(nextWorkspaceId);
      setSettings(nextSettings);
      setAllowSelfReview(nextSettings.allow_self_review);
      setRequireReviewOnUpdate(nextSettings.require_review_on_case_update);
      const nextProjects = await listProjects(nextWorkspaceId);
      setProjects(nextProjects);
      const nextProjectId = preferredProjectId || selectedProjectId || nextProjects[0]?.id || "";
      setSelectedProjectId(nextProjectId);
      if (nextProjectId) {
        await refreshCaseProject(nextWorkspaceId, nextProjectId, preferredCaseId);
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "评审数据加载失败");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void refreshCaseWorkspaces();
  }, []);

  async function handleWorkspaceSwitch(workspaceId: string) {
    setSelectedWorkspaceId(workspaceId);
    setBusy(true);
    setMessage(null);
    try {
      const [nextSettings, nextProjects] = await Promise.all([getReviewSettings(workspaceId), listProjects(workspaceId)]);
      setSettings(nextSettings);
      setAllowSelfReview(nextSettings.allow_self_review);
      setRequireReviewOnUpdate(nextSettings.require_review_on_case_update);
      setProjects(nextProjects);
      const nextProjectId = nextProjects[0]?.id ?? "";
      setSelectedProjectId(nextProjectId);
      if (nextProjectId) {
        await refreshCaseProject(workspaceId, nextProjectId);
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "评审 Workspace 切换失败");
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
      await refreshCaseProject(selectedWorkspaceId, projectId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "评审 Project 切换失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleSettingsSave() {
    if (!selectedWorkspaceId) return;
    setBusy(true);
    setMessage(null);
    try {
      const nextSettings = await updateReviewSettings(selectedWorkspaceId, actorEmail, {
        allow_self_review: allowSelfReview,
        require_review_on_case_update: requireReviewOnUpdate
      });
      setSettings(nextSettings);
      setMessage("已保存评审策略");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "评审策略保存失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateCase(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedWorkspaceId || !selectedProjectId) return;
    setBusy(true);
    setMessage(null);
    try {
      const created = await createTestCase(selectedWorkspaceId, selectedProjectId, actorEmail, buildCasePayload());
      setMessage(`已创建候选用例：${created.title}`);
      await refreshCaseProject(selectedWorkspaceId, selectedProjectId, created.id);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "候选用例创建失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleSelectCase(caseId: string) {
    setSelectedCaseId(caseId);
    if (!selectedWorkspaceId || !selectedProjectId) return;
    setBusy(true);
    setMessage(null);
    try {
      await refreshSelectedCase(selectedWorkspaceId, selectedProjectId, caseId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "评审详情加载失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleSubmitCase(caseId: string) {
    if (!selectedWorkspaceId || !selectedProjectId) return;
    setBusy(true);
    setMessage(null);
    try {
      const submitted = await submitTestCaseReview(selectedWorkspaceId, selectedProjectId, caseId, actorEmail);
      setMessage(`已提交评审：${submitted.title}`);
      await refreshCaseProject(selectedWorkspaceId, selectedProjectId, submitted.id);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "提交评审失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleReviewAction(action: CaseReviewAction) {
    if (!selectedWorkspaceId || !selectedProjectId || !selectedCaseId) return;
    setBusy(true);
    setMessage(null);
    try {
      await reviewTestCase(selectedWorkspaceId, selectedProjectId, selectedCaseId, actorEmail, {
        action,
        comment: reviewComment,
        edits: action === "edited" ? { title: editTitle } : undefined
      });
      setMessage(`已处理评审：${statusLabel[action] ?? action}`);
      await refreshCaseProject(selectedWorkspaceId, selectedProjectId, selectedCaseId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "评审操作失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleDirectEdit() {
    if (!selectedWorkspaceId || !selectedProjectId || !selectedCaseId) return;
    setBusy(true);
    setMessage(null);
    try {
      const updated = await updateTestCase(selectedWorkspaceId, selectedProjectId, selectedCaseId, actorEmail, { title: editTitle });
      setMessage(`已修改正式用例：${statusLabel[updated.status]}`);
      await refreshCaseProject(selectedWorkspaceId, selectedProjectId, updated.id);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "正式用例修改失败");
    } finally {
      setBusy(false);
    }
  }

  const selectedProject = projects.find((project) => project.id === selectedProjectId);
  const selectedCase = testCases.find((item) => item.id === selectedCaseId);
  const moduleById = new Map(modules.map((module) => [module.id, module]));

  return (
    <section className="section-block review-admin">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Case Review</span>
          <h2>用例评审治理</h2>
        </div>
        <ShieldCheck size={20} aria-hidden="true" />
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
          <span>
            {testCases.length} cases · {settings ? `self review ${settings.allow_self_review ? "on" : "off"} · update review ${settings.require_review_on_case_update ? "on" : "off"}` : "loading"}
          </span>
        </div>

        <div className="admin-grid">
          <section className="admin-pane" aria-label="评审策略">
            <div className="pane-heading">
              <div>
                <span className="eyebrow">Policy</span>
                <h3>评审策略</h3>
              </div>
              <Settings2 size={18} aria-hidden="true" />
            </div>
            <div className="stack-form">
              <label className="checkbox-label">
                <input type="checkbox" checked={allowSelfReview} onChange={(event) => setAllowSelfReview(event.target.checked)} />
                允许提交人自评审
              </label>
              <label className="checkbox-label">
                <input type="checkbox" checked={requireReviewOnUpdate} onChange={(event) => setRequireReviewOnUpdate(event.target.checked)} />
                正式用例修改后重新评审
              </label>
              <button className="ghost-button" type="button" onClick={() => void handleSettingsSave()} disabled={busy || !selectedWorkspaceId}>
                保存策略
              </button>
            </div>
          </section>

          <section className="admin-pane" aria-label="创建候选用例">
            <div className="pane-heading">
              <div>
                <span className="eyebrow">Candidate</span>
                <h3>候选用例</h3>
              </div>
              <Plus size={18} aria-hidden="true" />
            </div>
            <form className="stack-form" onSubmit={handleCreateCase}>
              <label>
                标题
                <input value={caseTitle} onChange={(event) => setCaseTitle(event.target.value)} required />
              </label>
              <label>
                模块
                <select value={caseModuleId} onChange={(event) => setCaseModuleId(event.target.value)}>
                  <option value="">未归属</option>
                  {modules.map((module) => (
                    <option value={module.id} key={module.id}>
                      {module.key} · {module.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                步骤
                <input value={caseSteps} onChange={(event) => setCaseSteps(event.target.value)} />
              </label>
              <label>
                预期
                <input value={caseExpected} onChange={(event) => setCaseExpected(event.target.value)} />
              </label>
              <div className="form-row">
                <label>
                  优先级
                  <input value={casePriority} onChange={(event) => setCasePriority(event.target.value)} />
                </label>
                <label>
                  风险
                  <input value={caseRisk} onChange={(event) => setCaseRisk(event.target.value)} />
                </label>
              </div>
              <label>
                标签
                <input value={caseTags} onChange={(event) => setCaseTags(event.target.value)} />
              </label>
              <label>
                自定义字段 JSON
                <input value={caseCustomFields} onChange={(event) => setCaseCustomFields(event.target.value)} />
              </label>
              <button className="ghost-button" type="submit" disabled={busy || !selectedWorkspaceId || !selectedProjectId}>
                创建候选
              </button>
            </form>
          </section>
        </div>

        <section className="audit-pane" aria-label="用例库治理列表">
          <div className="pane-heading">
            <div>
              <span className="eyebrow">Library</span>
              <h3>用例库</h3>
            </div>
            <ClipboardCheck size={18} aria-hidden="true" />
          </div>
          <div className="data-list">
            {testCases.map((testCase) => (
              <div className="data-row module-row" key={testCase.id}>
                <div>
                  <strong>{testCase.title} · {statusLabel[testCase.status]}</strong>
                  <span>{moduleById.get(testCase.module_id ?? "")?.key ?? "未归属"} · rev {testCase.current_revision_number} · submitted {testCase.submitted_by || "none"}</span>
                  <small>{testCase.steps.join(" / ")} → {testCase.expected_result}</small>
                </div>
                <button className="ghost-button" type="button" onClick={() => void handleSelectCase(testCase.id)}>
                  查看
                </button>
                <button className="ghost-button" type="button" onClick={() => void handleSubmitCase(testCase.id)} disabled={busy}>
                  提交
                </button>
              </div>
            ))}
            {testCases.length === 0 ? <p className="empty-state">暂无用例</p> : null}
          </div>
        </section>

        <div className="admin-grid">
          <section className="admin-pane" aria-label="评审操作">
            <div className="pane-heading">
              <div>
                <span className="eyebrow">Review</span>
                <h3>评审操作</h3>
              </div>
              <ShieldCheck size={18} aria-hidden="true" />
            </div>
            <div className="stack-form">
              <div className="admin-context compact-context">
                <strong>{selectedCase?.title ?? "尚未选择用例"}</strong>
                <span>{selectedCase ? `${statusLabel[selectedCase.status]} · rev ${selectedCase.current_revision_number}` : "从用例库选择一条候选或正式用例。"}</span>
              </div>
              <label>
                评论
                <input value={reviewComment} onChange={(event) => setReviewComment(event.target.value)} />
              </label>
              <label>
                编辑标题
                <input value={editTitle} onChange={(event) => setEditTitle(event.target.value)} />
              </label>
              <div className="form-row compact review-actions">
                <button className="ghost-button" type="button" onClick={() => void handleReviewAction("commented")} disabled={busy || !selectedCaseId}>
                  评论
                </button>
                <button className="ghost-button" type="button" onClick={() => void handleReviewAction("edited")} disabled={busy || !selectedCaseId}>
                  评审编辑
                </button>
                <button className="ghost-button" type="button" onClick={() => void handleReviewAction("changes_requested")} disabled={busy || !selectedCaseId}>
                  要求修改
                </button>
                <button className="ghost-button" type="button" onClick={() => void handleReviewAction("rejected")} disabled={busy || !selectedCaseId}>
                  驳回
                </button>
                <button className="primary-button small" type="button" onClick={() => void handleReviewAction("approved")} disabled={busy || !selectedCaseId}>
                  通过
                </button>
                <button className="ghost-button" type="button" onClick={() => void handleDirectEdit()} disabled={busy || !selectedCaseId}>
                  修改正式用例
                </button>
              </div>
            </div>
          </section>

          <section className="admin-pane" aria-label="评审历史">
            <div className="pane-heading">
              <div>
                <span className="eyebrow">Trace</span>
                <h3>评审和 Revision</h3>
              </div>
              <History size={18} aria-hidden="true" />
            </div>
            <div className="audit-list">
              {reviews.slice(0, 5).map((review) => (
                <div className="audit-row" key={review.id}>
                  <span>{statusLabel[review.action] ?? review.action}</span>
                  <strong>{review.comment || review.actor_email}</strong>
                  <small>{review.revision_id ? `revision ${review.revision_id.slice(0, 8)}` : review.actor_email}</small>
                </div>
              ))}
              {reviews.length === 0 ? <p className="empty-state">暂无评审记录</p> : null}
            </div>
            <div className="data-list">
              {revisions.slice(0, 5).map((revision) => (
                <div className="data-row wide" key={revision.id}>
                  <div>
                    <strong>Revision {revision.revision_number} · {revision.change_summary}</strong>
                    <span>{revision.created_by} · title {(revision.content_snapshot.title as string) ?? "unknown"}</span>
                  </div>
                </div>
              ))}
              {revisions.length === 0 ? <p className="empty-state">暂无 Revision</p> : null}
            </div>
          </section>
        </div>
      </div>
    </section>
  );
}

function AIConfigAdmin({ session }: { session: Session }) {
  const actorEmail = session.user.email;
  const [workspaces, setWorkspaces] = useState<WorkspaceRecord[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState("");
  const [settings, setSettings] = useState<AISettingsRecord | null>(null);
  const [providers, setProviders] = useState<LLMProviderRecord[]>([]);
  const [profiles, setProfiles] = useState<ModelProfileRecord[]>([]);
  const [invocations, setInvocations] = useState<AIInvocationRecord[]>([]);
  const [providerName, setProviderName] = useState("OpenAI Compatible");
  const [apiBaseUrl, setApiBaseUrl] = useState("https://api.openai.example/v1");
  const [apiKey, setApiKey] = useState("");
  const [headersText, setHeadersText] = useState("{\"X-Team\":\"qa\"}");
  const [organization, setOrganization] = useState("qualiforge");
  const [policy, setPolicy] = useState<AIDataPolicy>("ExternalAllowed");
  const [profileProviderId, setProfileProviderId] = useState("");
  const [profilePurpose, setProfilePurpose] = useState<AIPurpose>("import_cleanup");
  const [modelName, setModelName] = useState("gpt-test");
  const [reasoningEffort, setReasoningEffort] = useState<"low" | "medium" | "high" | "xhigh">("medium");
  const [inputTokenPrice, setInputTokenPrice] = useState("2.00");
  const [outputTokenPrice, setOutputTokenPrice] = useState("8.00");
  const [invocationPurpose, setInvocationPurpose] = useState<AIPurpose>("import_cleanup");
  const [invocationSummary, setInvocationSummary] = useState("Normalize imported checkout test cases");
  const [includesSourceCode, setIncludesSourceCode] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function refreshAIWorkspaces(preferredWorkspaceId?: string) {
    setBusy(true);
    setMessage(null);
    try {
      const nextWorkspaces = await listWorkspaces(actorEmail);
      setWorkspaces(nextWorkspaces);
      const nextSelectedId = preferredWorkspaceId || selectedWorkspaceId || nextWorkspaces[0]?.id || "";
      setSelectedWorkspaceId(nextSelectedId);
      if (nextSelectedId) {
        await refreshAIConfig(nextSelectedId);
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "AI 配置加载失败");
    } finally {
      setBusy(false);
    }
  }

  async function refreshAIConfig(workspaceId: string) {
    const [nextSettings, nextProviders, nextProfiles, nextInvocations] = await Promise.all([
      getAISettings(workspaceId),
      listLLMProviders(workspaceId),
      listModelProfiles(workspaceId),
      listAIInvocations(workspaceId)
    ]);
    setSettings(nextSettings);
    setPolicy(nextSettings.data_policy);
    setProviders(nextProviders);
    setProfiles(nextProfiles);
    setInvocations(nextInvocations);
    if (!profileProviderId && nextProviders[0]) {
      setProfileProviderId(nextProviders[0].id);
    }
  }

  useEffect(() => {
    void refreshAIWorkspaces();
  }, []);

  async function handleWorkspaceSwitch(workspaceId: string) {
    setSelectedWorkspaceId(workspaceId);
    setBusy(true);
    setMessage(null);
    try {
      await refreshAIConfig(workspaceId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "AI Workspace 切换失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleProviderCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedWorkspaceId) return;
    setBusy(true);
    setMessage(null);
    try {
      const defaultHeaders = headersText.trim() ? (JSON.parse(headersText) as Record<string, string>) : {};
      const provider = await createLLMProvider(selectedWorkspaceId, actorEmail, {
        name: providerName,
        api_base_url: apiBaseUrl,
        api_key: apiKey,
        default_headers: defaultHeaders,
        organization
      });
      setMessage(`已创建 Provider：${provider.name}`);
      setProfileProviderId(provider.id);
      setApiKey("");
      await refreshAIConfig(selectedWorkspaceId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Provider 创建失败");
    } finally {
      setBusy(false);
    }
  }

  async function handlePolicyUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedWorkspaceId) return;
    setBusy(true);
    setMessage(null);
    try {
      const nextSettings = await updateAISettings(selectedWorkspaceId, actorEmail, policy);
      setSettings(nextSettings);
      setMessage(`已更新 AI 数据策略：${nextSettings.data_policy}`);
      await refreshAIConfig(selectedWorkspaceId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "AI 数据策略更新失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleProfileSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedWorkspaceId || !profileProviderId) return;
    setBusy(true);
    setMessage(null);
    try {
      const profile = await upsertModelProfile(selectedWorkspaceId, actorEmail, {
        provider_id: profileProviderId,
        purpose: profilePurpose,
        model_name: modelName,
        reasoning_effort: reasoningEffort,
        max_context_tokens: 128000,
        max_output_tokens: 4096,
        input_token_price: inputTokenPrice,
        output_token_price: outputTokenPrice,
        cache_policy: "semantic",
        timeout_seconds: 90,
        retry_count: 2,
        budget_limit: "25.00"
      });
      setMessage(`已配置 Model Profile：${purposeLabel[profile.purpose]}`);
      await refreshAIConfig(selectedWorkspaceId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Model Profile 保存失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleInvocationStart(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedWorkspaceId) return;
    setBusy(true);
    setMessage(null);
    try {
      const invocation = await startAIInvocation(selectedWorkspaceId, actorEmail, {
        purpose: invocationPurpose,
        input_summary: invocationSummary,
        input_data_types: includesSourceCode ? ["diff", "source_code"] : ["test_cases", "summary"],
        includes_source_code: includesSourceCode
      });
      setMessage(`已通过策略检查并排队：${purposeLabel[invocation.purpose]}`);
      await refreshAIConfig(selectedWorkspaceId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "AI 任务启动失败");
      await refreshAIConfig(selectedWorkspaceId);
    } finally {
      setBusy(false);
    }
  }

  async function handleCompleteLatest() {
    if (!selectedWorkspaceId) return;
    const queued = invocations.find((invocation) => invocation.status === "queued");
    if (!queued) {
      setMessage("没有可记录摘要的排队 AI 任务");
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      await completeAIInvocation(selectedWorkspaceId, queued.id, actorEmail, {
        status: "succeeded",
        token_prompt: 1200,
        token_completion: 480,
        cache_hit: false,
        latency_ms: 1420,
        failure_reason: ""
      });
      setMessage("已记录 AI 调用摘要");
      await refreshAIConfig(selectedWorkspaceId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "AI 调用摘要记录失败");
    } finally {
      setBusy(false);
    }
  }

  const selectedWorkspace = workspaces.find((workspace) => workspace.id === selectedWorkspaceId);

  return (
    <section className="section-block ai-admin">
      <div className="section-heading">
        <div>
          <span className="eyebrow">AI Platform</span>
          <h2>模型配置和数据策略</h2>
        </div>
        <BrainCircuit size={20} aria-hidden="true" />
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
          <form className="compact-form" onSubmit={handlePolicyUpdate}>
            <label>
              AI 数据策略
              <select value={policy} onChange={(event) => setPolicy(event.target.value as AIDataPolicy)} disabled={!selectedWorkspaceId}>
                {(Object.keys(policyLabel) as AIDataPolicy[]).map((item) => (
                  <option value={item} key={item}>
                    {policyLabel[item]}
                  </option>
                ))}
              </select>
            </label>
            <button className="primary-button small" type="submit" disabled={busy || !selectedWorkspaceId}>
              <ShieldAlert size={16} aria-hidden="true" />
              <span>保存</span>
            </button>
          </form>
        </div>

        <div className="admin-context">
          <strong>{selectedWorkspace?.name ?? "尚未选择 Workspace"}</strong>
          <span>{settings ? `Policy ${settings.data_policy} · updated by ${settings.updated_by}` : "创建 Workspace 后配置 AI Provider、模型用途和数据策略。"}</span>
        </div>

        <div className="admin-grid">
          <section className="admin-pane" aria-label="LLM Provider 配置">
            <div className="pane-heading">
              <div>
                <span className="eyebrow">Provider</span>
                <h3>OpenAI-compatible Provider</h3>
              </div>
              <KeyRound size={18} aria-hidden="true" />
            </div>
            <form className="stack-form" onSubmit={handleProviderCreate}>
              <label>
                名称
                <input value={providerName} onChange={(event) => setProviderName(event.target.value)} required />
              </label>
              <label>
                API Base URL
                <input value={apiBaseUrl} onChange={(event) => setApiBaseUrl(event.target.value)} required />
              </label>
              <label>
                API Key
                <input value={apiKey} onChange={(event) => setApiKey(event.target.value)} required />
              </label>
              <label>
                默认 Header JSON
                <input value={headersText} onChange={(event) => setHeadersText(event.target.value)} />
              </label>
              <div className="form-row compact">
                <label>
                  组织
                  <input value={organization} onChange={(event) => setOrganization(event.target.value)} />
                </label>
                <button className="ghost-button" type="submit" disabled={busy || !selectedWorkspaceId}>
                  创建 Provider
                </button>
              </div>
            </form>
            <div className="data-list">
              {providers.map((provider) => (
                <div className="data-row wide" key={provider.id}>
                  <div>
                    <strong>{provider.name}</strong>
                    <span>{provider.api_base_url} · key {provider.api_key_masked} · org {provider.organization || "none"}</span>
                  </div>
                </div>
              ))}
              {providers.length === 0 ? <p className="empty-state">暂无 Provider</p> : null}
            </div>
          </section>

          <section className="admin-pane" aria-label="Model Profile 配置">
            <div className="pane-heading">
              <div>
                <span className="eyebrow">Model Profiles</span>
                <h3>用途模型</h3>
              </div>
              <Settings2 size={18} aria-hidden="true" />
            </div>
            <form className="stack-form" onSubmit={handleProfileSave}>
              <label>
                Provider
                <select value={profileProviderId} onChange={(event) => setProfileProviderId(event.target.value)} required>
                  <option value="">未选择</option>
                  {providers.map((provider) => (
                    <option value={provider.id} key={provider.id}>
                      {provider.name}
                    </option>
                  ))}
                </select>
              </label>
              <div className="form-row">
                <label>
                  用途
                  <select value={profilePurpose} onChange={(event) => setProfilePurpose(event.target.value as AIPurpose)}>
                    {(Object.keys(purposeLabel) as AIPurpose[]).map((purpose) => (
                      <option value={purpose} key={purpose}>
                        {purposeLabel[purpose]}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  模型
                  <input value={modelName} onChange={(event) => setModelName(event.target.value)} required />
                </label>
              </div>
              <div className="form-row">
                <label>
                  思考等级
                  <select value={reasoningEffort} onChange={(event) => setReasoningEffort(event.target.value as "low" | "medium" | "high" | "xhigh")}>
                    <option value="low">low</option>
                    <option value="medium">medium</option>
                    <option value="high">high</option>
                    <option value="xhigh">xhigh</option>
                  </select>
                </label>
                <label>
                  输入价格 / 1M
                  <input value={inputTokenPrice} onChange={(event) => setInputTokenPrice(event.target.value)} />
                </label>
              </div>
              <div className="form-row compact">
                <label>
                  输出价格 / 1M
                  <input value={outputTokenPrice} onChange={(event) => setOutputTokenPrice(event.target.value)} />
                </label>
                <button className="ghost-button" type="submit" disabled={busy || !selectedWorkspaceId || providers.length === 0}>
                  保存用途
                </button>
              </div>
            </form>
            <div className="data-list">
              {profiles.map((profile) => (
                <div className="data-row wide" key={profile.id}>
                  <div>
                    <strong>{purposeLabel[profile.purpose]} · {profile.model_name}</strong>
                    <span>{profile.reasoning_effort} · cache {profile.cache_policy} · ${profile.input_token_price}/${profile.output_token_price}</span>
                  </div>
                </div>
              ))}
              {profiles.length === 0 ? <p className="empty-state">暂无 Model Profile</p> : null}
            </div>
          </section>
        </div>

        <section className="audit-pane" aria-label="AI 调用摘要">
          <div className="pane-heading">
            <div>
              <span className="eyebrow">AI Task Gate</span>
              <h3>策略检查和调用摘要</h3>
            </div>
            <BrainCircuit size={18} aria-hidden="true" />
          </div>
          <form className="stack-form" onSubmit={handleInvocationStart}>
            <div className="form-row">
              <label>
                用途
                <select value={invocationPurpose} onChange={(event) => setInvocationPurpose(event.target.value as AIPurpose)}>
                  {(Object.keys(purposeLabel) as AIPurpose[]).map((purpose) => (
                    <option value={purpose} key={purpose}>
                      {purposeLabel[purpose]}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                输入摘要
                <input value={invocationSummary} onChange={(event) => setInvocationSummary(event.target.value)} required />
              </label>
            </div>
            <div className="form-row compact">
              <label className="checkbox-label">
                <input type="checkbox" checked={includesSourceCode} onChange={(event) => setIncludesSourceCode(event.target.checked)} />
                包含源码
              </label>
              <button className="ghost-button" type="submit" disabled={busy || !selectedWorkspaceId}>
                启动 AI 任务
              </button>
              <button className="ghost-button" type="button" onClick={() => void handleCompleteLatest()} disabled={busy || !selectedWorkspaceId}>
                记录摘要
              </button>
            </div>
          </form>
          <div className="audit-list">
            {invocations.slice(0, 8).map((invocation) => (
              <div className="audit-row" key={invocation.id}>
                <span>{statusLabel[invocation.status]}</span>
                <strong>{purposeLabel[invocation.purpose]} · {invocation.input_summary}</strong>
                <small>
                  {invocation.token_prompt + invocation.token_completion} tokens · ${invocation.estimated_cost}
                  {invocation.failure_reason ? ` · ${invocation.failure_reason}` : ""}
                </small>
              </div>
            ))}
            {invocations.length === 0 ? <p className="empty-state">暂无 AI 调用摘要</p> : null}
          </div>
        </section>
      </div>
    </section>
  );
}

function StatusTile({ label, status, detail }: { label: string; status: string; detail: string }) {
  return (
    <div className="status-tile">
      <div>
        <span>{label}</span>
        <strong>{statusLabel[status] ?? status}</strong>
      </div>
      <small>{detail}</small>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  return <span className={`status-pill ${status}`}>{statusLabel[status] ?? status}</span>;
}
