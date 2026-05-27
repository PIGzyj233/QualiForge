import { requestJson } from "./client";
import type { AIInvocationRecord } from "./ai";

export type AgentRunStatus = "queued" | "running" | "waiting_for_user" | "succeeded" | "failed" | "cancelled";

export type AgentRunMode = "preview" | "execute";

export type AgentConversationRecord = {
  id: string;
  workspace_id: string;
  project_id: string | null;
  title: string;
  status: "active" | "archived";
  created_by: string;
  created_at: string;
  updated_at: string;
};

export type AgentRunRecord = {
  id: string;
  conversation_id: string;
  workspace_id: string;
  project_id: string | null;
  goal: string;
  mode: AgentRunMode;
  trigger_type: string;
  status: AgentRunStatus;
  current_phase: string;
  created_by: string;
  temporal_workflow_id: string;
  langgraph_thread_id: string;
  budget_snapshot: Record<string, unknown>;
  failure_reason: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
};

export type AgentToolCallRecord = {
  id: string;
  agent_run_id: string;
  parent_tool_call_id: string | null;
  subagent_name: string;
  tool_name: string;
  permission_level: string;
  input_summary: string;
  output_summary: string;
  status: "queued" | "running" | "succeeded" | "failed";
  idempotency_key: string;
  duration_ms: number;
  error_summary: string;
  created_at: string;
  completed_at: string | null;
};

export type AgentRepositorySandboxRecord = {
  id: string;
  agent_run_id: string;
  repository_id: string;
  workspace_id: string;
  project_id: string | null;
  ref: string;
  resolved_ref: string;
  worktree_path: string;
  status: "preparing" | "ready" | "failed" | "cleaned";
  error_summary: string;
  created_at: string;
  cleaned_at: string | null;
};

export type AgentCoverageEntryRecord = {
  id: string;
  workspace_id: string;
  project_id: string | null;
  source_type: string;
  source_id: string;
  coverage_state: string;
  module_id: string | null;
  module_key: string;
  behavior_summary: string;
  signals: Record<string, unknown>[];
  evidence_refs: Record<string, unknown>[];
  confidence: number;
  verified_by_human: boolean;
  created_at: string;
  updated_at: string;
};

export type AgentStagedOutputRecord = {
  id: string;
  agent_run_id: string;
  workspace_id: string;
  project_id: string | null;
  output_type:
    | "case_candidate"
    | "regression_recommendation"
    | "report_draft"
    | "coverage_update"
    | "agent_note"
    | "module_tree_draft"
    | "module_mapping_suggestions"
    | "module_refactor_suggestion";
  status: "staged" | "accepted" | "rejected";
  idempotency_key: string;
  title: string;
  payload: Record<string, unknown>;
  evidence_refs: Record<string, unknown>[];
  quality_result: Record<string, unknown>;
  duplicate_result: Record<string, unknown>;
  created_at: string;
  decided_by: string;
  decision_summary: string;
  accepted_at: string | null;
  rejected_at: string | null;
  coverage_entries: AgentCoverageEntryRecord[];
};

export type AgentApprovalRecord = {
  id: string;
  agent_run_id: string;
  approval_type: string;
  status: "pending" | "approved" | "rejected" | "cancelled";
  requested_by: string;
  decided_by: string;
  request_summary: string;
  decision_summary: string;
  created_at: string;
  decided_at: string | null;
};

export type AgentRunBudgetRecord = {
  snapshot: Record<string, unknown>;
  usage: Record<string, unknown>;
  limits: Record<string, unknown>;
};

export type AgentSubagentRunRecord = {
  id: string;
  agent_run_id: string;
  workspace_id: string;
  project_id: string | null;
  subagent_name: string;
  stage: string;
  parallel_group: string;
  status: "queued" | "running" | "succeeded" | "failed" | "skipped";
  summary: string;
  input_summary: string;
  output_summary: string;
  result_snapshot: Record<string, unknown>;
  duration_ms: number;
  error_summary: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
};

export type AgentRunExecuteResponse = {
  run: AgentRunRecord;
  summary: string;
  staged_outputs: AgentStagedOutputRecord[];
  tool_calls: AgentToolCallRecord[];
  sandboxes: AgentRepositorySandboxRecord[];
};

export type AgentExecutionDetailRecord = {
  run: AgentRunRecord;
  staged_outputs: AgentStagedOutputRecord[];
  tool_calls: AgentToolCallRecord[];
  subagent_runs: AgentSubagentRunRecord[];
  ai_invocations: AIInvocationRecord[];
  repository_sandboxes: AgentRepositorySandboxRecord[];
  budget: AgentRunBudgetRecord;
  pending_approvals: AgentApprovalRecord[];
};

export type AgentBudgetPolicyRecord = {
  id: string;
  workspace_id: string;
  project_id: string | null;
  scope: "workspace" | "project";
  purpose: string;
  defaults: Record<string, unknown>;
  hard_caps: Record<string, unknown>;
  updated_by: string;
  created_at: string;
  updated_at: string;
};

export type AgentMemoryFileRecord = {
  id: string;
  workspace_id: string;
  project_id: string | null;
  user_id: string;
  scope: "workspace" | "project" | "user" | "dreams" | "daily_project";
  path: string;
  current_version: number;
  checksum: string;
  updated_by: string;
  updated_at: string;
};

export type AgentMemoryVersionRecord = {
  id: string;
  memory_file_id: string;
  version: number;
  patch_summary: string;
  editor: string;
  reason: string;
  checksum: string;
  created_at: string;
};

export type AgentMemorySearchResult = {
  memory_file: AgentMemoryFileRecord;
  score: number;
  snippet: string;
};

export function listAgentConversations(workspaceId: string, projectId?: string): Promise<AgentConversationRecord[]> {
  const suffix = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
  return requestJson<AgentConversationRecord[]>(`/workspaces/${workspaceId}/agent/conversations${suffix}`);
}

export function createAgentConversation(
  workspaceId: string,
  actorEmail: string,
  payload: { title: string; project_id?: string | null }
): Promise<AgentConversationRecord> {
  return requestJson<AgentConversationRecord>(`/workspaces/${workspaceId}/agent/conversations?actor_email=${encodeURIComponent(actorEmail)}`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function listAgentRuns(
  workspaceId: string,
  filters?: { projectId?: string; status?: AgentRunStatus }
): Promise<AgentRunRecord[]> {
  const params = new URLSearchParams();
  if (filters?.projectId) params.set("project_id", filters.projectId);
  if (filters?.status) params.set("status", filters.status);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<AgentRunRecord[]>(`/workspaces/${workspaceId}/agent/runs${suffix}`);
}

export function listAgentBudgetPolicies(
  workspaceId: string,
  filters?: { projectId?: string; purpose?: string }
): Promise<AgentBudgetPolicyRecord[]> {
  const params = new URLSearchParams();
  if (filters?.projectId) params.set("project_id", filters.projectId);
  if (filters?.purpose) params.set("purpose", filters.purpose);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<AgentBudgetPolicyRecord[]>(`/workspaces/${workspaceId}/agent/budget-policies${suffix}`);
}

export function upsertAgentBudgetPolicy(
  workspaceId: string,
  actorEmail: string,
  payload: {
    scope: "workspace" | "project";
    project_id?: string | null;
    purpose?: string;
    defaults: Record<string, unknown>;
    hard_caps?: Record<string, unknown>;
  }
): Promise<AgentBudgetPolicyRecord> {
  return requestJson<AgentBudgetPolicyRecord>(`/workspaces/${workspaceId}/agent/budget-policies?actor_email=${encodeURIComponent(actorEmail)}`, {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

export function listAgentMemoryFiles(
  workspaceId: string,
  filters?: { projectId?: string; scope?: string }
): Promise<AgentMemoryFileRecord[]> {
  const params = new URLSearchParams();
  if (filters?.projectId) params.set("project_id", filters.projectId);
  if (filters?.scope) params.set("scope", filters.scope);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<AgentMemoryFileRecord[]>(`/workspaces/${workspaceId}/agent/memory/files${suffix}`);
}

export function searchAgentMemory(
  workspaceId: string,
  filters: { query?: string; projectId?: string; scope?: string; limit?: number }
): Promise<AgentMemorySearchResult[]> {
  const params = new URLSearchParams();
  if (filters.query) params.set("query", filters.query);
  if (filters.projectId) params.set("project_id", filters.projectId);
  if (filters.scope) params.set("scope", filters.scope);
  if (filters.limit) params.set("limit", String(filters.limit));
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<AgentMemorySearchResult[]>(`/workspaces/${workspaceId}/agent/memory/search${suffix}`);
}

export function curateAgentMemory(
  workspaceId: string,
  actorEmail: string,
  payload: {
    scope: "workspace" | "project" | "user" | "dreams";
    project_id?: string | null;
    user_id?: string;
    content: string;
    reason?: string;
    patch_summary?: string;
  }
): Promise<AgentMemoryFileRecord> {
  return requestJson<AgentMemoryFileRecord>(`/workspaces/${workspaceId}/agent/memory/curate?actor_email=${encodeURIComponent(actorEmail)}`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function listAgentMemoryVersions(workspaceId: string, memoryFileId: string): Promise<AgentMemoryVersionRecord[]> {
  return requestJson<AgentMemoryVersionRecord[]>(`/workspaces/${workspaceId}/agent/memory/files/${memoryFileId}/versions`);
}

export function rollbackAgentMemory(
  workspaceId: string,
  memoryFileId: string,
  actorEmail: string,
  payload: { target_version: number; reason?: string }
): Promise<AgentMemoryFileRecord> {
  return requestJson<AgentMemoryFileRecord>(
    `/workspaces/${workspaceId}/agent/memory/files/${memoryFileId}/rollback?actor_email=${encodeURIComponent(actorEmail)}`,
    {
      method: "POST",
      body: JSON.stringify(payload)
    }
  );
}

export function createAgentRun(
  workspaceId: string,
  conversationId: string,
  actorEmail: string,
  payload: { goal: string; mode: AgentRunMode; project_id?: string | null; budget_snapshot?: Record<string, unknown> }
): Promise<AgentRunRecord> {
  return requestJson<AgentRunRecord>(
    `/workspaces/${workspaceId}/agent/conversations/${conversationId}/runs?actor_email=${encodeURIComponent(actorEmail)}`,
    {
      method: "POST",
      body: JSON.stringify(payload)
    }
  );
}

export function executeAgentRun(
  workspaceId: string,
  runId: string,
  actorEmail: string,
  payload: { repository_id: string; ref?: string; candidate_limit?: number }
): Promise<AgentRunExecuteResponse> {
  return requestJson<AgentRunExecuteResponse>(
    `/workspaces/${workspaceId}/agent/runs/${runId}/execute?actor_email=${encodeURIComponent(actorEmail)}`,
    {
      method: "POST",
      body: JSON.stringify(payload)
    }
  );
}

export function getAgentExecutionDetail(workspaceId: string, runId: string): Promise<AgentExecutionDetailRecord> {
  return requestJson<AgentExecutionDetailRecord>(`/workspaces/${workspaceId}/agent/runs/${runId}/execution-detail`);
}

export function resumeAgentRun(
  workspaceId: string,
  runId: string,
  actorEmail: string,
  payload: { budget_snapshot: Record<string, unknown>; resume_reason?: string }
): Promise<AgentRunExecuteResponse> {
  return requestJson<AgentRunExecuteResponse>(
    `/workspaces/${workspaceId}/agent/runs/${runId}/resume?actor_email=${encodeURIComponent(actorEmail)}`,
    {
      method: "POST",
      body: JSON.stringify(payload)
    }
  );
}

export function cancelAgentRun(workspaceId: string, runId: string, actorEmail: string, cancelReason: string): Promise<AgentRunRecord> {
  return requestJson<AgentRunRecord>(`/workspaces/${workspaceId}/agent/runs/${runId}/cancel?actor_email=${encodeURIComponent(actorEmail)}`, {
    method: "POST",
    body: JSON.stringify({ cancel_reason: cancelReason })
  });
}

export function decideAgentStagedOutput(
  workspaceId: string,
  outputId: string,
  actorEmail: string,
  payload: { status: "accepted" | "rejected"; decision_summary?: string }
): Promise<AgentStagedOutputRecord> {
  return requestJson<AgentStagedOutputRecord>(
    `/workspaces/${workspaceId}/agent/staged-outputs/${outputId}?actor_email=${encodeURIComponent(actorEmail)}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload)
    }
  );
}

export function decideAgentApproval(
  workspaceId: string,
  approvalId: string,
  actorEmail: string,
  payload: { status: "approved" | "rejected" | "cancelled"; decision_summary?: string }
): Promise<AgentApprovalRecord> {
  return requestJson<AgentApprovalRecord>(
    `/workspaces/${workspaceId}/agent/approvals/${approvalId}?actor_email=${encodeURIComponent(actorEmail)}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload)
    }
  );
}
