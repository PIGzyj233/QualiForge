import { useEffect, useMemo, useState } from "react";
import { Bot, Boxes, Check, CircleStop, ClipboardCheck, FileSearch, GitBranch, ListChecks, Play, RefreshCcw, RotateCcw, Save, Search, X } from "lucide-react";
import { useParams } from "react-router-dom";
import { AgentExecutionDetailRecord, AgentMemoryFileRecord, AgentMemorySearchResult, AgentMemoryVersionRecord, AgentRunRecord, AgentRunStatus, AgentStagedOutputRecord, cancelAgentRun, curateAgentMemory, createAgentConversation, createAgentRun, decideAgentApproval, decideAgentStagedOutput, executeAgentRun, getAgentExecutionDetail, listAgentMemoryVersions, listAgentRuns, rollbackAgentMemory, resumeAgentRun, searchAgentMemory, upsertAgentBudgetPolicy } from "../api/agents";
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
import { usePagination } from "../hooks/usePagination";
import { statusLabel } from "../lib/labels";
import { pickExistingId } from "../lib/selection";
import { cn } from "@/lib/utils";

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
    } else {
      setDetail(null);
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

  const eyebrowClass = "text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)]";
  const detailsClass = "rounded-md border border-[var(--border)] p-3 [&>summary]:cursor-pointer [&>summary]:text-sm [&>summary]:font-semibold [&>summary]:list-none";

  return (
    <div className="flex flex-col gap-5 min-w-0">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className={cn(eyebrowClass, "mb-1")}>Agent Runs</p>
          <h1 className="font-heading text-2xl font-bold">Agent Workbench</h1>
        </div>
        <Bot size={20} className="text-[var(--muted-foreground)] shrink-0" aria-hidden="true" />
      </div>

      {message ? (
        <Alert>
          <AlertDescription>{message}</AlertDescription>
        </Alert>
      ) : null}

      <div className="grid grid-cols-1 md:grid-cols-[1fr_1fr_auto] gap-3 items-end">
        <div className="flex flex-col gap-1.5">
          <Label>Workspace</Label>
          <Select
            value={selectedWorkspaceId || "__none__"}
            onValueChange={(value) => void handleWorkspaceSwitch(value === "__none__" ? "" : value)}
            disabled={busy || workspaces.length === 0}
          >
            <SelectTrigger>
              <SelectValue placeholder="未选择" />
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
          <Label>Project</Label>
          <Select
            value={selectedProjectId || "__none__"}
            onValueChange={(value) => void handleProjectSwitch(value === "__none__" ? "" : value)}
            disabled={busy || projects.length === 0}
          >
            <SelectTrigger>
              <SelectValue placeholder="未选择" />
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
        <Button variant="outline" size="icon" type="button" onClick={() => void refreshAll()} title="刷新 Agent Workbench" disabled={busy} className="shrink-0">
          <RefreshCcw size={18} aria-hidden="true" />
        </Button>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(220px,0.8fr)_minmax(240px,0.85fr)_minmax(320px,1.25fr)] gap-4 items-start">
        <Card className="min-w-0" aria-label="Agent run launcher">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
            <div>
              <p className={eyebrowClass}>Launch</p>
              <CardTitle className="text-base">新建执行</CardTitle>
            </div>
            <Play size={18} className="text-[var(--muted-foreground)]" aria-hidden="true" />
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <Label>Goal</Label>
              <Textarea value={goal} onChange={(event) => setGoal(event.target.value)} rows={4} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Repository</Label>
              <Select value={selectedRepositoryId || "__none__"} onValueChange={(value) => setSelectedRepositoryId(value === "__none__" ? "" : value)} disabled={busy || repositories.length === 0}>
                <SelectTrigger>
                  <SelectValue placeholder="未选择" />
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
            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1.5">
                <Label>Ref</Label>
                <Input value={ref} onChange={(event) => setRef(event.target.value)} />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Candidates</Label>
                <Input type="number" min={1} max={5} value={candidateLimit} onChange={(event) => setCandidateLimit(numberValue(event.target.value, 3))} />
              </div>
            </div>
            <details className={detailsClass}>
              <summary>高级参数（预算 / 并发 / 上下文）</summary>
              <div className="mt-3 flex flex-col gap-3">
                <div className="grid grid-cols-2 gap-3">
                  <div className="flex flex-col gap-1.5">
                    <Label>Tool calls</Label>
                    <Input type="number" min={0} value={maxToolCalls} onChange={(event) => setMaxToolCalls(numberValue(event.target.value, 60))} />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label>Subagents</Label>
                    <Input type="number" min={0} value={maxSubagents} onChange={(event) => setMaxSubagents(numberValue(event.target.value, 4))} />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="flex flex-col gap-1.5">
                    <Label>Parallel</Label>
                    <Input type="number" min={1} value={maxParallelSubagents} onChange={(event) => setMaxParallelSubagents(numberValue(event.target.value, 3))} />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label>Model calls</Label>
                    <Input type="number" min={0} value={maxModelCalls} onChange={(event) => setMaxModelCalls(numberValue(event.target.value, 20))} />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="flex flex-col gap-1.5">
                    <Label>Wall minutes</Label>
                    <Input type="number" min={1} value={maxWallMinutes} onChange={(event) => setMaxWallMinutes(numberValue(event.target.value, 20))} />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label>Source chars</Label>
                    <Input type="number" min={0} value={maxSourceChars} onChange={(event) => setMaxSourceChars(numberValue(event.target.value, 200000))} />
                  </div>
                </div>
              </div>
            </details>
            <Button type="button" onClick={() => void handleLaunch()} disabled={busy || !selectedRepositoryId || !selectedProjectId} className="self-start">
              <Play size={16} aria-hidden="true" />
              启动
            </Button>
            <details className={cn(detailsClass, "bg-[var(--muted)]/30")}>
              <summary>项目预算默认值（保存后影响后续 Run）</summary>
              <div className="mt-3 flex flex-col gap-3">
                <div className="grid grid-cols-2 gap-3">
                  <div className="flex flex-col gap-1.5">
                    <Label>Tool calls</Label>
                    <Input type="number" min={0} value={policyMaxToolCalls} onChange={(event) => setPolicyMaxToolCalls(numberValue(event.target.value, 60))} />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label>Model calls</Label>
                    <Input type="number" min={0} value={policyMaxModelCalls} onChange={(event) => setPolicyMaxModelCalls(numberValue(event.target.value, 20))} />
                  </div>
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label>Subagents</Label>
                  <Input type="number" min={0} value={policyMaxSubagents} onChange={(event) => setPolicyMaxSubagents(numberValue(event.target.value, 4))} />
                </div>
                <Button variant="outline" type="button" onClick={() => void handleSaveBudgetPolicy()} disabled={busy || !selectedProjectId} className="self-start">
                  <Save size={16} aria-hidden="true" />
                  保存
                </Button>
              </div>
            </details>
          </CardContent>
        </Card>

        <Card className="min-w-0 flex flex-col" aria-label="Agent run list">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
            <div>
              <p className={eyebrowClass}>Runs</p>
              <CardTitle className="text-base">{selectedProject ? `${selectedProject.key} · ${runs.length}` : `${runs.length} runs`}</CardTitle>
            </div>
            <GitBranch size={18} className="text-[var(--muted-foreground)]" aria-hidden="true" />
          </CardHeader>
          <CardContent className="flex flex-col gap-3 flex-1 min-h-0">
            <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Run status filter">
              {runStatuses.map((status) => (
                <Button
                  key={status}
                  type="button"
                  size="sm"
                  variant={statusFilter === status ? "default" : "outline"}
                  onClick={() => void handleFilteredRefresh(status)}
                >
                  {status === "all" ? "全部" : statusLabel[status]}
                </Button>
              ))}
            </div>
            <div className="rounded-md border border-[var(--border)] overflow-hidden max-h-[560px] overflow-y-auto">
              {runsPagination.currentItems.map((run) => (
                <button
                  className={cn(
                    "w-full text-left px-3 py-3 border-b border-[var(--border)] last:border-b-0 transition-colors hover:bg-[var(--muted)] flex flex-col gap-1",
                    selectedRunId === run.id && "bg-[var(--accent)] border-l-2 border-l-[var(--primary)]"
                  )}
                  key={run.id}
                  type="button"
                  onClick={() => void handleSelectRun(run.id)}
                >
                  <strong className="text-sm font-semibold line-clamp-2">{run.goal}</strong>
                  <span className="text-xs text-[var(--muted-foreground)]">
                    {statusLabel[run.status] ?? run.status} · {run.current_phase} · {formatDate(run.created_at)}
                  </span>
                  <small className="text-[10px] font-mono text-[var(--muted-foreground)] truncate">
                    {run.temporal_workflow_id || run.langgraph_thread_id || run.id}
                  </small>
                </button>
              ))}
              {runs.length === 0 ? <p className="text-sm text-[var(--muted-foreground)] p-4">暂无 Agent run</p> : null}
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

        <Card className="min-w-0" aria-label="Agent run detail">
          <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0 pb-3">
            <div className="min-w-0">
              <p className={eyebrowClass}>Detail</p>
              <CardTitle className="text-base line-clamp-2">{selectedRun?.goal ?? "未选择 Run"}</CardTitle>
              <p className="text-xs text-[var(--muted-foreground)] mt-1">
                {selectedRepository ? `${selectedRepository.name} · ${ref || selectedRepository.default_branch}` : "Repository"}
              </p>
            </div>
            {selectedRun ? <StatusPill status={selectedRun.status} /> : null}
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {selectedRun ? (
              <>
                <div className="flex flex-wrap gap-2">
                  <Button variant="outline" size="sm" type="button" onClick={() => void handleSelectRun(selectedRun.id)} disabled={busy}>
                    <RefreshCcw size={16} aria-hidden="true" />
                    刷新
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    type="button"
                    onClick={() => void handleResume()}
                    disabled={busy || !["waiting_for_user", "failed"].includes(selectedRun.status)}
                  >
                    <RotateCcw size={16} aria-hidden="true" />
                    Resume
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    type="button"
                    onClick={() => void handleCancel()}
                    disabled={busy || ["succeeded", "failed", "cancelled"].includes(selectedRun.status)}
                  >
                    <CircleStop size={16} aria-hidden="true" />
                    Cancel
                  </Button>
                </div>

                <div className="flex flex-col gap-1.5">
                  <Label>Resume reason</Label>
                  <Input value={resumeReason} onChange={(event) => setResumeReason(event.target.value)} />
                </div>

                <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                  {[
                    { label: "Tool calls", value: `${shortJson(budgetUsage.tool_calls)} / ${shortJson(budgetLimits.max_tool_calls)}` },
                    { label: "Subagents", value: `${shortJson(budgetUsage.subagents)} / ${shortJson(budgetLimits.max_subagents)}` },
                    { label: "Parallel", value: `${shortJson(budgetUsage.parallel_subagents)} / ${shortJson(budgetLimits.max_parallel_subagents)}` },
                    { label: "Model calls", value: `${shortJson(budgetUsage.model_calls)} / ${shortJson(budgetLimits.max_model_calls)}` },
                    { label: "Source chars", value: `${shortJson(budgetUsage.source_chars_sent)} / ${shortJson(budgetLimits.max_total_source_chars_sent)}` }
                  ].map((metric) => (
                    <div key={metric.label} className="rounded-md border border-[var(--border)] bg-[var(--card)] p-3 flex flex-col gap-1">
                      <span className="text-[10px] font-bold uppercase text-[var(--muted-foreground)]">{metric.label}</span>
                      <strong className="text-base font-bold text-[var(--primary)]">{metric.value}</strong>
                    </div>
                  ))}
                </div>

                {selectedRun.failure_reason ? (
                  <Alert variant="warning">
                    <AlertDescription>{selectedRun.failure_reason}</AlertDescription>
                  </Alert>
                ) : null}

                {detail?.pending_approvals.length ? (
                  <section className="flex flex-col gap-3" aria-label="Pending approvals">
                    <div className="flex items-center justify-between gap-2">
                      <div>
                        <p className={eyebrowClass}>Approvals</p>
                        <h3 className="font-heading text-sm font-bold">{detail.pending_approvals.length} pending</h3>
                      </div>
                      <ClipboardCheck size={18} className="text-[var(--muted-foreground)]" aria-hidden="true" />
                    </div>
                    <div className="grid grid-cols-1 gap-3">
                      {detail.pending_approvals.map((approval) => (
                        <article className="rounded-md border border-[var(--border)] p-4 flex flex-col gap-3" key={approval.id}>
                          <div className="flex flex-col gap-1">
                            <strong className="text-sm">{approval.approval_type}</strong>
                            <span className="text-sm text-[var(--muted-foreground)]">{approval.request_summary}</span>
                            <small className="text-xs text-[var(--muted-foreground)]">{approval.requested_by} · {formatDate(approval.created_at)}</small>
                          </div>
                          <div className="flex flex-wrap gap-2">
                            <Button variant="outline" size="sm" type="button" onClick={() => void handleApprovalDecision(approval.id, "approved")} disabled={busy}>
                              <Check size={16} aria-hidden="true" />
                              批准
                            </Button>
                            <Button variant="outline" size="sm" type="button" onClick={() => void handleApprovalDecision(approval.id, "rejected")} disabled={busy}>
                              <X size={16} aria-hidden="true" />
                              拒绝
                            </Button>
                          </div>
                        </article>
                      ))}
                    </div>
                  </section>
                ) : null}

                <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2 gap-4">
                  <div className="rounded-md border border-[var(--border)] p-4 flex flex-col gap-3">
                    <div className="flex items-center justify-between gap-2">
                      <div>
                        <p className={eyebrowClass}>Subagents</p>
                        <h3 className="font-heading text-sm font-bold">{shortJson(subagentPlan.selection_policy || "not planned")}</h3>
                      </div>
                      <Boxes size={18} className="text-[var(--muted-foreground)]" aria-hidden="true" />
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {selectedSubagents.map((name) => (
                        <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-[var(--accent)] text-[var(--accent-foreground)]" key={name}>{name}</span>
                      ))}
                      {selectedSubagents.length === 0 ? <p className="text-sm text-[var(--muted-foreground)]">暂无 subagent plan</p> : null}
                    </div>
                    <small className="text-xs text-[var(--muted-foreground)]">{parallelGroups.map((group) => Array.isArray(group) ? group.join(" + ") : shortJson(group)).join(" / ") || "no parallel groups"}</small>
                    {skippedSubagents.length > 0 ? <small className="text-xs text-[var(--muted-foreground)]">Skipped: {skippedSubagents.map((item) => shortJson(item)).join(" · ")}</small> : null}
                    {subagentRuns.length > 0 ? (
                      <div className="rounded-md border border-[var(--border)] overflow-hidden divide-y divide-[var(--border)]">
                        {subagentRuns.map((item) => (
                          <div className="grid grid-cols-[minmax(76px,112px)_1fr] gap-2 items-center p-2 text-sm" key={item.id}>
                            <span className="text-xs font-medium">{item.status}</span>
                            <div className="min-w-0">
                              <strong className="text-sm block">{item.subagent_name} · {item.stage}</strong>
                              <small className="text-xs text-[var(--muted-foreground)] break-words">{[item.parallel_group, item.output_summary || item.error_summary || item.summary, `${item.duration_ms}ms`].filter(Boolean).join(" · ")}</small>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : null}
                    {temporalChildResults.length > 0 ? (
                      <div className="rounded-md border border-[var(--border)] overflow-hidden divide-y divide-[var(--border)]">
                        {temporalChildResults.map((item, index) => {
                          const stats = childWorkflowStats(item);
                          return (
                            <div className="grid grid-cols-[minmax(76px,112px)_1fr] gap-2 items-center p-2 text-sm" key={`${shortJson(item.workflow_id)}-${index}`}>
                              <span className="text-xs font-medium">{shortJson(item.status)}</span>
                              <div className="min-w-0">
                                <strong className="text-sm block">{shortJson(item.task_kind)}</strong>
                                <small className="text-xs text-[var(--muted-foreground)] break-words">{[shortJson(item.summary), stats, shortJson(item.workflow_id)].filter(Boolean).join(" · ")}</small>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    ) : null}
                    {subagentResultEntries.length > 0 ? (
                      <div className="rounded-md border border-[var(--border)] overflow-hidden divide-y divide-[var(--border)]">
                        {subagentResultEntries.map(([name, item]) => (
                          <div className="grid grid-cols-[minmax(76px,112px)_1fr] gap-2 items-center p-2 text-sm" key={name}>
                            <span className="text-xs font-medium">{shortJson(item.source || "run")}</span>
                            <div className="min-w-0">
                              <strong className="text-sm block">{name}</strong>
                              <small className="text-xs text-[var(--muted-foreground)] break-words">{shortJson(item.summary || childWorkflowStats({ metadata: item }) || item)}</small>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </div>

                  <div className="rounded-md border border-[var(--border)] p-4 flex flex-col gap-3">
                    <div className="flex items-center justify-between gap-2">
                      <div>
                        <p className={eyebrowClass}>Timeline</p>
                        <h3 className="font-heading text-sm font-bold">工具和模型调用</h3>
                      </div>
                      <Boxes size={18} className="text-[var(--muted-foreground)]" aria-hidden="true" />
                    </div>
                    <div className="rounded-md border border-[var(--border)] overflow-hidden max-h-80 overflow-y-auto">
                      {timeline.map((item) => (
                        <div className="grid grid-cols-[minmax(76px,112px)_1fr] gap-2 items-center p-2 border-b border-[var(--border)] last:border-b-0 text-sm" key={item.id}>
                          <span className="text-xs font-medium">{statusLabel[item.status] ?? item.status}</span>
                          <div className="min-w-0">
                            <strong className="text-sm block">{item.title}</strong>
                            <small className="text-xs text-[var(--muted-foreground)] break-words">{formatDate(item.at)} · {item.body}</small>
                          </div>
                        </div>
                      ))}
                      {timeline.length === 0 ? <p className="text-sm text-[var(--muted-foreground)] p-3">暂无调用记录</p> : null}
                    </div>
                  </div>

                  <div className="rounded-md border border-[var(--border)] p-4 flex flex-col gap-3 lg:col-span-2 2xl:col-span-1">
                    <div className="flex items-center justify-between gap-2">
                      <div>
                        <p className={eyebrowClass}>Sandbox</p>
                        <h3 className="font-heading text-sm font-bold">仓库沙箱</h3>
                      </div>
                      <GitBranch size={18} className="text-[var(--muted-foreground)]" aria-hidden="true" />
                    </div>
                    {detail?.repository_sandboxes.map((sandbox) => (
                      <div className="rounded-md border border-[var(--border)] bg-[var(--muted)]/30 p-3 flex flex-col gap-1 text-sm" key={sandbox.id}>
                        <strong>{sandbox.ref} · {statusLabel[sandbox.status] ?? sandbox.status}</strong>
                        <span className="text-xs text-[var(--muted-foreground)]">{sandbox.resolved_ref || "unresolved"}</span>
                        <small className="text-xs text-[var(--muted-foreground)] break-all">{sandbox.error_summary || sandbox.worktree_path}</small>
                      </div>
                    ))}
                    {detail?.repository_sandboxes.length === 0 ? <p className="text-sm text-[var(--muted-foreground)]">暂无沙箱记录</p> : null}
                  </div>
                </div>

                <section className="flex flex-col gap-3" aria-label="Evidence and coverage">
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <p className={eyebrowClass}>Evidence</p>
                      <h3 className="font-heading text-sm font-bold">证据与覆盖信号</h3>
                    </div>
                    <FileSearch size={18} className="text-[var(--muted-foreground)]" aria-hidden="true" />
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="rounded-md border border-[var(--border)] p-4 flex flex-col gap-3">
                      <div className="flex items-center justify-between gap-2">
                        <div>
                          <p className={eyebrowClass}>Evidence refs</p>
                          <h3 className="font-heading text-sm font-bold">{evidenceItems.length} refs</h3>
                        </div>
                        <FileSearch size={16} className="text-[var(--muted-foreground)]" aria-hidden="true" />
                      </div>
                      <div className="rounded-md border border-[var(--border)] overflow-hidden divide-y divide-[var(--border)]">
                        {evidenceItems.map((item) => (
                          <div className="grid grid-cols-[minmax(64px,96px)_1fr] gap-2 items-start p-2 text-sm" key={item.id}>
                            <span className="text-xs font-medium">{item.kind}</span>
                            <div className="min-w-0">
                              <strong className="text-sm block">{item.label}</strong>
                              <small className="text-xs text-[var(--muted-foreground)] break-words">{item.outputTitle} · {shortJson(item.source)} · confidence {shortJson(item.confidence)}</small>
                            </div>
                          </div>
                        ))}
                        {evidenceItems.length === 0 ? <p className="text-sm text-[var(--muted-foreground)] p-3">暂无 evidence ref</p> : null}
                      </div>
                    </div>

                    <div className="rounded-md border border-[var(--border)] p-4 flex flex-col gap-3">
                      <div className="flex items-center justify-between gap-2">
                        <div>
                          <p className={eyebrowClass}>Coverage</p>
                          <h3 className="font-heading text-sm font-bold">{coverageItems.length} signals</h3>
                        </div>
                        <ListChecks size={16} className="text-[var(--muted-foreground)]" aria-hidden="true" />
                      </div>
                      <div className="rounded-md border border-[var(--border)] overflow-hidden divide-y divide-[var(--border)]">
                        {coverageItems.map((entry) => (
                          <div className="p-2 text-sm flex flex-col gap-1" key={entry.id}>
                            <strong className="text-sm">{entry.module_key} · {entry.coverage_state}</strong>
                            <small className="text-xs text-[var(--muted-foreground)]">{entry.behavior_summary}</small>
                            <small className="text-xs text-[var(--muted-foreground)]">{entry.outputTitle} · confidence {entry.confidence} · {entry.verified_by_human ? "human verified" : "pending review"}</small>
                          </div>
                        ))}
                        {coverageItems.length === 0 ? <p className="text-sm text-[var(--muted-foreground)] p-3">暂无 coverage signal</p> : null}
                      </div>
                    </div>
                  </div>
                </section>

                <section className="flex flex-col gap-3" aria-label="Staged outputs">
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <p className={eyebrowClass}>Staged Outputs</p>
                      <h3 className="font-heading text-sm font-bold">审阅候选输出</h3>
                    </div>
                    <ClipboardCheck size={18} className="text-[var(--muted-foreground)]" aria-hidden="true" />
                  </div>
                  <div className="grid grid-cols-1 gap-3">
                    {detail?.staged_outputs.map((output) => (
                      <article className="rounded-md border border-[var(--border)] p-4 flex flex-col gap-3" key={output.id}>
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0 flex flex-col gap-1">
                            <strong className="text-sm">{output.title}</strong>
                            <span className="text-xs text-[var(--muted-foreground)]">{outputMeta(output)} · {statusLabel[output.status]}</span>
                          </div>
                          <StatusPill status={output.status} />
                        </div>
                        <p className="text-sm">{shortJson(output.payload.expected_result ?? output.payload.recommendation ?? output.payload.note_type)}</p>
                        <small className="text-xs text-[var(--muted-foreground)]">{output.evidence_refs.map((refItem) => shortJson(refItem.label ?? refItem.ref_id)).join(" · ") || "no evidence"}</small>
                        <div className="flex flex-wrap gap-2">
                          <Button variant="outline" size="sm" type="button" onClick={() => void handleOutputDecision(output, "accepted")} disabled={busy || output.status !== "staged"}>
                            <Check size={16} aria-hidden="true" />
                            采纳
                          </Button>
                          <Button variant="outline" size="sm" type="button" onClick={() => void handleOutputDecision(output, "rejected")} disabled={busy || output.status !== "staged"}>
                            <X size={16} aria-hidden="true" />
                            拒绝
                          </Button>
                        </div>
                      </article>
                    ))}
                    {detail?.staged_outputs.length === 0 ? <p className="text-sm text-[var(--muted-foreground)]">暂无 staged output</p> : null}
                  </div>
                </section>
              </>
            ) : (
              <p className="text-sm text-[var(--muted-foreground)]">暂无选中 Run</p>
            )}
          </CardContent>
        </Card>
      </div>

      <details className={cn(detailsClass, "bg-[var(--card)]")} aria-label="Agent memory">
        <summary>项目记忆 / Memory Versions（按需展开）</summary>
        <div className="mt-4 grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <Label>Curated Markdown</Label>
              <Textarea value={memoryContent} rows={6} onChange={(event) => setMemoryContent(event.target.value)} />
            </div>
            <Button variant="outline" type="button" onClick={() => void handleCurateMemory()} disabled={busy || !selectedProjectId} className="self-start">
              <Save size={16} aria-hidden="true" />
              保存记忆
            </Button>
          </div>
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <Label>Search</Label>
              <Input value={memoryQuery} onChange={(event) => setMemoryQuery(event.target.value)} />
            </div>
            <Button variant="outline" type="button" onClick={() => void handleMemorySearch()} disabled={busy || !selectedWorkspaceId} className="self-start">
              <Search size={16} aria-hidden="true" />
              搜索
            </Button>
            <div className="flex flex-col gap-2 max-h-64 overflow-y-auto">
              {memoryResults.map((result) => (
                <article className="rounded-md border border-[var(--border)] bg-[var(--muted)]/20 p-3 flex flex-col gap-2" key={result.memory_file.id}>
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex flex-col gap-1">
                      <strong className="text-sm">{result.memory_file.scope} · v{result.memory_file.current_version}</strong>
                      <span className="text-xs text-[var(--muted-foreground)] line-clamp-2">{result.snippet}</span>
                    </div>
                    <Button variant="outline" size="sm" type="button" onClick={() => void handleMemoryVersionSelect(result.memory_file)} disabled={busy}>
                      版本
                    </Button>
                  </div>
                  <small className="text-xs font-mono text-[var(--muted-foreground)] truncate">{result.memory_file.path}</small>
                </article>
              ))}
              {memoryResults.length === 0 ? <p className="text-sm text-[var(--muted-foreground)]">暂无 memory result</p> : null}
            </div>
            <section className="rounded-md border border-[var(--border)] p-4 flex flex-col gap-3" aria-label="Memory version history">
              <div className="flex items-center justify-between gap-2">
                <div>
                  <p className={eyebrowClass}>Versions</p>
                  <h3 className="font-heading text-sm font-bold">{selectedMemoryFile ? `${selectedMemoryFile.scope} · v${selectedMemoryFile.current_version}` : "未选择 memory"}</h3>
                </div>
                <RotateCcw size={16} className="text-[var(--muted-foreground)]" aria-hidden="true" />
              </div>
              <div className="flex flex-col gap-2 max-h-48 overflow-y-auto">
                {memoryVersions.map((version) => (
                  <article className="flex items-start justify-between gap-2 p-2 rounded-md border border-[var(--border)] text-sm" key={version.id}>
                    <div className="min-w-0 flex flex-col gap-0.5">
                      <strong className="text-sm">v{version.version} · {version.patch_summary || "memory update"}</strong>
                      <small className="text-xs text-[var(--muted-foreground)]">{formatDate(version.created_at)} · {version.editor || "system"} · {version.reason || "no reason"}</small>
                      <small className="text-xs font-mono text-[var(--muted-foreground)]">{version.checksum.slice(0, 12)}</small>
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      type="button"
                      onClick={() => void handleMemoryRollback(version.version)}
                      disabled={busy || !selectedMemoryFile || version.version === selectedMemoryFile.current_version}
                      className="shrink-0"
                    >
                      回滚
                    </Button>
                  </article>
                ))}
                {memoryVersions.length === 0 ? <p className="text-sm text-[var(--muted-foreground)]">暂无 version history</p> : null}
              </div>
            </section>
          </div>
        </div>
      </details>
    </div>
  );
}
