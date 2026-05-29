import { useEffect, useMemo, useState } from "react";
import { 
  AlertCircle,
  Bot, 
  Boxes, 
  Brain,
  Check, 
  CircleStop, 
  ClipboardCheck, 
  Cpu,
  FileSearch, 
  GitBranch, 
  History,
  LayoutDashboard,
  ListChecks, 
  Play, 
  Plus,
  RefreshCcw, 
  RotateCcw, 
  Save, 
  Search, 
  ShieldCheck,
  X 
} from "lucide-react";
import { useParams } from "react-router-dom";
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
  listAgentMemoryVersions, 
  listAgentRuns, 
  rollbackAgentMemory, 
  resumeAgentRun, 
  searchAgentMemory, 
  upsertAgentBudgetPolicy 
} from "../api/agents";
import { GitRepositoryRecord, listRepositories } from "../api/git";
import { listProjects, listWorkspaces, ProjectRecord, WorkspaceRecord } from "../api/workspace";
import { useSessionStore } from "@/stores/session-store";
import { Pagination } from "../components/Pagination";
import { StatusPill } from "../components/StatusPill";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { usePagination } from "../hooks/usePagination";
import { statusLabel } from "../lib/labels";
import { pickExistingId } from "../lib/selection";
import { cn } from "@/lib/utils";

const runStatuses: Array<AgentRunStatus | "all"> = ["all", "queued", "running", "waiting_for_user", "succeeded", "failed", "cancelled"];

function formatDate(value: string | null) {
  if (!value) return "无";
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

function numberValue(value: unknown, fallback: number) {
  const next = Number(value);
  return Number.isFinite(next) ? next : fallback;
}

function shortJson(value: unknown) {
  if (value === null || value === undefined || value === "") return "无";
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

export function AgentWorkbenchView() {
  const session = useSessionStore((s) => s.session);
  const actorEmail = session?.user.email ?? "";
  const { wid: routeWorkspaceId = "", pid: routeProjectId = "" } = useParams<{ wid: string; pid: string }>();
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
  const [showLaunchForm, setShowLaunchForm] = useState(true);
  const [activeTab, setActiveTab] = useState<string>("overview");
  
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
    const nextRunId = pickExistingId(nextRuns, preferredRunId, selectedRunId);
    setSelectedRunId(nextRunId);
    if (nextRunId) {
      setDetail(await getAgentExecutionDetail(workspaceId, nextRunId));
      setShowLaunchForm(false);
    } else {
      setDetail(null);
      setShowLaunchForm(true);
    }
  }

  async function refreshProject(workspaceId: string, projectId: string, preferredRunId?: string) {
    const [nextRepositories] = await Promise.all([listRepositories(workspaceId, projectId || undefined)]);
    setRepositories(nextRepositories);
    setSelectedRepositoryId((current) => pickExistingId(nextRepositories, current, ""));
    await refreshRuns(workspaceId, projectId, preferredRunId);
  }

  async function refreshAll(preferredWorkspaceId?: string, preferredProjectId?: string, preferredRunId?: string) {
    setBusy(true);
    setMessage(null);
    try {
      const nextWorkspaces = await listWorkspaces(actorEmail);
      setWorkspaces(nextWorkspaces);
      const workspaceId = pickExistingId(nextWorkspaces, preferredWorkspaceId, selectedWorkspaceId);
      setSelectedWorkspaceId(workspaceId);
      if (!workspaceId) return;
      const nextProjects = await listProjects(workspaceId);
      setProjects(nextProjects);
      const projectId = pickExistingId(nextProjects, preferredProjectId, selectedProjectId);
      setSelectedProjectId(projectId);
      await refreshProject(workspaceId, projectId, preferredRunId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Agent 数据加载失败");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void refreshAll(routeWorkspaceId || undefined, routeProjectId || undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routeWorkspaceId, routeProjectId]);

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
    setShowLaunchForm(false);
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
      if (nextRunId) {
        setShowLaunchForm(false);
      } else {
        setShowLaunchForm(true);
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Run 列表刷新失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-6 min-w-0">
      {/* Page Title Header */}
      <div className="flex items-center justify-between border-b border-[var(--border)] pb-4 gap-4">
        <div>
          <h1 className="font-heading text-2xl font-bold tracking-tight">Agent 工作台</h1>
          <p className="text-xs text-[var(--muted-foreground)] mt-1">控制、配置和审阅 AI Agent 的异步运行，并管理项目的核心记忆库。</p>
        </div>
        <div className="p-2 rounded-xl bg-[var(--primary)]/10 text-[var(--primary)] shrink-0">
          <Bot size={24} aria-hidden="true" />
        </div>
      </div>

      {message ? (
        <Alert className="bg-[var(--accent)] border-[var(--primary)]/30">
          <AlertDescription className="text-xs font-medium">{message}</AlertDescription>
        </Alert>
      ) : null}

      <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-6 items-start">
        {/* Left Column: Selector & Running Runs History */}
        <div className="flex flex-col gap-4">
          {/* Select Scope Card */}
          <Card className="min-w-0 shadow-sm border-[var(--border)]">
            <CardHeader className="pb-3 border-b border-[var(--border)]/60">
              <CardTitle className="text-xs font-bold text-[var(--muted-foreground)] uppercase tracking-wider flex items-center gap-1.5">
                <Boxes size={14} className="text-[var(--primary)]" />
                范围选择
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-4 flex flex-col gap-3">
              <div className="flex flex-col gap-1.5">
                <Label className="text-xs font-semibold text-[var(--muted-foreground)]">Workspace</Label>
                <Select
                  value={selectedWorkspaceId || "__none__"}
                  onValueChange={(value) => void handleWorkspaceSwitch(value === "__none__" ? "" : value)}
                  disabled={busy || workspaces.length === 0}
                >
                  <SelectTrigger className="h-9 text-xs">
                    <SelectValue placeholder="未选择 Workspace" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__">未选择</SelectItem>
                    {workspaces.map((workspace) => (
                      <SelectItem value={workspace.id} key={workspace.id}>
                        {workspace.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label className="text-xs font-semibold text-[var(--muted-foreground)]">Project</Label>
                <Select
                  value={selectedProjectId || "__none__"}
                  onValueChange={(value) => void handleProjectSwitch(value === "__none__" ? "" : value)}
                  disabled={busy || projects.length === 0}
                >
                  <SelectTrigger className="h-9 text-xs">
                    <SelectValue placeholder="未选择 Project" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__">未选择</SelectItem>
                    {projects.map((project) => (
                      <SelectItem value={project.id} key={project.id}>
                        {project.key} · {project.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex gap-2 mt-1 pt-1 border-t border-[var(--border)]/40">
                <Button
                  className="flex-1 text-xs gap-1.5 h-9"
                  onClick={() => {
                    setShowLaunchForm(true);
                    setSelectedRunId("");
                    setDetail(null);
                  }}
                  disabled={busy || !selectedProjectId}
                >
                  <Plus size={14} />
                  新建执行
                </Button>
                <Button
                  variant="outline"
                  size="icon"
                  className="h-9 w-9 shrink-0"
                  onClick={() => void refreshAll()}
                  title="刷新工作台"
                  disabled={busy}
                >
                  <RefreshCcw size={14} />
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* Runs History List Card */}
          <Card className="min-w-0 flex flex-col flex-1 shadow-sm border-[var(--border)]" aria-label="Agent run list">
            <CardHeader className="flex flex-row items-center justify-between pb-3 border-b border-[var(--border)]/60">
              <CardTitle className="text-xs font-bold text-[var(--muted-foreground)] uppercase tracking-wider flex items-center gap-1.5">
                <History size={14} className="text-[var(--primary)]" />
                执行历史
              </CardTitle>
              {selectedProject && (
                <span className="text-[10px] font-bold bg-[var(--muted)] px-2 py-0.5 rounded-full text-[var(--muted-foreground)]">
                  {runs.length} Runs
                </span>
              )}
            </CardHeader>
            <CardContent className="pt-4 flex flex-col gap-3">
              {/* Status filter buttons */}
              <div className="flex flex-wrap gap-1" role="tablist" aria-label="Run status filter">
                {runStatuses.map((status) => (
                  <Button
                    key={status}
                    type="button"
                    size="sm"
                    variant={statusFilter === status ? "default" : "outline"}
                    className="text-[10px] px-2 py-0.5 h-7 rounded"
                    onClick={() => void handleFilteredRefresh(status)}
                  >
                    {status === "all" ? "全部" : statusLabel[status]}
                  </Button>
                ))}
              </div>

              {/* Items List */}
              <div className="rounded-lg border border-[var(--border)] overflow-hidden max-h-[420px] overflow-y-auto divide-y divide-[var(--border)]/60 bg-[var(--muted)]/5">
                {runsPagination.currentItems.map((run) => (
                  <button
                    className={cn(
                      "w-full text-left px-3.5 py-3 transition-colors hover:bg-[var(--muted)]/40 flex flex-col gap-1.5",
                      selectedRunId === run.id && !showLaunchForm && "bg-[var(--accent)] border-l-2 border-l-[var(--primary)]"
                    )}
                    key={run.id}
                    type="button"
                    onClick={() => void handleSelectRun(run.id)}
                  >
                    <strong className="text-xs font-semibold leading-relaxed line-clamp-2 text-[var(--foreground)]">{run.goal}</strong>
                    <div className="flex flex-col gap-0.5">
                      <div className="flex items-center justify-between text-[10px] text-[var(--muted-foreground)]">
                        <span className="font-semibold px-1.5 py-0.2 rounded bg-[var(--muted)] text-[var(--foreground)]">
                          {statusLabel[run.status] ?? run.status}
                        </span>
                        <span>{formatDate(run.created_at)}</span>
                      </div>
                      <span className="text-[9px] font-mono text-[var(--muted-foreground)] truncate mt-1">
                        {run.temporal_workflow_id || run.langgraph_thread_id || run.id}
                      </span>
                    </div>
                  </button>
                ))}
                {runs.length === 0 ? <p className="text-xs text-[var(--muted-foreground)] p-6 text-center">暂无匹配的运行记录</p> : null}
              </div>

              <Pagination
                currentPage={runsPagination.currentPage}
                totalPages={runsPagination.totalPages}
                totalItems={runsPagination.totalItems}
                onPageChange={runsPagination.goToPage}
                itemsPerPage={8}
              />
            </CardContent>
          </Card>
        </div>

        {/* Right Column: Main Content Area */}
        <div className="flex-1 min-w-0">
          {showLaunchForm ? (
            /* Launch Form View */
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
              {/* Basic Configuration */}
              <Card className="shadow-sm border-[var(--border)]">
                <CardHeader className="pb-3 border-b border-[var(--border)]/60 flex flex-row items-start justify-between gap-4">
                  <div>
                    <CardTitle className="text-base font-bold text-[var(--foreground)]">启动 Agent 执行</CardTitle>
                    <p className="text-xs text-[var(--muted-foreground)] mt-1">配置并初始化一个新的 AI Agent 运行流</p>
                  </div>
                  <div className="p-2 rounded-lg bg-[var(--primary)]/10 text-[var(--primary)]">
                    <Play size={16} />
                  </div>
                </CardHeader>
                <CardContent className="pt-5 flex flex-col gap-4">
                  <div className="flex flex-col gap-1.5">
                    <Label className="text-sm font-semibold text-[var(--foreground)]">目标 (Goal)</Label>
                    <Textarea 
                      value={goal} 
                      onChange={(event) => setGoal(event.target.value)} 
                      rows={5} 
                      placeholder="请详细描述本次运行的目标和要求..."
                      className="text-xs leading-relaxed"
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label className="text-sm font-semibold text-[var(--foreground)]">代码仓库 (Repository)</Label>
                    <Select 
                      value={selectedRepositoryId || "__none__"} 
                      onValueChange={(value) => setSelectedRepositoryId(value === "__none__" ? "" : value)} 
                      disabled={busy || repositories.length === 0}
                    >
                      <SelectTrigger className="text-xs">
                        <SelectValue placeholder="请选择关联的 Git 代码仓库" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__none__">未选择</SelectItem>
                        {repositories.map((repository) => (
                          <SelectItem value={repository.id} key={repository.id}>
                            {repository.name} · {repository.status}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="flex flex-col gap-1.5">
                      <Label className="text-sm font-semibold text-[var(--foreground)]">分支/提交 (Ref)</Label>
                      <Input value={ref} onChange={(event) => setRef(event.target.value)} className="text-xs font-mono h-9" />
                    </div>
                    <div className="flex flex-col gap-1.5">
                      <Label className="text-sm font-semibold text-[var(--foreground)]">推荐候选上限 (Candidates)</Label>
                      <Input 
                        type="number" 
                        min={1} 
                        max={5} 
                        value={candidateLimit} 
                        onChange={(event) => setCandidateLimit(numberValue(event.target.value, 3))} 
                        className="text-xs h-9"
                      />
                    </div>
                  </div>
                  <div className="pt-3 border-t border-[var(--border)]/40 mt-1">
                    <Button 
                      type="button" 
                      onClick={() => void handleLaunch()} 
                      disabled={busy || !selectedRepositoryId || !selectedProjectId} 
                      className="w-full sm:w-auto px-6 h-10 text-xs font-semibold gap-2"
                    >
                      <Play size={14} aria-hidden="true" />
                      启动异步运行
                    </Button>
                  </div>
                </CardContent>
              </Card>

              {/* Advanced Limits & Project Defaults */}
              <div className="flex flex-col gap-6">
                {/* Advanced parameters */}
                <Card className="shadow-sm border-[var(--border)]">
                  <CardHeader className="pb-3 border-b border-[var(--border)]/60">
                    <CardTitle className="text-sm font-bold text-[var(--foreground)]">微调参数限额与预算上限</CardTitle>
                    <p className="text-xs text-[var(--muted-foreground)] mt-0.5">控制执行并发数以及资源、工具的消耗门槛</p>
                  </CardHeader>
                  <CardContent className="pt-4 grid grid-cols-2 gap-4">
                    <div className="flex flex-col gap-1">
                      <Label className="text-[11px] font-semibold text-[var(--muted-foreground)] uppercase">Tool Calls Limit</Label>
                      <Input type="number" min={0} value={maxToolCalls} onChange={(event) => setMaxToolCalls(numberValue(event.target.value, 60))} className="h-8 text-xs font-mono" />
                    </div>
                    <div className="flex flex-col gap-1">
                      <Label className="text-[11px] font-semibold text-[var(--muted-foreground)] uppercase">Subagents Limit</Label>
                      <Input type="number" min={0} value={maxSubagents} onChange={(event) => setMaxSubagents(numberValue(event.target.value, 4))} className="h-8 text-xs font-mono" />
                    </div>
                    <div className="flex flex-col gap-1">
                      <Label className="text-[11px] font-semibold text-[var(--muted-foreground)] uppercase">Parallel Subagents</Label>
                      <Input type="number" min={1} value={maxParallelSubagents} onChange={(event) => setMaxParallelSubagents(numberValue(event.target.value, 3))} className="h-8 text-xs font-mono" />
                    </div>
                    <div className="flex flex-col gap-1">
                      <Label className="text-[11px] font-semibold text-[var(--muted-foreground)] uppercase">Model Calls Limit</Label>
                      <Input type="number" min={0} value={maxModelCalls} onChange={(event) => setMaxModelCalls(numberValue(event.target.value, 20))} className="h-8 text-xs font-mono" />
                    </div>
                    <div className="flex flex-col gap-1">
                      <Label className="text-[11px] font-semibold text-[var(--muted-foreground)] uppercase">Wall Time (Minutes)</Label>
                      <Input type="number" min={1} value={maxWallMinutes} onChange={(event) => setMaxWallMinutes(numberValue(event.target.value, 20))} className="h-8 text-xs font-mono" />
                    </div>
                    <div className="flex flex-col gap-1">
                      <Label className="text-[11px] font-semibold text-[var(--muted-foreground)] uppercase">Source Chars Limit</Label>
                      <Input type="number" min={0} value={maxSourceChars} onChange={(event) => setMaxSourceChars(numberValue(event.target.value, 200000))} className="h-8 text-xs font-mono" />
                    </div>
                  </CardContent>
                </Card>

                {/* Project Budget Default Settings */}
                <Card className="shadow-sm border-[var(--border)]">
                  <CardHeader className="pb-3 border-b border-[var(--border)]/60">
                    <CardTitle className="text-sm font-bold text-[var(--foreground)]">项目级预算默认策略</CardTitle>
                    <p className="text-xs text-[var(--muted-foreground)] mt-0.5">保存默认额度，这些数值将作为后续执行的初始推荐参数</p>
                  </CardHeader>
                  <CardContent className="pt-4 flex flex-col gap-3">
                    <div className="grid grid-cols-3 gap-3">
                      <div className="flex flex-col gap-1">
                        <Label className="text-[10px] font-bold text-[var(--muted-foreground)] uppercase">Tool Calls</Label>
                        <Input type="number" min={0} value={policyMaxToolCalls} onChange={(event) => setPolicyMaxToolCalls(numberValue(event.target.value, 60))} className="h-8 text-xs font-mono" />
                      </div>
                      <div className="flex flex-col gap-1">
                        <Label className="text-[10px] font-bold text-[var(--muted-foreground)] uppercase">Model Calls</Label>
                        <Input type="number" min={0} value={policyMaxModelCalls} onChange={(event) => setPolicyMaxModelCalls(numberValue(event.target.value, 20))} className="h-8 text-xs font-mono" />
                      </div>
                      <div className="flex flex-col gap-1">
                        <Label className="text-[10px] font-bold text-[var(--muted-foreground)] uppercase">Subagents</Label>
                        <Input type="number" min={0} value={policyMaxSubagents} onChange={(event) => setPolicyMaxSubagents(numberValue(event.target.value, 4))} className="h-8 text-xs font-mono" />
                      </div>
                    </div>
                    <Button 
                      variant="outline" 
                      size="sm" 
                      type="button" 
                      onClick={() => void handleSaveBudgetPolicy()} 
                      disabled={busy || !selectedProjectId} 
                      className="self-start gap-1 text-xs h-8 px-4 mt-1 border-[var(--border)]"
                    >
                      <Save size={12} />
                      保存默认配置
                    </Button>
                  </CardContent>
                </Card>
              </div>
            </div>
          ) : (
            /* Selected Run Detail & Tabs View */
            <div className="flex flex-col gap-4">
              {/* Summary Header Card */}
              <Card className="shadow-sm border-[var(--border)]">
                <CardContent className="p-5 flex flex-col gap-4">
                  <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        {selectedRun ? <StatusPill status={selectedRun.status} /> : null}
                        <span className="text-[10px] font-mono text-[var(--muted-foreground)]">
                          Workflow: {selectedRun?.temporal_workflow_id || selectedRun?.langgraph_thread_id || selectedRun?.id}
                        </span>
                      </div>
                      <h2 className="font-heading text-lg font-bold leading-relaxed text-[var(--foreground)] mt-2 line-clamp-3">
                        {selectedRun?.goal}
                      </h2>
                      <div className="flex items-center gap-2 mt-1.5 text-xs text-[var(--muted-foreground)]">
                        <span className="font-semibold text-[var(--foreground)]">Repository:</span>
                        <span>{selectedRepository ? `${selectedRepository.name} · ${ref || selectedRepository.default_branch}` : "N/A"}</span>
                        <span>·</span>
                        <span>创建于 {formatDate(selectedRun?.created_at ?? null)}</span>
                      </div>
                    </div>

                    {/* Action buttons */}
                    <div className="flex flex-wrap gap-2 shrink-0 md:pt-1">
                      <Button variant="outline" size="sm" type="button" onClick={() => void handleSelectRun(selectedRunId)} disabled={busy} className="h-8 text-xs gap-1">
                        <RefreshCcw size={12} />
                        刷新
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        type="button"
                        onClick={() => void handleResume()}
                        disabled={busy || !["waiting_for_user", "failed"].includes(selectedRun?.status ?? "")}
                        className="h-8 text-xs gap-1"
                      >
                        <RotateCcw size={12} />
                        恢复
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        type="button"
                        onClick={() => void handleCancel()}
                        disabled={busy || ["succeeded", "failed", "cancelled"].includes(selectedRun?.status ?? "")}
                        className="h-8 text-xs gap-1 hover:bg-destructive/10 hover:text-destructive"
                      >
                        <CircleStop size={12} />
                        取消
                      </Button>
                    </div>
                  </div>

                  {/* Resume Reason Input if waiting */}
                  {selectedRun && ["waiting_for_user", "failed"].includes(selectedRun.status) ? (
                    <div className="flex flex-col gap-1.5 bg-[var(--muted)]/20 p-3 rounded-lg border border-[var(--border)]/40 mt-1">
                      <Label className="text-xs font-semibold">恢复执行附加说明 (Resume reason)</Label>
                      <div className="flex gap-2">
                        <Input 
                          value={resumeReason} 
                          onChange={(event) => setResumeReason(event.target.value)} 
                          className="text-xs bg-[var(--card)] h-8"
                          placeholder="例如：已放宽限额、增加重试预算..."
                        />
                      </div>
                    </div>
                  ) : null}
                </CardContent>
              </Card>

              {/* Tabs Dashboard */}
              <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
                <TabsList className="grid grid-cols-3 md:grid-cols-6 h-auto p-1 bg-[var(--muted)]/40 border border-[var(--border)] rounded-xl">
                  <TabsTrigger value="overview" className="py-2.5 text-xs font-semibold gap-1.5 rounded-lg data-[state=active]:bg-[var(--card)] data-[state=active]:shadow-sm">
                    <LayoutDashboard size={13} />
                    运行看板
                  </TabsTrigger>
                  <TabsTrigger value="subagents" className="py-2.5 text-xs font-semibold gap-1.5 rounded-lg data-[state=active]:bg-[var(--card)] data-[state=active]:shadow-sm">
                    <Cpu size={13} />
                    子智能体
                  </TabsTrigger>
                  <TabsTrigger value="timeline" className="py-2.5 text-xs font-semibold gap-1.5 rounded-lg data-[state=active]:bg-[var(--card)] data-[state=active]:shadow-sm">
                    <History size={13} />
                    调用日志
                  </TabsTrigger>
                  <TabsTrigger value="evidence" className="py-2.5 text-xs font-semibold gap-1.5 rounded-lg data-[state=active]:bg-[var(--card)] data-[state=active]:shadow-sm">
                    <ShieldCheck size={13} />
                    证据与信号
                  </TabsTrigger>
                  <TabsTrigger value="outputs" className="py-2.5 text-xs font-semibold gap-1.5 rounded-lg data-[state=active]:bg-[var(--card)] data-[state=active]:shadow-sm">
                    <ClipboardCheck size={13} />
                    候选输出
                  </TabsTrigger>
                  <TabsTrigger value="memory" className="py-2.5 text-xs font-semibold gap-1.5 rounded-lg data-[state=active]:bg-[var(--card)] data-[state=active]:shadow-sm">
                    <Brain size={13} />
                    项目记忆
                  </TabsTrigger>
                </TabsList>

                {/* Tab: Overview (运行看板) */}
                <TabsContent value="overview" className="mt-4 flex flex-col gap-6 focus-visible:ring-0">
                  {/* Budget Usage Grid */}
                  <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                    {[
                      { label: "Tool Calls", usage: budgetUsage.tool_calls, limit: budgetLimits.max_tool_calls },
                      { label: "Subagents", usage: budgetUsage.subagents, limit: budgetLimits.max_subagents },
                      { label: "Parallel", usage: budgetUsage.parallel_subagents, limit: budgetLimits.max_parallel_subagents },
                      { label: "Model Calls", usage: budgetUsage.model_calls, limit: budgetLimits.max_model_calls },
                      { label: "Source Chars", usage: budgetUsage.source_chars_sent, limit: budgetLimits.max_total_source_chars_sent }
                    ].map((metric) => {
                      const val = numberValue(metric.usage, 0);
                      const lim = numberValue(metric.limit, 0);
                      const percentage = lim > 0 ? Math.min(100, Math.round((val / lim) * 100)) : 0;
                      return (
                        <div key={metric.label} className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-4 flex flex-col justify-between gap-3 shadow-sm hover:shadow transition-shadow">
                          <span className="text-[10px] font-bold uppercase text-[var(--muted-foreground)] tracking-wider line-clamp-1">{metric.label}</span>
                          <div className="flex flex-col">
                            <strong className="text-xl font-extrabold tracking-tight text-[var(--primary)]">
                              {shortJson(metric.usage)}
                            </strong>
                            <span className="text-[10px] text-[var(--muted-foreground)] font-mono mt-0.5">上限: {shortJson(metric.limit)}</span>
                            <div className="w-full bg-[var(--muted)] h-1.5 rounded-full mt-2.5 overflow-hidden">
                              <div className={cn(
                                "h-full rounded-full transition-all duration-300",
                                percentage > 90 ? "bg-destructive" : percentage > 70 ? "bg-yellow-500" : "bg-[var(--primary)]"
                              )} style={{ width: `${percentage}%` }}></div>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  {selectedRun?.failure_reason ? (
                    <Alert className="bg-destructive/10 border-destructive/20 text-destructive flex items-start gap-2">
                      <AlertCircle size={16} className="shrink-0 mt-0.5" />
                      <AlertDescription className="text-xs font-semibold leading-normal">{selectedRun.failure_reason}</AlertDescription>
                    </Alert>
                  ) : null}

                  {/* Sandboxes & Approvals Row */}
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    {/* Repository Sandbox Status */}
                    <Card className="shadow-sm border-[var(--border)]">
                      <CardHeader className="flex flex-row items-center justify-between pb-3 border-b border-[var(--border)]/40">
                        <div>
                          <CardTitle className="text-sm font-bold">虚拟沙箱 (Sandbox)</CardTitle>
                          <p className="text-xs text-[var(--muted-foreground)] mt-0.5">代码分支及编译的安全沙箱运行状态</p>
                        </div>
                        <GitBranch size={16} className="text-[var(--muted-foreground)]" />
                      </CardHeader>
                      <CardContent className="pt-4 flex flex-col gap-3">
                        {detail?.repository_sandboxes.map((sandbox) => (
                          <div className="rounded-lg border border-[var(--border)] bg-[var(--muted)]/20 p-3.5 flex flex-col gap-2 hover:bg-[var(--muted)]/30 transition-colors" key={sandbox.id}>
                            <div className="flex items-center justify-between gap-2 font-bold text-xs">
                              <span className="font-mono text-[var(--foreground)]">{sandbox.ref}</span>
                              <span className={cn(
                                "px-2 py-0.5 rounded-full text-[10px] font-semibold",
                                sandbox.status === "ready" && "bg-green-500/15 text-green-500",
                                sandbox.status === "failed" && "bg-destructive/15 text-destructive",
                                ["preparing"].includes(sandbox.status) && "bg-yellow-500/15 text-yellow-500"
                              )}>
                                {statusLabel[sandbox.status] ?? sandbox.status}
                              </span>
                            </div>
                            <span className="text-[10px] text-[var(--muted-foreground)] font-mono leading-none">Resolved Ref: {sandbox.resolved_ref || "unresolved"}</span>
                            <small className="text-[10px] text-[var(--muted-foreground)] break-all mt-1 leading-relaxed bg-[var(--card)] p-2.5 rounded border border-[var(--border)]/40 font-mono">
                              {sandbox.error_summary || sandbox.worktree_path}
                            </small>
                          </div>
                        ))}
                        {(!detail || detail.repository_sandboxes.length === 0) ? (
                          <p className="text-xs text-[var(--muted-foreground)] p-6 text-center">暂无关联的代码沙箱实例</p>
                        ) : null}
                      </CardContent>
                    </Card>

                    {/* Pending Approvals Section */}
                    <Card className="shadow-sm border-[var(--border)]">
                      <CardHeader className="flex flex-row items-center justify-between pb-3 border-b border-[var(--border)]/40">
                        <div>
                          <CardTitle className="text-sm font-bold">待批准决策 (Pending Approvals)</CardTitle>
                          <p className="text-xs text-[var(--muted-foreground)] mt-0.5">Agent 暂停运行并等待手动授权的动作</p>
                        </div>
                        <ClipboardCheck size={16} className="text-[var(--muted-foreground)]" />
                      </CardHeader>
                      <CardContent className="pt-4 flex flex-col gap-3">
                        {detail?.pending_approvals.map((approval) => (
                          <article className="rounded-lg border border-[var(--border)] p-4 flex flex-col gap-3 hover:bg-[var(--muted)]/10 transition-colors" key={approval.id}>
                            <div className="flex flex-col gap-1">
                              <strong className="text-xs font-bold text-[var(--primary)] uppercase tracking-wider">{approval.approval_type}</strong>
                              <span className="text-xs font-semibold leading-relaxed mt-1 text-[var(--foreground)]">{approval.request_summary}</span>
                              <div className="flex items-center gap-2 text-[10px] text-[var(--muted-foreground)] mt-1.5">
                                <span>申请人: {approval.requested_by}</span>
                                <span>·</span>
                                <span>{formatDate(approval.created_at)}</span>
                              </div>
                            </div>
                            <div className="flex flex-wrap gap-2 mt-1 pt-2 border-t border-[var(--border)]/40">
                              <Button variant="outline" size="sm" type="button" onClick={() => void handleApprovalDecision(approval.id, "approved")} disabled={busy} className="h-8 text-xs px-4 gap-1 border-green-500/30 text-green-500 hover:bg-green-500/10">
                                <Check size={12} />
                                批准通过
                              </Button>
                              <Button variant="outline" size="sm" type="button" onClick={() => void handleApprovalDecision(approval.id, "rejected")} disabled={busy} className="h-8 text-xs px-4 gap-1 border-destructive/30 text-destructive hover:bg-destructive/10">
                                <X size={12} />
                                拒绝申请
                              </Button>
                            </div>
                          </article>
                        ))}
                        {(!detail || detail.pending_approvals.length === 0) ? (
                          <div className="py-10 flex flex-col items-center justify-center text-center gap-2.5">
                            <div className="p-2.5 rounded-full bg-green-500/10 text-green-500">
                              <Check size={20} />
                            </div>
                            <p className="text-xs font-medium text-[var(--muted-foreground)]">暂无待审阅的批准决策，工作流无阻碍。</p>
                          </div>
                        ) : null}
                      </CardContent>
                    </Card>
                  </div>
                </TabsContent>

                {/* Tab: Subagents (子智能体) */}
                <TabsContent value="subagents" className="mt-4 flex flex-col gap-6 focus-visible:ring-0">
                  <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
                    {/* Subagent Plan & Budget Details (Left column) */}
                    <Card className="shadow-sm border-[var(--border)]">
                      <CardHeader className="pb-3 border-b border-[var(--border)]/40">
                        <CardTitle className="text-sm font-bold flex items-center gap-1.5">
                          <Boxes size={16} className="text-[var(--primary)]" />
                          规划策略 (Policy)
                        </CardTitle>
                      </CardHeader>
                      <CardContent className="pt-4 flex flex-col gap-4">
                        <div>
                          <Label className="text-xs font-bold text-[var(--muted-foreground)] block mb-1">选择策略</Label>
                          <span className="text-xs font-mono font-bold leading-normal text-[var(--foreground)]">{shortJson(subagentPlan.selection_policy || "未提供规划")}</span>
                        </div>
                        
                        <div>
                          <Label className="text-xs font-bold text-[var(--muted-foreground)] block mb-2">计划运行的 Subagents</Label>
                          <div className="flex flex-wrap gap-1.5">
                            {selectedSubagents.map((name) => (
                              <span className="text-xs font-semibold px-2.5 py-1 rounded-md bg-[var(--primary)]/10 text-[var(--primary)] border border-[var(--primary)]/15" key={name}>
                                {name}
                              </span>
                            ))}
                            {selectedSubagents.length === 0 ? <p className="text-xs text-[var(--muted-foreground)] leading-loose">未生成 Subagent 执行树规划</p> : null}
                          </div>
                        </div>

                        {parallelGroups.length > 0 && (
                          <div>
                            <Label className="text-xs font-bold text-[var(--muted-foreground)] block mb-1">并行分组 (Parallel Groups)</Label>
                            <p className="text-xs font-medium text-[var(--foreground)] leading-relaxed bg-[var(--muted)]/30 p-2 rounded border border-[var(--border)]/50">
                              {parallelGroups.map((group) => Array.isArray(group) ? group.join(" + ") : shortJson(group)).join(" / ")}
                            </p>
                          </div>
                        )}

                        {skippedSubagents.length > 0 && (
                          <div>
                            <Label className="text-xs font-bold text-[var(--muted-foreground)] block mb-1">跳过执行 (Skipped Subagents)</Label>
                            <div className="flex flex-wrap gap-1.5">
                              {skippedSubagents.map((item) => (
                                <span className="text-[10px] bg-[var(--muted)] text-[var(--muted-foreground)] px-2 py-0.5 rounded font-mono" key={shortJson(item)}>
                                  {shortJson(item)}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}
                      </CardContent>
                    </Card>

                    {/* Subagents Runs, Workflows, Results details (Right columns) */}
                    <div className="lg:col-span-2 flex flex-col gap-6">
                      {subagentRuns.length > 0 || temporalChildResults.length > 0 || subagentResultEntries.length > 0 ? (
                        <Card className="shadow-sm border-[var(--border)]">
                          <CardHeader className="pb-3 border-b border-[var(--border)]/40">
                            <CardTitle className="text-sm font-bold">执行流程详情与计算产物</CardTitle>
                          </CardHeader>
                          <CardContent className="pt-4 flex flex-col gap-5">
                            {/* Subagent Runs list */}
                            {subagentRuns.length > 0 && (
                              <div className="flex flex-col gap-2">
                                <h4 className="text-xs font-bold text-[var(--muted-foreground)] uppercase tracking-wider">Subagent Runs</h4>
                                <div className="rounded-lg border border-[var(--border)] divide-y divide-[var(--border)] overflow-hidden bg-[var(--muted)]/5">
                                  {subagentRuns.map((item) => (
                                    <div className="grid grid-cols-[100px_1fr_90px] gap-4 items-start p-3 hover:bg-[var(--muted)]/20 transition-colors" key={item.id}>
                                      <span className={cn(
                                        "font-bold text-[10px] px-1.5 py-0.5 rounded text-center leading-none mt-0.5 uppercase block w-fit",
                                        item.status === "succeeded" && "bg-green-500/10 text-green-500",
                                        item.status === "failed" && "bg-destructive/10 text-destructive",
                                        item.status === "running" && "bg-info/10 text-info",
                                        item.status === "queued" && "bg-yellow-500/10 text-yellow-500"
                                      )}>
                                        {item.status}
                                      </span>
                                      <div className="text-xs min-w-0">
                                        <strong className="text-sm font-bold text-[var(--foreground)]">{item.subagent_name}</strong>
                                        <span className="text-[10px] text-[var(--muted-foreground)] font-mono ml-2">({item.stage})</span>
                                        <p className="text-xs text-[var(--muted-foreground)] mt-1.5 leading-relaxed break-all bg-[var(--card)] p-2.5 rounded border border-[var(--border)]/50">
                                          {item.output_summary || item.error_summary || item.summary || item.input_summary}
                                        </p>
                                      </div>
                                      <span className="text-right text-xs font-mono text-[var(--muted-foreground)] mt-0.5">{item.duration_ms}ms</span>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}

                            {/* Temporal Child Workflows */}
                            {temporalChildResults.length > 0 && (
                              <div className="flex flex-col gap-2">
                                <h4 className="text-xs font-bold text-[var(--muted-foreground)] uppercase tracking-wider">Temporal Child Workflows</h4>
                                <div className="rounded-lg border border-[var(--border)] divide-y divide-[var(--border)] overflow-hidden bg-[var(--muted)]/5">
                                  {temporalChildResults.map((item, index) => {
                                    const stats = childWorkflowStats(item);
                                    return (
                                      <div className="grid grid-cols-[100px_1fr] gap-4 items-start p-3 hover:bg-[var(--muted)]/20 transition-colors" key={`${shortJson(item.workflow_id)}-${index}`}>
                                        <span className={cn(
                                          "font-bold text-[10px] px-1.5 py-0.5 rounded text-center leading-none mt-0.5 uppercase block w-fit",
                                          item.status === "completed" && "bg-green-500/10 text-green-500",
                                          item.status === "failed" && "bg-destructive/10 text-destructive",
                                          item.status === "running" && "bg-info/10 text-info"
                                        )}>
                                          {shortJson(item.status)}
                                        </span>
                                        <div className="text-xs min-w-0">
                                          <strong className="text-sm font-bold text-[var(--foreground)]">{shortJson(item.task_kind)}</strong>
                                          <p className="text-xs text-[var(--muted-foreground)] mt-1.5 leading-relaxed break-all bg-[var(--card)] p-2.5 rounded border border-[var(--border)]/50">
                                            {[shortJson(item.summary), stats, shortJson(item.workflow_id)].filter(Boolean).join(" · ")}
                                          </p>
                                        </div>
                                      </div>
                                    );
                                  })}
                                </div>
                              </div>
                            )}

                            {/* Subagent Results */}
                            {subagentResultEntries.length > 0 && (
                              <div className="flex flex-col gap-2">
                                <h4 className="text-xs font-bold text-[var(--muted-foreground)] uppercase tracking-wider">Subagent Results</h4>
                                <div className="rounded-lg border border-[var(--border)] divide-y divide-[var(--border)] overflow-hidden bg-[var(--muted)]/5">
                                  {subagentResultEntries.map(([name, item]) => (
                                    <div className="grid grid-cols-[100px_1fr] gap-4 items-start p-3 hover:bg-[var(--muted)]/20 transition-colors" key={name}>
                                      <span className="font-bold text-[10px] px-1.5 py-0.5 rounded text-center leading-none mt-0.5 bg-[var(--accent)] text-[var(--accent-foreground)] uppercase block w-fit font-mono">
                                        {shortJson(item.source || "run")}
                                      </span>
                                      <div className="text-xs min-w-0">
                                        <strong className="text-sm font-bold text-[var(--foreground)]">{name}</strong>
                                        <p className="text-xs text-[var(--muted-foreground)] mt-1.5 leading-relaxed break-all bg-[var(--card)] p-2.5 rounded border border-[var(--border)]/50">
                                          {shortJson(item.summary || childWorkflowStats({ metadata: item }) || item)}
                                        </p>
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}
                          </CardContent>
                        </Card>
                      ) : (
                        <Card className="shadow-sm border-[var(--border)]">
                          <CardContent className="py-12 text-center text-xs text-[var(--muted-foreground)]">
                            此 Agent 执行未生成具体的子智能体运行或并行计算记录
                          </CardContent>
                        </Card>
                      )}
                    </div>
                  </div>
                </TabsContent>

                {/* Tab: Timeline (调用日志) */}
                <TabsContent value="timeline" className="mt-4 flex flex-col gap-6 focus-visible:ring-0">
                  <Card className="shadow-sm border-[var(--border)]">
                    <CardHeader className="pb-3 border-b border-[var(--border)]/40">
                      <CardTitle className="text-sm font-bold flex items-center gap-1.5">
                        <History size={16} className="text-[var(--primary)]" />
                        工具与 AI 调用时间线
                      </CardTitle>
                      <p className="text-xs text-[var(--muted-foreground)] mt-0.5">按时间排序，记录该运行实例内的全部工具调用及 LLM 交互细节。</p>
                    </CardHeader>
                    <CardContent className="pt-4 flex flex-col gap-4">
                      <div className="rounded-lg border border-[var(--border)] overflow-hidden max-h-[640px] overflow-y-auto divide-y divide-[var(--border)]/60 bg-[var(--muted)]/5">
                        {timeline.map((item) => (
                          <div className="grid grid-cols-[100px_1fr_120px] gap-4 items-start p-3.5 hover:bg-[var(--muted)]/20 transition-colors text-xs" key={item.id}>
                            <span className={cn(
                              "font-bold text-[10px] px-2 py-0.5 rounded text-center leading-none mt-0.5 uppercase block w-fit font-mono",
                              item.status === "succeeded" && "bg-green-500/10 text-green-500",
                              item.status === "failed" && "bg-destructive/10 text-destructive",
                              item.status === "running" && "bg-info/10 text-info",
                              item.status === "queued" && "bg-yellow-500/10 text-yellow-500"
                            )}>
                              {statusLabel[item.status] ?? item.status}
                            </span>
                            <div className="min-w-0">
                              <strong className="text-sm font-bold text-[var(--foreground)]">{item.title}</strong>
                              <p className="text-xs font-mono text-[var(--muted-foreground)] mt-1.5 leading-relaxed break-all bg-[var(--card)] p-3 rounded-lg border border-[var(--border)]/50">
                                {item.body}
                              </p>
                            </div>
                            <span className="text-right text-[10px] text-[var(--muted-foreground)] font-mono mt-0.5">
                              {formatDate(item.at)}
                            </span>
                          </div>
                        ))}
                        {timeline.length === 0 ? (
                          <p className="text-xs text-[var(--muted-foreground)] p-8 text-center">暂无系统调用及调用痕迹记录</p>
                        ) : null}
                      </div>
                    </CardContent>
                  </Card>
                </TabsContent>

                {/* Tab: Evidence (证据与信号) */}
                <TabsContent value="evidence" className="mt-4 flex flex-col gap-6 focus-visible:ring-0">
                  <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 items-start">
                    {/* Evidence refs */}
                    <Card className="shadow-sm border-[var(--border)]">
                      <CardHeader className="pb-3 border-b border-[var(--border)]/40">
                        <CardTitle className="text-sm font-bold flex items-center gap-1.5">
                          <FileSearch size={16} className="text-[var(--primary)]" />
                          关联证据凭证 (Evidence Refs · {evidenceItems.length})
                        </CardTitle>
                        <p className="text-xs text-[var(--muted-foreground)] mt-0.5">Agent 推理、审查结论背后的事实或文档依据</p>
                      </CardHeader>
                      <CardContent className="pt-4">
                        <div className="rounded-lg border border-[var(--border)] overflow-hidden divide-y divide-[var(--border)] bg-[var(--muted)]/5">
                          {evidenceItems.map((item) => (
                            <div className="p-3.5 text-xs hover:bg-[var(--muted)]/20 transition-colors flex flex-col gap-2" key={item.id}>
                              <div className="flex items-center justify-between gap-2">
                                <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-[var(--accent)] text-[var(--accent-foreground)] uppercase font-mono">
                                  {item.kind}
                                </span>
                                <span className="text-[10px] text-[var(--muted-foreground)] font-mono">置信度: {shortJson(item.confidence)}</span>
                              </div>
                              <strong className="text-sm font-bold text-[var(--foreground)]">{item.label}</strong>
                              <div className="flex flex-col gap-1 text-[10px] text-[var(--muted-foreground)] mt-0.5 leading-normal">
                                <span><span className="font-semibold text-[var(--foreground)]">来源:</span> {shortJson(item.source)}</span>
                                <span><span className="font-semibold text-[var(--foreground)]">关联输出:</span> {item.outputTitle}</span>
                              </div>
                            </div>
                          ))}
                          {evidenceItems.length === 0 ? (
                            <p className="text-xs text-[var(--muted-foreground)] p-8 text-center">暂未搜集到关联事实或文件依据</p>
                          ) : null}
                        </div>
                      </CardContent>
                    </Card>

                    {/* Coverage Signals */}
                    <Card className="shadow-sm border-[var(--border)]">
                      <CardHeader className="pb-3 border-b border-[var(--border)]/40">
                        <CardTitle className="text-sm font-bold flex items-center gap-1.5">
                          <ListChecks size={16} className="text-[var(--primary)]" />
                          覆盖率信号 (Coverage Signals · {coverageItems.length})
                        </CardTitle>
                        <p className="text-xs text-[var(--muted-foreground)] mt-0.5">本项运行在测试或检测任务中的覆盖详情</p>
                      </CardHeader>
                      <CardContent className="pt-4">
                        <div className="rounded-lg border border-[var(--border)] overflow-hidden divide-y divide-[var(--border)] bg-[var(--muted)]/5">
                          {coverageItems.map((entry) => (
                            <div className="p-3.5 text-xs hover:bg-[var(--muted)]/20 transition-colors flex flex-col gap-2" key={entry.id}>
                              <div className="flex items-center justify-between gap-2">
                                <span className={cn(
                                  "text-[10px] font-bold px-2 py-0.5 rounded-full uppercase",
                                  entry.coverage_state === "covered" && "bg-green-500/10 text-green-500",
                                  entry.coverage_state === "partial" && "bg-yellow-500/10 text-yellow-500",
                                  entry.coverage_state === "uncovered" && "bg-destructive/10 text-destructive"
                                )}>
                                  {entry.coverage_state}
                                </span>
                                <span className="text-[10px] font-bold text-[var(--muted-foreground)]">
                                  {entry.verified_by_human ? "已人工核实" : "挂起审阅"}
                                </span>
                              </div>
                              <strong className="text-sm font-bold text-[var(--foreground)]">{entry.module_key}</strong>
                              <p className="text-xs text-[var(--muted-foreground)] leading-relaxed mt-0.5">{entry.behavior_summary}</p>
                              <div className="flex items-center justify-between text-[10px] text-[var(--muted-foreground)] border-t border-[var(--border)]/40 pt-2 mt-1">
                                <span>置信度: {entry.confidence}</span>
                                <span>关联输出: {entry.outputTitle}</span>
                              </div>
                            </div>
                          ))}
                          {coverageItems.length === 0 ? (
                            <p className="text-xs text-[var(--muted-foreground)] p-8 text-center">暂未搜集到可用覆盖状态信号</p>
                          ) : null}
                        </div>
                      </CardContent>
                    </Card>
                  </div>
                </TabsContent>

                {/* Tab: Outputs (候选输出) */}
                <TabsContent value="outputs" className="mt-4 flex flex-col gap-6 focus-visible:ring-0">
                  <Card className="shadow-sm border-[var(--border)]">
                    <CardHeader className="pb-3 border-b border-[var(--border)]/40">
                      <CardTitle className="text-sm font-bold flex items-center gap-1.5">
                        <ClipboardCheck size={16} className="text-[var(--primary)]" />
                        审阅候选输出清单 (Staged Outputs)
                      </CardTitle>
                      <p className="text-xs text-[var(--muted-foreground)] mt-0.5">由 Agent 工作流产出的推荐成果。请开发人员在此进行最终采纳或拒绝决策。</p>
                    </CardHeader>
                    <CardContent className="pt-4 flex flex-col gap-4">
                      {detail?.staged_outputs.map((output) => (
                        <article className="rounded-xl border border-[var(--border)] p-4 flex flex-col gap-3 shadow-sm bg-[var(--card)] hover:shadow transition-shadow" key={output.id}>
                          <div className="flex items-start justify-between gap-4 border-b border-[var(--border)]/40 pb-2.5">
                            <div className="min-w-0">
                              <h4 className="text-sm font-bold text-[var(--foreground)]">{output.title}</h4>
                              <p className="text-[10px] text-[var(--muted-foreground)] mt-1">{outputMeta(output)}</p>
                            </div>
                            <span className={cn(
                              "text-[10px] font-bold px-2 py-0.5 rounded-full uppercase",
                              output.status === "accepted" && "bg-green-500/10 text-green-500",
                              output.status === "rejected" && "bg-destructive/10 text-destructive",
                              output.status === "staged" && "bg-yellow-500/10 text-yellow-500"
                            )}>
                              {statusLabel[output.status] ?? output.status}
                            </span>
                          </div>
                          
                          <div className="text-xs leading-relaxed whitespace-pre-wrap font-mono text-[var(--foreground)] bg-[var(--muted)]/20 p-3.5 rounded-lg border border-[var(--border)]/50">
                            {shortJson(output.payload.expected_result ?? output.payload.recommendation ?? output.payload.note_type)}
                          </div>
                          
                          {output.evidence_refs.length > 0 && (
                            <div className="text-[10px] text-[var(--muted-foreground)] bg-[var(--muted)]/5 p-2 rounded border border-[var(--border)]/40 mt-0.5 flex flex-col gap-0.5">
                              <span className="font-bold text-[var(--foreground)]">证据依据:</span>
                              <p className="leading-normal">{output.evidence_refs.map((refItem) => shortJson(refItem.label ?? refItem.ref_id)).join(" · ")}</p>
                            </div>
                          )}

                          <div className="flex items-center gap-2 mt-1 pt-1">
                            <Button
                              variant="default"
                              size="sm"
                              type="button"
                              onClick={() => void handleOutputDecision(output, "accepted")}
                              disabled={busy || output.status !== "staged"}
                              className="gap-1 px-4 h-8 text-xs font-semibold"
                            >
                              <Check size={12} />
                              采纳输出
                            </Button>
                            <Button
                              variant="outline"
                              size="sm"
                              type="button"
                              onClick={() => void handleOutputDecision(output, "rejected")}
                              disabled={busy || output.status !== "staged"}
                              className="gap-1 px-4 h-8 text-xs font-semibold hover:bg-destructive/10 hover:text-destructive"
                            >
                              <X size={12} />
                              拒绝输出
                            </Button>
                          </div>
                        </article>
                      ))}
                      {(!detail || detail.staged_outputs.length === 0) ? (
                        <p className="text-xs text-[var(--muted-foreground)] p-10 text-center">当前运行实例中尚未提报候选输出产物</p>
                      ) : null}
                    </CardContent>
                  </Card>
                </TabsContent>

                {/* Tab: Memory (项目记忆) */}
                <TabsContent value="memory" className="mt-4 flex flex-col gap-6 focus-visible:ring-0">
                  <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 items-start">
                    {/* Markdown Memory Curate (Left Column) */}
                    <Card className="shadow-sm border-[var(--border)] flex flex-col">
                      <CardHeader className="pb-3 border-b border-[var(--border)]/40">
                        <CardTitle className="text-sm font-bold flex items-center gap-1.5">
                          <Brain size={16} className="text-[var(--primary)]" />
                          项目全局记忆库 (Markdown)
                        </CardTitle>
                        <p className="text-xs text-[var(--muted-foreground)] mt-0.5">编辑固化项目经验、规约和基础信息，这些文字将被输入给 Agent 形成基础常识。</p>
                      </CardHeader>
                      <CardContent className="pt-4 flex flex-col gap-4 flex-1">
                        <div className="flex flex-col gap-1.5 flex-1">
                          <Label className="text-xs font-bold text-[var(--muted-foreground)]">Curated Content</Label>
                          <Textarea 
                            value={memoryContent} 
                            rows={15} 
                            onChange={(event) => setMemoryContent(event.target.value)} 
                            className="font-mono text-xs leading-relaxed bg-[var(--muted)]/5 border-[var(--border)]/80 p-3 rounded"
                          />
                        </div>
                        <Button 
                          variant="default" 
                          type="button" 
                          onClick={() => void handleCurateMemory()} 
                          disabled={busy || !selectedProjectId} 
                          className="self-start gap-1 text-xs h-9 px-5 mt-1"
                        >
                          <Save size={12} />
                          更新并保存项目记忆
                        </Button>
                      </CardContent>
                    </Card>

                    {/* Memory Search & Versions History (Right Column) */}
                    <div className="flex flex-col gap-6">
                      {/* Search box card */}
                      <Card className="shadow-sm border-[var(--border)]">
                        <CardHeader className="pb-3 border-b border-[var(--border)]/40">
                          <CardTitle className="text-sm font-bold flex items-center gap-1.5">
                            <Search size={16} className="text-[var(--primary)]" />
                            语义检索记忆
                          </CardTitle>
                        </CardHeader>
                        <CardContent className="pt-4 flex flex-col gap-4">
                          <div className="flex gap-2">
                            <Input 
                              value={memoryQuery} 
                              onChange={(event) => setMemoryQuery(event.target.value)} 
                              placeholder="输入项目内关键词..."
                              className="text-xs h-9"
                            />
                            <Button 
                              variant="outline" 
                              type="button" 
                              onClick={() => void handleMemorySearch()} 
                              disabled={busy || !selectedWorkspaceId}
                              className="shrink-0 gap-1 text-xs h-9 px-4 border-[var(--border)]"
                            >
                              <Search size={12} />
                              检索
                            </Button>
                          </div>
                          <div className="flex flex-col gap-2 max-h-[190px] overflow-y-auto pr-1">
                            {memoryResults.map((result) => (
                              <article className="rounded-lg border border-[var(--border)] bg-[var(--muted)]/20 p-3 flex flex-col gap-1 hover:bg-[var(--muted)]/30 transition-colors" key={result.memory_file.id}>
                                <div className="flex items-start justify-between gap-4">
                                  <div className="min-w-0">
                                    <strong className="text-xs font-bold text-[var(--foreground)]">{result.memory_file.scope} · v{result.memory_file.current_version}</strong>
                                    <span className="text-[10px] text-[var(--muted-foreground)] line-clamp-2 leading-relaxed mt-1">{result.snippet}</span>
                                  </div>
                                  <Button variant="outline" size="sm" type="button" onClick={() => void handleMemoryVersionSelect(result.memory_file)} disabled={busy} className="h-7 text-[10px] px-2 shrink-0 border-[var(--border)]">
                                    查看版本
                                  </Button>
                                </div>
                                <span className="text-[9px] font-mono text-[var(--muted-foreground)] truncate mt-1 leading-none">{result.memory_file.path}</span>
                              </article>
                            ))}
                            {memoryResults.length === 0 ? <p className="text-xs text-[var(--muted-foreground)] text-center py-6">暂无关联记忆文件产物</p> : null}
                          </div>
                        </CardContent>
                      </Card>

                      {/* Versions History Card */}
                      <Card className="shadow-sm border-[var(--border)]">
                        <CardHeader className="pb-3 border-b border-[var(--border)]/40 flex flex-row items-center justify-between gap-4">
                          <div>
                            <CardTitle className="text-sm font-bold flex items-center gap-1.5">
                              <History size={16} className="text-[var(--primary)]" />
                              快照版本历史
                            </CardTitle>
                            <p className="text-[10px] text-[var(--muted-foreground)] mt-0.5">
                              {selectedMemoryFile ? `当前选中: ${selectedMemoryFile.scope} · v${selectedMemoryFile.current_version}` : "未选择任何记忆模型"}
                            </p>
                          </div>
                          <RotateCcw size={14} className="text-[var(--muted-foreground)] shrink-0" />
                        </CardHeader>
                        <CardContent className="pt-4">
                          <div className="flex flex-col gap-2 max-h-[190px] overflow-y-auto pr-1">
                            {memoryVersions.map((version) => (
                              <article className="flex items-start justify-between gap-4 p-2.5 rounded-lg border border-[var(--border)] text-xs hover:bg-[var(--muted)]/10 transition-colors" key={version.id}>
                                <div className="min-w-0 flex flex-col gap-1">
                                  <strong className="text-xs font-bold text-[var(--foreground)]">v{version.version} · {version.patch_summary || "记忆库快照"}</strong>
                                  <div className="text-[9px] text-[var(--muted-foreground)] flex flex-wrap gap-x-2 gap-y-0.5 leading-none">
                                    <span>编辑人: {version.editor || "system"}</span>
                                    <span>原因: {version.reason || "无记录"}</span>
                                    <span>时间: {formatDate(version.created_at)}</span>
                                  </div>
                                  <span className="text-[8px] font-mono text-[var(--muted-foreground)] leading-none mt-1">Checksum: {version.checksum.slice(0, 12)}</span>
                                </div>
                                <Button
                                  variant="outline"
                                  size="sm"
                                  type="button"
                                  onClick={() => void handleMemoryRollback(version.version)}
                                  disabled={busy || !selectedMemoryFile || version.version === selectedMemoryFile.current_version}
                                  className="shrink-0 h-7 text-[10px] px-2.5 border-[var(--border)]"
                                >
                                  回滚
                                </Button>
                              </article>
                            ))}
                            {memoryVersions.length === 0 ? <p className="text-xs text-[var(--muted-foreground)] text-center py-6">暂无可用版本提交记录</p> : null}
                          </div>
                        </CardContent>
                      </Card>
                    </div>
                  </div>
                </TabsContent>
              </Tabs>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
