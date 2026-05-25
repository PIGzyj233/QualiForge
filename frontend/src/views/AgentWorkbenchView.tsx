import { useEffect, useMemo, useState } from "react";
import { Bot, Boxes, Check, CircleStop, ClipboardCheck, FileSearch, GitBranch, ListChecks, Play, RefreshCcw, RotateCcw, Save, Search, X } from "lucide-react";
import {
  AgentExecutionDetailRecord,
  AgentMemoryFileRecord,
  AgentMemorySearchResult,
  AgentMemoryVersionRecord,
  AgentRunRecord,
  AgentRunStatus,
  AgentStagedOutputRecord,
  cancelAgentRun,
  curateAgentMemory,
  createAgentConversation,
  createAgentRun,
  decideAgentApproval,
  decideAgentStagedOutput,
  executeAgentRun,
  getAgentExecutionDetail,
  GitRepositoryRecord,
  listAgentMemoryVersions,
  listAgentRuns,
  listProjects,
  listRepositories,
  listWorkspaces,
  ProjectRecord,
  rollbackAgentMemory,
  resumeAgentRun,
  Session,
  searchAgentMemory,
  upsertAgentBudgetPolicy,
  WorkspaceRecord
} from "../api";
import { Pagination } from "../components/Pagination";
import { StatusPill } from "../components/StatusPill";
import { usePagination } from "../hooks/usePagination";
import { statusLabel } from "../lib/labels";

const runStatuses: Array<AgentRunStatus | "all"> = ["all", "queued", "running", "waiting_for_user", "succeeded", "failed", "cancelled"];

function formatDate(value: string | null) {
  if (!value) return "none";
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

function numberValue(value: unknown, fallback: number) {
  const next = Number(value);
  return Number.isFinite(next) ? next : fallback;
}

function shortJson(value: unknown) {
  if (value === null || value === undefined || value === "") return "none";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value).slice(0, 420);
}

function outputMeta(output: AgentStagedOutputRecord) {
  const payload = output.payload ?? {};
  const risk = typeof payload.risk === "string" ? payload.risk : "";
  const moduleKey = typeof payload.module_key === "string" ? payload.module_key : "UNMAPPED";
  const priority = typeof payload.priority === "string" ? payload.priority : "";
  return [output.output_type, moduleKey, risk, priority].filter(Boolean).join(" · ");
}

function evidenceLabel(refItem: Record<string, unknown>) {
  const label = refItem.label ?? refItem.summary ?? refItem.ref_id ?? refItem.kind;
  return shortJson(label);
}

function childWorkflowStats(item: Record<string, unknown>) {
  const metadata = item.metadata;
  if (!metadata || typeof metadata !== "object" || Array.isArray(metadata)) return "";
  const data = metadata as Record<string, unknown>;
  const parts: string[] = [];
  if (data.file_count !== undefined) parts.push(`${shortJson(data.file_count)} files`);
  if (data.batch_count !== undefined) parts.push(`${shortJson(data.batch_count)} batches`);
  if (data.draft_count !== undefined) parts.push(`${shortJson(data.draft_count)} drafts`);
  if (data.unmapped_draft_count !== undefined) parts.push(`${shortJson(data.unmapped_draft_count)} unmapped`);
  return parts.join(" · ");
}

export function AgentWorkbenchView({ session }: { session: Session }) {
  const actorEmail = session.user.email;
  const [workspaces, setWorkspaces] = useState<WorkspaceRecord[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState("");
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [repositories, setRepositories] = useState<GitRepositoryRecord[]>([]);
  const [selectedRepositoryId, setSelectedRepositoryId] = useState("");
  const [runs, setRuns] = useState<AgentRunRecord[]>([]);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [statusFilter, setStatusFilter] = useState<AgentRunStatus | "all">("all");
  const [detail, setDetail] = useState<AgentExecutionDetailRecord | null>(null);
  const [goal, setGoal] = useState("Generate refund audit candidate cases with observability");
  const [ref, setRef] = useState("master");
  const [candidateLimit, setCandidateLimit] = useState(3);
  const [maxToolCalls, setMaxToolCalls] = useState(60);
  const [maxSubagents, setMaxSubagents] = useState(4);
  const [maxParallelSubagents, setMaxParallelSubagents] = useState(3);
  const [maxModelCalls, setMaxModelCalls] = useState(20);
  const [maxWallMinutes, setMaxWallMinutes] = useState(20);
  const [maxSourceChars, setMaxSourceChars] = useState(200000);
  const [resumeReason, setResumeReason] = useState("Continue with expanded budget");
  const [policyMaxToolCalls, setPolicyMaxToolCalls] = useState(60);
  const [policyMaxModelCalls, setPolicyMaxModelCalls] = useState(20);
  const [policyMaxSubagents, setPolicyMaxSubagents] = useState(4);
  const [memoryQuery, setMemoryQuery] = useState("refund audit");
  const [memoryContent, setMemoryContent] = useState("# Project Memory\n\n");
  const [memoryResults, setMemoryResults] = useState<AgentMemorySearchResult[]>([]);
  const [selectedMemoryFile, setSelectedMemoryFile] = useState<AgentMemoryFileRecord | null>(null);
  const [memoryVersions, setMemoryVersions] = useState<AgentMemoryVersionRecord[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const runsPagination = usePagination(runs, 8);

  const selectedProject = projects.find((project) => project.id === selectedProjectId);
  const selectedRepository = repositories.find((repository) => repository.id === selectedRepositoryId);
  const selectedRun = runs.find((run) => run.id === selectedRunId) ?? detail?.run ?? null;
  const budgetUsage = (detail?.budget.usage ?? selectedRun?.budget_snapshot.usage ?? {}) as Record<string, unknown>;
  const budgetLimits = (detail?.budget.limits ?? selectedRun?.budget_snapshot.limits ?? {}) as Record<string, unknown>;
  const subagentPlan = (detail?.budget.snapshot.subagent_plan ?? selectedRun?.budget_snapshot.subagent_plan ?? {}) as Record<string, unknown>;
  const selectedSubagents = Array.isArray(subagentPlan.selected) ? subagentPlan.selected.map((item) => String(item)) : [];
  const parallelGroups = Array.isArray(subagentPlan.parallel_groups) ? subagentPlan.parallel_groups : [];
  const skippedSubagents = Array.isArray(subagentPlan.skipped_subagents) ? subagentPlan.skipped_subagents : [];
  const subagentRuns = detail?.subagent_runs ?? [];
  const temporalChildResultsSource = detail?.budget.snapshot.temporal_child_results ?? selectedRun?.budget_snapshot.temporal_child_results;
  const temporalChildResults = Array.isArray(temporalChildResultsSource)
    ? temporalChildResultsSource.filter((item): item is Record<string, unknown> => item !== null && typeof item === "object")
    : [];
  const subagentResultsSource = detail?.budget.snapshot.subagent_results ?? selectedRun?.budget_snapshot.subagent_results;
  const subagentResultEntries =
    subagentResultsSource && typeof subagentResultsSource === "object" && !Array.isArray(subagentResultsSource)
      ? Object.entries(subagentResultsSource as Record<string, unknown>).filter((entry): entry is [string, Record<string, unknown>] => {
          const value = entry[1];
          return value !== null && typeof value === "object" && !Array.isArray(value);
        })
      : [];

  const evidenceItems = useMemo(() => {
    return (detail?.staged_outputs ?? []).flatMap((output) =>
      output.evidence_refs.map((refItem, index) => ({
        id: `${output.id}:${index}`,
        outputTitle: output.title,
        kind: shortJson(refItem.kind),
        label: evidenceLabel(refItem),
        confidence: refItem.confidence,
        source: refItem.source
      }))
    );
  }, [detail]);

  const coverageItems = useMemo(() => {
    return (detail?.staged_outputs ?? []).flatMap((output) =>
      output.coverage_entries.map((entry) => ({
        ...entry,
        outputTitle: output.title
      }))
    );
  }, [detail]);

  const timeline = useMemo(() => {
    if (!detail) return [];
    return [
      ...detail.subagent_runs.map((item) => ({
        id: item.id,
        at: item.started_at ?? item.created_at,
        title: `${item.subagent_name} · ${item.stage}`,
        status: item.status,
        body: item.output_summary || item.error_summary || item.summary || item.input_summary
      })),
      ...detail.tool_calls.map((item) => ({
        id: item.id,
        at: item.created_at,
        title: `${item.subagent_name || "Supervisor"} · ${item.tool_name}`,
        status: item.status,
        body: item.output_summary || item.error_summary || item.input_summary
      })),
      ...detail.ai_invocations.map((item) => ({
        id: item.id,
        at: item.created_at,
        title: `${item.subagent_name || "Model"} · ${item.model_alias}`,
        status: item.status,
        body: `${item.prompt_version || "prompt"} · ${item.prompt_hash ? item.prompt_hash.slice(0, 12) : "no hash"}`
      }))
    ].sort((left, right) => new Date(left.at).getTime() - new Date(right.at).getTime());
  }, [detail]);

  async function refreshRuns(workspaceId: string, projectId: string, preferredRunId?: string) {
    if (!workspaceId) return;
    const nextRuns = await listAgentRuns(workspaceId, {
      projectId: projectId || undefined,
      status: statusFilter === "all" ? undefined : statusFilter
    });
    setRuns(nextRuns);
    const nextRunId = preferredRunId || selectedRunId || nextRuns[0]?.id || "";
    setSelectedRunId(nextRunId);
    if (nextRunId) {
      setDetail(await getAgentExecutionDetail(workspaceId, nextRunId));
    } else {
      setDetail(null);
    }
  }

  async function refreshProject(workspaceId: string, projectId: string, preferredRunId?: string) {
    const [nextRepositories] = await Promise.all([listRepositories(workspaceId, projectId || undefined)]);
    setRepositories(nextRepositories);
    setSelectedRepositoryId((current) => current || nextRepositories[0]?.id || "");
    await refreshRuns(workspaceId, projectId, preferredRunId);
  }

  async function refreshAll(preferredWorkspaceId?: string, preferredProjectId?: string, preferredRunId?: string) {
    setBusy(true);
    setMessage(null);
    try {
      const nextWorkspaces = await listWorkspaces(actorEmail);
      setWorkspaces(nextWorkspaces);
      const workspaceId = preferredWorkspaceId || selectedWorkspaceId || nextWorkspaces[0]?.id || "";
      setSelectedWorkspaceId(workspaceId);
      if (!workspaceId) return;
      const nextProjects = await listProjects(workspaceId);
      setProjects(nextProjects);
      const projectId = preferredProjectId || selectedProjectId || nextProjects[0]?.id || "";
      setSelectedProjectId(projectId);
      await refreshProject(workspaceId, projectId, preferredRunId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Agent 数据加载失败");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void refreshAll();
  }, []);

  async function handleWorkspaceSwitch(workspaceId: string) {
    setSelectedWorkspaceId(workspaceId);
    setMemoryResults([]);
    setSelectedMemoryFile(null);
    setMemoryVersions([]);
    await refreshAll(workspaceId);
  }

  async function handleProjectSwitch(projectId: string) {
    setSelectedProjectId(projectId);
    setMemoryResults([]);
    setSelectedMemoryFile(null);
    setMemoryVersions([]);
    if (!selectedWorkspaceId) return;
    setBusy(true);
    setMessage(null);
    try {
      await refreshProject(selectedWorkspaceId, projectId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Project 切换失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleSelectRun(runId: string) {
    setSelectedRunId(runId);
    if (!selectedWorkspaceId || !runId) return;
    setBusy(true);
    setMessage(null);
    try {
      setDetail(await getAgentExecutionDetail(selectedWorkspaceId, runId));
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Run detail 加载失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleLaunch() {
    if (!selectedWorkspaceId || !selectedProjectId || !selectedRepositoryId || !goal.trim()) return;
    setBusy(true);
    setMessage(null);
    try {
      const conversation = await createAgentConversation(selectedWorkspaceId, actorEmail, {
        title: goal.slice(0, 120),
        project_id: selectedProjectId
      });
      const run = await createAgentRun(selectedWorkspaceId, conversation.id, actorEmail, {
        goal,
        mode: "execute",
        project_id: selectedProjectId,
        budget_snapshot: {
          max_tool_calls: maxToolCalls,
          max_subagents: maxSubagents,
          max_parallel_subagents: maxParallelSubagents,
          max_model_calls: maxModelCalls,
          max_wall_time_minutes: maxWallMinutes,
          max_total_source_chars_sent: maxSourceChars,
          max_case_candidates_per_run: candidateLimit
        }
      });
      const executed = await executeAgentRun(selectedWorkspaceId, run.id, actorEmail, {
        repository_id: selectedRepositoryId,
        ref,
        candidate_limit: candidateLimit
      });
      setMessage(executed.summary);
      await refreshRuns(selectedWorkspaceId, selectedProjectId, executed.run.id);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Agent run 启动失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleResume() {
    if (!selectedWorkspaceId || !selectedRun) return;
    setBusy(true);
    setMessage(null);
    try {
      const resumed = await resumeAgentRun(selectedWorkspaceId, selectedRun.id, actorEmail, {
        budget_snapshot: {
          max_tool_calls: maxToolCalls,
          max_subagents: maxSubagents,
          max_parallel_subagents: maxParallelSubagents,
          max_model_calls: maxModelCalls,
          max_wall_time_minutes: maxWallMinutes,
          max_total_source_chars_sent: maxSourceChars,
          max_case_candidates_per_run: candidateLimit
        },
        resume_reason: resumeReason
      });
      setMessage(resumed.summary);
      await refreshRuns(selectedWorkspaceId, selectedProjectId, selectedRun.id);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Agent run resume 失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleCancel() {
    if (!selectedWorkspaceId || !selectedRun) return;
    setBusy(true);
    setMessage(null);
    try {
      const cancelled = await cancelAgentRun(selectedWorkspaceId, selectedRun.id, actorEmail, "Cancelled from Agent Workbench");
      setMessage(`已取消：${cancelled.id.slice(0, 8)}`);
      await refreshRuns(selectedWorkspaceId, selectedProjectId, selectedRun.id);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Agent run cancel 失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleOutputDecision(output: AgentStagedOutputRecord, status: "accepted" | "rejected") {
    if (!selectedWorkspaceId || !selectedRun) return;
    setBusy(true);
    setMessage(null);
    try {
      await decideAgentStagedOutput(selectedWorkspaceId, output.id, actorEmail, {
        status,
        decision_summary: `${status} from Agent Workbench`
      });
      await refreshRuns(selectedWorkspaceId, selectedProjectId, selectedRun.id);
      setMessage(status === "accepted" ? "已采纳 staged output" : "已拒绝 staged output");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Staged output 更新失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleApprovalDecision(approvalId: string, status: "approved" | "rejected") {
    if (!selectedWorkspaceId || !selectedRun) return;
    setBusy(true);
    setMessage(null);
    try {
      await decideAgentApproval(selectedWorkspaceId, approvalId, actorEmail, {
        status,
        decision_summary: `${status} from Agent Workbench`
      });
      await refreshRuns(selectedWorkspaceId, selectedProjectId, selectedRun.id);
      setMessage(status === "approved" ? "已批准 pending approval" : "已拒绝 pending approval");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Approval 更新失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveBudgetPolicy() {
    if (!selectedWorkspaceId || !selectedProjectId) return;
    setBusy(true);
    setMessage(null);
    try {
      const policy = await upsertAgentBudgetPolicy(selectedWorkspaceId, actorEmail, {
        scope: "project",
        project_id: selectedProjectId,
        defaults: {
          max_tool_calls: policyMaxToolCalls,
          max_model_calls: policyMaxModelCalls,
          max_subagents: policyMaxSubagents
        },
        hard_caps: {}
      });
      setMessage(`已保存预算默认值：${policy.scope}`);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "预算默认值保存失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleMemorySearch() {
    if (!selectedWorkspaceId) return;
    setBusy(true);
    setMessage(null);
    try {
      const results = await searchAgentMemory(selectedWorkspaceId, {
        projectId: selectedProjectId || undefined,
        query: memoryQuery,
        limit: 5
      });
      setMemoryResults(results);
      if (!selectedMemoryFile && results[0]?.memory_file) {
        await loadMemoryVersions(results[0].memory_file, selectedWorkspaceId);
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Memory search 失败");
    } finally {
      setBusy(false);
    }
  }

  async function loadMemoryVersions(memoryFile: AgentMemoryFileRecord, workspaceId = selectedWorkspaceId) {
    if (!workspaceId) return;
    const versions = await listAgentMemoryVersions(workspaceId, memoryFile.id);
    setSelectedMemoryFile(memoryFile);
    setMemoryVersions(versions);
  }

  async function handleCurateMemory() {
    if (!selectedWorkspaceId || !selectedProjectId || !memoryContent.trim()) return;
    setBusy(true);
    setMessage(null);
    try {
      const file = await curateAgentMemory(selectedWorkspaceId, actorEmail, {
        scope: "project",
        project_id: selectedProjectId,
        content: memoryContent,
        reason: "agent_workbench_curator",
        patch_summary: "Updated from Agent Workbench"
      });
      setMessage(`Memory v${file.current_version} 已保存`);
      await loadMemoryVersions(file, selectedWorkspaceId);
      await handleMemorySearch();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Memory curator 保存失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleMemoryVersionSelect(memoryFile: AgentMemoryFileRecord) {
    if (!selectedWorkspaceId) return;
    setBusy(true);
    setMessage(null);
    try {
      await loadMemoryVersions(memoryFile);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Memory version 加载失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleMemoryRollback(version: number) {
    if (!selectedWorkspaceId || !selectedMemoryFile) return;
    setBusy(true);
    setMessage(null);
    try {
      const rolledBack = await rollbackAgentMemory(selectedWorkspaceId, selectedMemoryFile.id, actorEmail, {
        target_version: version,
        reason: `Rollback to v${version} from Agent Workbench`
      });
      await loadMemoryVersions(rolledBack, selectedWorkspaceId);
      await handleMemorySearch();
      setMessage(`Memory 已回滚到 v${version}，当前为 v${rolledBack.current_version}`);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Memory rollback 失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleFilteredRefresh(nextStatus: AgentRunStatus | "all") {
    setStatusFilter(nextStatus);
    if (!selectedWorkspaceId) return;
    setBusy(true);
    setMessage(null);
    try {
      const nextRuns = await listAgentRuns(selectedWorkspaceId, {
        projectId: selectedProjectId || undefined,
        status: nextStatus === "all" ? undefined : nextStatus
      });
      setRuns(nextRuns);
      const nextRunId = nextRuns[0]?.id || "";
      setSelectedRunId(nextRunId);
      setDetail(nextRunId ? await getAgentExecutionDetail(selectedWorkspaceId, nextRunId) : null);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Run 列表刷新失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="section-block agent-workbench">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Agent Runs</span>
          <h2>Agent Workbench</h2>
        </div>
        <Bot size={20} aria-hidden="true" />
      </div>
      <div className="admin-body">
        {message ? <div className="inline-notice">{message}</div> : null}

        <div className="admin-toolbar agent-toolbar">
          <label className="select-label">
            Workspace
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
            Project
            <select value={selectedProjectId} onChange={(event) => void handleProjectSwitch(event.target.value)} disabled={busy || projects.length === 0}>
              <option value="">未选择</option>
              {projects.map((project) => (
                <option value={project.id} key={project.id}>
                  {project.key} · {project.name}
                </option>
              ))}
            </select>
          </label>
          <button className="icon-button" type="button" onClick={() => void refreshAll()} title="刷新 Agent Workbench" disabled={busy}>
            <RefreshCcw size={18} aria-hidden="true" />
          </button>
        </div>

        <div className="agent-shell">
          <section className="agent-launch-pane" aria-label="Agent run launcher">
            <div className="pane-heading">
              <div>
                <span className="eyebrow">Launch</span>
                <h3>新建执行</h3>
              </div>
              <Play size={18} aria-hidden="true" />
            </div>
            <div className="stack-form">
              <label>
                Goal
                <textarea value={goal} onChange={(event) => setGoal(event.target.value)} rows={4} />
              </label>
              <label>
                Repository
                <select value={selectedRepositoryId} onChange={(event) => setSelectedRepositoryId(event.target.value)} disabled={busy || repositories.length === 0}>
                  <option value="">未选择</option>
                  {repositories.map((repository) => (
                    <option value={repository.id} key={repository.id}>
                      {repository.name} · {repository.status}
                    </option>
                  ))}
                </select>
              </label>
              <div className="agent-number-grid">
                <label>
                  Ref
                  <input value={ref} onChange={(event) => setRef(event.target.value)} />
                </label>
                <label>
                  Candidates
                  <input type="number" min={1} max={5} value={candidateLimit} onChange={(event) => setCandidateLimit(numberValue(event.target.value, 3))} />
                </label>
              </div>
              <details className="agent-advanced">
                <summary>高级参数（预算 / 并发 / 上下文）</summary>
                <div className="agent-number-grid">
                  <label>
                    Tool calls
                    <input type="number" min={0} value={maxToolCalls} onChange={(event) => setMaxToolCalls(numberValue(event.target.value, 60))} />
                  </label>
                  <label>
                    Subagents
                    <input type="number" min={0} value={maxSubagents} onChange={(event) => setMaxSubagents(numberValue(event.target.value, 4))} />
                  </label>
                </div>
                <div className="agent-number-grid">
                  <label>
                    Parallel
                    <input type="number" min={1} value={maxParallelSubagents} onChange={(event) => setMaxParallelSubagents(numberValue(event.target.value, 3))} />
                  </label>
                  <label>
                    Model calls
                    <input type="number" min={0} value={maxModelCalls} onChange={(event) => setMaxModelCalls(numberValue(event.target.value, 20))} />
                  </label>
                </div>
                <div className="agent-number-grid">
                  <label>
                    Wall minutes
                    <input type="number" min={1} value={maxWallMinutes} onChange={(event) => setMaxWallMinutes(numberValue(event.target.value, 20))} />
                  </label>
                  <label>
                    Source chars
                    <input type="number" min={0} value={maxSourceChars} onChange={(event) => setMaxSourceChars(numberValue(event.target.value, 200000))} />
                  </label>
                </div>
              </details>
              <button className="primary-button small" type="button" onClick={() => void handleLaunch()} disabled={busy || !selectedRepositoryId || !selectedProjectId}>
                <Play size={16} aria-hidden="true" />
                启动
              </button>
            </div>
            <details className="agent-advanced agent-policy-box">
              <summary>项目预算默认值（保存后影响后续 Run）</summary>
              <div className="agent-number-grid">
                <label>
                  Tool calls
                  <input type="number" min={0} value={policyMaxToolCalls} onChange={(event) => setPolicyMaxToolCalls(numberValue(event.target.value, 60))} />
                </label>
                <label>
                  Model calls
                  <input type="number" min={0} value={policyMaxModelCalls} onChange={(event) => setPolicyMaxModelCalls(numberValue(event.target.value, 20))} />
                </label>
              </div>
              <label>
                Subagents
                <input type="number" min={0} value={policyMaxSubagents} onChange={(event) => setPolicyMaxSubagents(numberValue(event.target.value, 4))} />
              </label>
              <button className="ghost-button" type="button" onClick={() => void handleSaveBudgetPolicy()} disabled={busy || !selectedProjectId}>
                <Save size={16} aria-hidden="true" />
                保存
              </button>
            </details>
          </section>

          <section className="agent-run-list" aria-label="Agent run list">
            <div className="pane-heading">
              <div>
                <span className="eyebrow">Runs</span>
                <h3>{selectedProject ? `${selectedProject.key} · ${runs.length}` : `${runs.length} runs`}</h3>
              </div>
              <GitBranch size={18} aria-hidden="true" />
            </div>
            <div className="agent-status-filter" role="tablist" aria-label="Run status filter">
              {runStatuses.map((status) => (
                <button
                  className={statusFilter === status ? "status-filter active" : "status-filter"}
                  key={status}
                  type="button"
                  onClick={() => void handleFilteredRefresh(status)}
                >
                  {status === "all" ? "全部" : statusLabel[status]}
                </button>
              ))}
            </div>
            <div className="data-list agent-runs">
              {runsPagination.currentItems.map((run) => (
                <button
                  className={selectedRunId === run.id ? "agent-run-row active" : "agent-run-row"}
                  key={run.id}
                  type="button"
                  onClick={() => void handleSelectRun(run.id)}
                >
                  <strong>{run.goal}</strong>
                  <span>{statusLabel[run.status] ?? run.status} · {run.current_phase} · {formatDate(run.created_at)}</span>
                  <small>{run.temporal_workflow_id || run.langgraph_thread_id || run.id}</small>
                </button>
              ))}
              {runs.length === 0 ? <p className="empty-state">暂无 Agent run</p> : null}
            </div>
            <Pagination
              currentPage={runsPagination.currentPage}
              totalPages={runsPagination.totalPages}
              totalItems={runsPagination.totalItems}
              onPageChange={runsPagination.goToPage}
              itemsPerPage={8}
            />
          </section>

          <section className="agent-detail-pane" aria-label="Agent run detail">
            <div className="agent-detail-head">
              <div>
                <span className="eyebrow">Detail</span>
                <h3>{selectedRun?.goal ?? "未选择 Run"}</h3>
                <p>{selectedRepository ? `${selectedRepository.name} · ${ref || selectedRepository.default_branch}` : "Repository"}</p>
              </div>
              {selectedRun ? <StatusPill status={selectedRun.status} /> : null}
            </div>

            {selectedRun ? (
              <>
                <div className="agent-run-actions">
                  <button className="ghost-button" type="button" onClick={() => void handleSelectRun(selectedRun.id)} disabled={busy}>
                    <RefreshCcw size={16} aria-hidden="true" />
                    刷新
                  </button>
                  <button
                    className="ghost-button"
                    type="button"
                    onClick={() => void handleResume()}
                    disabled={busy || !["waiting_for_user", "failed"].includes(selectedRun.status)}
                  >
                    <RotateCcw size={16} aria-hidden="true" />
                    Resume
                  </button>
                  <button
                    className="ghost-button"
                    type="button"
                    onClick={() => void handleCancel()}
                    disabled={busy || ["succeeded", "failed", "cancelled"].includes(selectedRun.status)}
                  >
                    <CircleStop size={16} aria-hidden="true" />
                    Cancel
                  </button>
                </div>

                <div className="stack-form resume-strip">
                  <label>
                    Resume reason
                    <input value={resumeReason} onChange={(event) => setResumeReason(event.target.value)} />
                  </label>
                </div>

                <div className="agent-metric-grid">
                  <div className="metric-card compact">
                    <span>Tool calls</span>
                    <strong>{shortJson(budgetUsage.tool_calls)} / {shortJson(budgetLimits.max_tool_calls)}</strong>
                  </div>
                  <div className="metric-card compact">
                    <span>Subagents</span>
                    <strong>{shortJson(budgetUsage.subagents)} / {shortJson(budgetLimits.max_subagents)}</strong>
                  </div>
                  <div className="metric-card compact">
                    <span>Parallel</span>
                    <strong>{shortJson(budgetUsage.parallel_subagents)} / {shortJson(budgetLimits.max_parallel_subagents)}</strong>
                  </div>
                  <div className="metric-card compact">
                    <span>Model calls</span>
                    <strong>{shortJson(budgetUsage.model_calls)} / {shortJson(budgetLimits.max_model_calls)}</strong>
                  </div>
                  <div className="metric-card compact">
                    <span>Source chars</span>
                    <strong>{shortJson(budgetUsage.source_chars_sent)} / {shortJson(budgetLimits.max_total_source_chars_sent)}</strong>
                  </div>
                </div>

                {selectedRun.failure_reason ? (
                  <div className="inline-notice agent-warning">{selectedRun.failure_reason}</div>
                ) : null}

                {detail?.pending_approvals.length ? (
                  <section className="audit-pane" aria-label="Pending approvals">
                    <div className="pane-heading">
                      <div>
                        <span className="eyebrow">Approvals</span>
                        <h3>{detail.pending_approvals.length} pending</h3>
                      </div>
                      <ClipboardCheck size={18} aria-hidden="true" />
                    </div>
                    <div className="agent-output-grid">
                      {detail.pending_approvals.map((approval) => (
                        <article className="agent-approval-card" key={approval.id}>
                          <div>
                            <strong>{approval.approval_type}</strong>
                            <span>{approval.request_summary}</span>
                            <small>{approval.requested_by} · {formatDate(approval.created_at)}</small>
                          </div>
                          <div className="agent-run-actions">
                            <button className="ghost-button" type="button" onClick={() => void handleApprovalDecision(approval.id, "approved")} disabled={busy}>
                              <Check size={16} aria-hidden="true" />
                              批准
                            </button>
                            <button className="ghost-button" type="button" onClick={() => void handleApprovalDecision(approval.id, "rejected")} disabled={busy}>
                              <X size={16} aria-hidden="true" />
                              拒绝
                            </button>
                          </div>
                        </article>
                      ))}
                    </div>
                  </section>
                ) : null}

                <div className="agent-detail-grid">
                  <section className="execution-card">
                    <div className="pane-heading">
                      <div>
                        <span className="eyebrow">Subagents</span>
                        <h3>{shortJson(subagentPlan.selection_policy || "not planned")}</h3>
                      </div>
                      <Boxes size={18} aria-hidden="true" />
                    </div>
                    <div className="agent-chip-row">
                      {selectedSubagents.map((name) => (
                        <span className="agent-chip" key={name}>{name}</span>
                      ))}
                      {selectedSubagents.length === 0 ? <p className="empty-state">暂无 subagent plan</p> : null}
                    </div>
                    <small>{parallelGroups.map((group) => Array.isArray(group) ? group.join(" + ") : shortJson(group)).join(" / ") || "no parallel groups"}</small>
                    {skippedSubagents.length > 0 ? <small>Skipped: {skippedSubagents.map((item) => shortJson(item)).join(" · ")}</small> : null}
                    {subagentRuns.length > 0 ? (
                      <div className="child-workflow-list">
                        {subagentRuns.map((item) => (
                          <div className="child-workflow-row" key={item.id}>
                            <span>{item.status}</span>
                            <div>
                              <strong>{item.subagent_name} · {item.stage}</strong>
                              <small>{[item.parallel_group, item.output_summary || item.error_summary || item.summary, `${item.duration_ms}ms`].filter(Boolean).join(" · ")}</small>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : null}
                    {temporalChildResults.length > 0 ? (
                      <div className="child-workflow-list">
                        {temporalChildResults.map((item, index) => {
                          const stats = childWorkflowStats(item);
                          return (
                            <div className="child-workflow-row" key={`${shortJson(item.workflow_id)}-${index}`}>
                              <span>{shortJson(item.status)}</span>
                              <div>
                                <strong>{shortJson(item.task_kind)}</strong>
                                <small>{[shortJson(item.summary), stats, shortJson(item.workflow_id)].filter(Boolean).join(" · ")}</small>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    ) : null}
                    {subagentResultEntries.length > 0 ? (
                      <div className="child-workflow-list">
                        {subagentResultEntries.map(([name, item]) => (
                          <div className="child-workflow-row" key={name}>
                            <span>{shortJson(item.source || "run")}</span>
                            <div>
                              <strong>{name}</strong>
                              <small>{shortJson(item.summary || childWorkflowStats({ metadata: item }) || item)}</small>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </section>

                  <section className="execution-card">
                    <div className="pane-heading">
                      <div>
                        <span className="eyebrow">Timeline</span>
                        <h3>工具和模型调用</h3>
                      </div>
                      <Boxes size={18} aria-hidden="true" />
                    </div>
                    <div className="agent-timeline">
                      {timeline.map((item) => (
                        <div className="audit-row" key={item.id}>
                          <span>{statusLabel[item.status] ?? item.status}</span>
                          <div>
                            <strong>{item.title}</strong>
                            <small>{formatDate(item.at)} · {item.body}</small>
                          </div>
                        </div>
                      ))}
                      {timeline.length === 0 ? <p className="empty-state">暂无调用记录</p> : null}
                    </div>
                  </section>

                  <section className="execution-card">
                    <div className="pane-heading">
                      <div>
                        <span className="eyebrow">Sandbox</span>
                        <h3>仓库沙箱</h3>
                      </div>
                      <GitBranch size={18} aria-hidden="true" />
                    </div>
                    {detail?.repository_sandboxes.map((sandbox) => (
                      <div className="execution-card compact-card" key={sandbox.id}>
                        <strong>{sandbox.ref} · {statusLabel[sandbox.status] ?? sandbox.status}</strong>
                        <span>{sandbox.resolved_ref || "unresolved"}</span>
                        <small>{sandbox.error_summary || sandbox.worktree_path}</small>
                      </div>
                    ))}
                    {detail?.repository_sandboxes.length === 0 ? <p className="empty-state">暂无沙箱记录</p> : null}
                  </section>
                </div>

                <section className="audit-pane" aria-label="Evidence and coverage">
                  <div className="pane-heading">
                    <div>
                      <span className="eyebrow">Evidence</span>
                      <h3>证据与覆盖信号</h3>
                    </div>
                    <FileSearch size={18} aria-hidden="true" />
                  </div>
                  <div className="agent-evidence-grid">
                    <section className="execution-card">
                      <div className="pane-heading">
                        <div>
                          <span className="eyebrow">Evidence refs</span>
                          <h3>{evidenceItems.length} refs</h3>
                        </div>
                        <FileSearch size={16} aria-hidden="true" />
                      </div>
                      <div className="evidence-list">
                        {evidenceItems.map((item) => (
                          <div className="evidence-row" key={item.id}>
                            <span>{item.kind}</span>
                            <div>
                              <strong>{item.label}</strong>
                              <small>{item.outputTitle} · {shortJson(item.source)} · confidence {shortJson(item.confidence)}</small>
                            </div>
                          </div>
                        ))}
                        {evidenceItems.length === 0 ? <p className="empty-state">暂无 evidence ref</p> : null}
                      </div>
                    </section>

                    <section className="execution-card">
                      <div className="pane-heading">
                        <div>
                          <span className="eyebrow">Coverage</span>
                          <h3>{coverageItems.length} signals</h3>
                        </div>
                        <ListChecks size={16} aria-hidden="true" />
                      </div>
                      <div className="evidence-list">
                        {coverageItems.map((entry) => (
                          <div className="coverage-row" key={entry.id}>
                            <div>
                              <strong>{entry.module_key} · {entry.coverage_state}</strong>
                              <small>{entry.behavior_summary}</small>
                              <small>{entry.outputTitle} · confidence {entry.confidence} · {entry.verified_by_human ? "human verified" : "pending review"}</small>
                            </div>
                          </div>
                        ))}
                        {coverageItems.length === 0 ? <p className="empty-state">暂无 coverage signal</p> : null}
                      </div>
                    </section>
                  </div>
                </section>

                <section className="audit-pane" aria-label="Staged outputs">
                  <div className="pane-heading">
                    <div>
                      <span className="eyebrow">Staged Outputs</span>
                      <h3>审阅候选输出</h3>
                    </div>
                    <ClipboardCheck size={18} aria-hidden="true" />
                  </div>
                  <div className="agent-output-grid">
                    {detail?.staged_outputs.map((output) => (
                      <article className="agent-output-card" key={output.id}>
                        <div className="agent-output-head">
                          <div>
                            <strong>{output.title}</strong>
                            <span>{outputMeta(output)} · {statusLabel[output.status]}</span>
                          </div>
                          <StatusPill status={output.status} />
                        </div>
                        <p>{shortJson(output.payload.expected_result ?? output.payload.recommendation ?? output.payload.note_type)}</p>
                        <small>{output.evidence_refs.map((refItem) => shortJson(refItem.label ?? refItem.ref_id)).join(" · ") || "no evidence"}</small>
                        <div className="agent-run-actions">
                          <button className="ghost-button" type="button" onClick={() => void handleOutputDecision(output, "accepted")} disabled={busy || output.status !== "staged"}>
                            <Check size={16} aria-hidden="true" />
                            采纳
                          </button>
                          <button className="ghost-button" type="button" onClick={() => void handleOutputDecision(output, "rejected")} disabled={busy || output.status !== "staged"}>
                            <X size={16} aria-hidden="true" />
                            拒绝
                          </button>
                        </div>
                      </article>
                    ))}
                    {detail?.staged_outputs.length === 0 ? <p className="empty-state">暂无 staged output</p> : null}
                  </div>
                </section>
              </>
            ) : (
              <p className="empty-state">暂无选中 Run</p>
            )}
          </section>
        </div>

        <details className="agent-memory-panel agent-advanced" aria-label="Agent memory">
          <summary>项目记忆 / Memory Versions（按需展开）</summary>
          <div className="agent-memory-grid">
            <div className="stack-form">
              <label>
                Curated Markdown
                <textarea value={memoryContent} rows={6} onChange={(event) => setMemoryContent(event.target.value)} />
              </label>
              <button className="ghost-button" type="button" onClick={() => void handleCurateMemory()} disabled={busy || !selectedProjectId}>
                <Save size={16} aria-hidden="true" />
                保存记忆
              </button>
            </div>
            <div className="stack-form">
              <label>
                Search
                <input value={memoryQuery} onChange={(event) => setMemoryQuery(event.target.value)} />
              </label>
              <button className="ghost-button" type="button" onClick={() => void handleMemorySearch()} disabled={busy || !selectedWorkspaceId}>
                <Search size={16} aria-hidden="true" />
                搜索
              </button>
              <div className="agent-memory-results">
                {memoryResults.map((result) => (
                  <article className="compact-card execution-card" key={result.memory_file.id}>
                    <div className="agent-output-head">
                      <div>
                        <strong>{result.memory_file.scope} · v{result.memory_file.current_version}</strong>
                        <span>{result.snippet}</span>
                      </div>
                      <button className="ghost-button compact-action" type="button" onClick={() => void handleMemoryVersionSelect(result.memory_file)} disabled={busy}>
                        版本
                      </button>
                    </div>
                    <small>{result.memory_file.path}</small>
                  </article>
                ))}
                {memoryResults.length === 0 ? <p className="empty-state">暂无 memory result</p> : null}
              </div>
              <section className="execution-card memory-version-panel" aria-label="Memory version history">
                <div className="pane-heading">
                  <div>
                    <span className="eyebrow">Versions</span>
                    <h3>{selectedMemoryFile ? `${selectedMemoryFile.scope} · v${selectedMemoryFile.current_version}` : "未选择 memory"}</h3>
                  </div>
                  <RotateCcw size={16} aria-hidden="true" />
                </div>
                <div className="memory-version-list">
                  {memoryVersions.map((version) => (
                    <article className="memory-version-row" key={version.id}>
                      <div>
                        <strong>v{version.version} · {version.patch_summary || "memory update"}</strong>
                        <small>{formatDate(version.created_at)} · {version.editor || "system"} · {version.reason || "no reason"}</small>
                        <small>{version.checksum.slice(0, 12)}</small>
                      </div>
                      <button
                        className="ghost-button compact-action"
                        type="button"
                        onClick={() => void handleMemoryRollback(version.version)}
                        disabled={busy || !selectedMemoryFile || version.version === selectedMemoryFile.current_version}
                      >
                        回滚
                      </button>
                    </article>
                  ))}
                  {memoryVersions.length === 0 ? <p className="empty-state">暂无 version history</p> : null}
                </div>
              </section>
            </div>
          </div>
        </details>
      </div>
    </section>
  );
}
