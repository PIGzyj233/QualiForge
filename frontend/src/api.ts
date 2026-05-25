const API_BASE = import.meta.env.VITE_API_URL ?? "/api";

export type CaseStep = {
  action: string;
  expected: string;
};

export type HealthPayload = {
  status: "ok" | "degraded";
  service: string;
  environment: string;
  checked_at: string;
  services: Record<string, { status: string; detail: string }>;
};

export type DashboardSummary = {
  workspace: string;
  mvp_stage: string;
  work_items: Array<{
    issue: string;
    title: string;
    status: "done" | "in_progress" | "next" | "blocked";
    owner: string;
    blocked_by: string[];
  }>;
  queues: Array<{ label: string; value: number; trend: string }>;
  recent_jobs: Array<{ type: string; status: string; summary: string; created_at: string }>;
};

export type LoginPayload = {
  email: string;
  display_name: string;
  workspace_name: string;
};

export type Session = {
  access_token: string;
  token_type: string;
  user: { email: string; display_name: string; role: string };
  workspace: { id: string; name: string };
};

export type WorkspaceRecord = {
  id: string;
  name: string;
  owner_email: string;
  created_at: string;
  updated_at: string;
};

export type MemberRecord = {
  id: string;
  workspace_id: string;
  email: string;
  display_name: string;
  role: "WorkspaceOwner" | "WorkspaceMember";
  created_at: string;
};

export type ProjectRecord = {
  id: string;
  workspace_id: string;
  name: string;
  key: string;
  description: string;
  status: "active" | "archived";
  created_at: string;
  updated_at: string;
};

export type AuditLogRecord = {
  id: string;
  workspace_id: string;
  actor_email: string;
  action: string;
  entity_type: string;
  entity_id: string;
  summary: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  created_at: string;
};

export type AIDataPolicy = "ExternalAllowed" | "NoSourceCode" | "InternalOnly" | "AIDisabled";
export type AIPurpose = "import_cleanup" | "diff_analysis" | "case_generation" | "report_summary";

export type AISettingsRecord = {
  id: string;
  workspace_id: string;
  data_policy: AIDataPolicy;
  updated_by: string;
  created_at: string;
  updated_at: string;
};

export type LLMProviderRecord = {
  id: string;
  workspace_id: string;
  name: string;
  api_base_url: string;
  api_key_masked: string;
  has_api_key: boolean;
  default_headers: Record<string, string>;
  organization: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type ModelProfileRecord = {
  id: string;
  workspace_id: string;
  provider_id: string;
  purpose: AIPurpose;
  model_name: string;
  reasoning_effort: "low" | "medium" | "high" | "xhigh";
  max_context_tokens: number;
  max_output_tokens: number;
  input_token_price: string;
  output_token_price: string;
  cache_policy: "disabled" | "prompt" | "semantic";
  timeout_seconds: number;
  retry_count: number;
  budget_limit: string;
  created_at: string;
  updated_at: string;
};

export type AIInvocationRecord = {
  id: string;
  workspace_id: string;
  provider_id: string | null;
  model_profile_id: string | null;
  agent_run_id: string | null;
  tool_call_id: string | null;
  actor_email: string;
  purpose: AIPurpose;
  data_policy: AIDataPolicy;
  provider_name: string;
  model_alias: string;
  model_name: string;
  prompt_hash: string;
  prompt_version: string;
  subagent_name: string;
  status: "queued" | "rejected" | "succeeded" | "failed";
  input_summary: string;
  input_data_types: string[];
  includes_source_code: boolean;
  token_prompt: number;
  token_completion: number;
  estimated_cost: string;
  cache_hit: boolean;
  latency_ms: number;
  attempts: number;
  usage: Record<string, unknown>;
  raw_invocation_id: string;
  failure_reason: string;
  created_at: string;
  completed_at: string | null;
};

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
  output_type: "case_candidate" | "regression_recommendation" | "report_draft" | "coverage_update" | "agent_note";
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

export type GitLabTokenRecord = {
  id: string;
  workspace_id: string;
  gitlab_base_url: string;
  token_masked: string;
  has_token: boolean;
  updated_by: string;
  created_at: string;
  updated_at: string;
};

export type GitRepositoryRecord = {
  id: string;
  workspace_id: string;
  project_id: string;
  name: string;
  remote_url: string;
  default_branch: string;
  mirror_path: string;
  status: "pending" | "synced" | "sync_failed";
  last_synced_at: string | null;
  repo_size_limit_mb: number;
  diff_file_limit: number;
  sync_timeout_seconds: number;
  created_at: string;
  updated_at: string;
};

export type JobRecord = {
  id: string;
  workspace_id: string;
  project_id: string | null;
  repository_id: string | null;
  job_type: string;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  created_by: string;
  input_summary: string;
  output_summary: string;
  error_summary: string;
  key_logs: string[];
  timeout_seconds: number;
  repo_size_limit_mb: number;
  diff_file_limit: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type DiffStructureChange = {
  type: string;
  name: string;
  state: string;
  evidence?: string;
};

export type DiffFileChange = {
  path: string;
  old_path: string | null;
  directory: string;
  language: string;
  change_type: "added" | "modified" | "deleted" | "renamed";
  additions: number;
  deletions: number;
  module_id: string | null;
  module_key: string | null;
  module_name: string | null;
  is_test_file: boolean;
  is_migration: boolean;
  structure_changes: DiffStructureChange[];
  risk_level: "low" | "medium" | "high";
  confidence: number;
  evidence: string[];
};

export type DiffModuleImpact = {
  module_id: string | null;
  module_key: string;
  module_name: string;
  risk_level: "low" | "medium" | "high";
  changed_file_count: number;
  recommended_tests: string[];
  evidence: string[];
  confidence: number;
};

export type DiffAnalysisRecord = {
  id: string;
  workspace_id: string;
  project_id: string;
  repository_id: string;
  job_id: string;
  base_ref: string;
  target_ref: string;
  status: "running" | "succeeded" | "failed";
  risk_level: "low" | "medium" | "high";
  summary: string;
  recommended_scope: string[];
  file_changes: DiffFileChange[];
  module_impacts: DiffModuleImpact[];
  key_logs: string[];
  error_summary: string;
  created_by: string;
  created_at: string;
  completed_at: string | null;
};

export type AISuggestionStatus = "suggested" | "accepted" | "ignored" | "modified";
export type AISuggestionType = "regression" | "case_candidate";

export type AISuggestionRecord = {
  id: string;
  workspace_id: string;
  project_id: string;
  diff_analysis_id: string;
  suggestion_type: AISuggestionType;
  status: AISuggestionStatus;
  title: string;
  rationale: string;
  confidence: number;
  module_id: string | null;
  module_key: string;
  source_diff: Record<string, unknown>;
  mapping_evidence: string[];
  code_paths: string[];
  interfaces: string[];
  config_keys: string[];
  related_case_ids: string[];
  selected_case_ids: string[];
  candidate_payload: TestCasePayload & { custom_fields: Record<string, string> };
  candidate_case_id: string | null;
  plan_item_ids: string[];
  feedback_history: Array<{ actor_email: string; comment: string; created_at: string }>;
  created_by: string;
  created_at: string;
  updated_at: string;
};

export type TestPlanRecord = {
  id: string;
  workspace_id: string;
  project_id: string;
  name: string;
  plan_type: "release" | "regression" | "smoke" | "feature" | "custom";
  status: "draft" | "in_progress" | "completed" | "archived";
  scope_summary: string;
  version_ref: string;
  owner_email: string;
  final_conclusion: string;
  created_by: string;
  created_at: string;
  updated_at: string;
};

export type PlanItemRecord = {
  id: string;
  workspace_id: string;
  project_id: string;
  plan_id: string;
  source_type: "formal_case" | "ai_temp" | "manual";
  source_id: string | null;
  title: string;
  snapshot: Record<string, unknown>;
  rationale: string;
  status: "not_run" | "passed" | "failed" | "blocked" | "skipped" | "todo" | "in_progress";
  assignee_email: string;
  actual_result: string;
  failure_reason: string;
  defect_links: string[];
  evidence: Array<{
    id: string;
    file_name: string;
    content_type: string;
    size_bytes: number;
    storage_path: string;
    note: string;
    uploaded_by: string;
    uploaded_at: string;
  }>;
  executed_by: string | null;
  executed_at: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
};

export type ReleaseReportRecord = {
  id: string;
  workspace_id: string;
  project_id: string;
  plan_id: string;
  title: string;
  status: "draft" | "confirmed";
  version_ref: string;
  sections: Record<string, unknown>;
  ai_notes: string[];
  release_suggestion: string;
  release_decision: string;
  decision_comment: string;
  confirmed_by: string | null;
  confirmed_at: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
};

export type MappingRuleType =
  | "directory"
  | "file"
  | "api"
  | "service"
  | "config_key"
  | "database_migration"
  | "keyword";

export type MappingSource = "manual" | "ai_repository" | "ai_history" | "diff_confirmation";

export type ModuleMappingRuleRecord = {
  id: string;
  workspace_id: string;
  project_id: string;
  module_id: string;
  rule_type: MappingRuleType;
  pattern: string;
  source: MappingSource;
  description: string;
  confidence: number;
  created_at: string;
  updated_at: string;
};

export type ProjectModuleRecord = {
  id: string;
  workspace_id: string;
  project_id: string;
  parent_id: string | null;
  key: string;
  name: string;
  slug: string;
  code: string;
  path: string;
  path_label: string;
  depth: number;
  sort_order: number;
  status: "active" | "archived";
  description: string;
  owner: string;
  reference_count: number;
  mapping_rules: ModuleMappingRuleRecord[];
  created_at: string;
  updated_at: string;
};

export type ModuleTreeNode = ProjectModuleRecord & { children: ModuleTreeNode[] };

export type ImportBatchRecord = {
  id: string;
  workspace_id: string;
  project_id: string;
  job_id: string | null;
  file_name: string;
  file_type: "csv" | "xlsx";
  original_file_path: string;
  status: "uploaded" | "preview_ready" | "review_submitted" | "imported" | "failed";
  created_by: string;
  row_count: number;
  raw_rows: Record<string, unknown>[];
  ai_conversion_result: Record<string, unknown>[];
  manual_changes: Record<string, unknown>[];
  error_summary: string;
  created_at: string;
  updated_at: string;
  submitted_at: string | null;
  imported_at: string | null;
};

export type ImportDraftRecord = {
  id: string;
  workspace_id: string;
  project_id: string;
  batch_id: string;
  module_id: string | null;
  test_case_id: string | null;
  case_draft_id: string | null;
  review_cycle_id: string | null;
  title: string;
  steps: CaseStep[];
  priority: string;
  risk: string;
  tags: string[];
  custom_fields: Record<string, string>;
  source_row_index: number;
  raw_row: Record<string, unknown>;
  ai_confidence: number;
  status: "draft" | "review_submitted" | "imported";
  created_at: string;
  updated_at: string;
};

export type TestCaseRecord = {
  id: string;
  workspace_id: string;
  project_id: string;
  lifecycle_status: "draft" | "active" | "archived";
  current_revision_id: string | null;
  current_revision_number: number;
  current_module_id: string | null;
  source_type: "manual" | "import" | "ai_suggestion" | "active_edit" | string;
  source_ref: Record<string, unknown>;
  created_by: string;
  created_at: string;
  updated_at: string;
  title: string;
  module_id: string | null;
  module_path_label: string;
  review_status: "pending_review" | "changes_requested" | "approved" | "rejected" | "cancelled" | null;
  active_draft: CaseDraftRecord | null;
  current_revision: CaseRevisionRecord | null;
  open_cycle: ReviewCycleRecord | null;
  revisions?: CaseRevisionRecord[];
  review_cycles?: ReviewCycleRecord[];
  review_events?: CaseReviewRecord[];
};

export type ImportResultRecord = {
  batch: ImportBatchRecord;
  imported_count: number;
};

export type ReviewSettingsRecord = {
  id: string;
  workspace_id: string;
  allow_self_review: boolean;
  require_review_on_case_update: boolean;
  allow_direct_revision_for_active_case: boolean;
  direct_revision_roles: string[];
  updated_by: string;
  created_at: string;
  updated_at: string;
};

export type CaseReviewAction = "submitted" | "approved" | "rejected" | "changes_requested" | "changes_addressed" | "commented";

export type CaseDraftRecord = {
  id: string;
  test_case_id: string;
  workspace_id: string;
  project_id: string;
  base_revision_id: string | null;
  module_id: string | null;
  title: string;
  steps: CaseStep[];
  priority: string;
  risk: string;
  tags: string[];
  custom_fields: Record<string, unknown>;
  draft_status: "editing" | "in_review" | "consumed" | "cancelled";
  source_type: "manual" | "import" | "ai_suggestion" | "active_edit" | string;
  source_ref: Record<string, unknown>;
  created_by: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
};

export type ReviewCycleRecord = {
  id: string;
  workspace_id: string;
  project_id: string;
  test_case_id: string;
  draft_id: string;
  status: "pending_review" | "changes_requested" | "approved" | "rejected" | "cancelled";
  submitted_by: string;
  closed_by: string;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
};

export type CaseReviewRecord = {
  id: string;
  workspace_id: string;
  project_id: string;
  test_case_id: string;
  cycle_id: string | null;
  draft_id: string | null;
  revision_id: string | null;
  actor_email: string;
  action: CaseReviewAction;
  comment: string;
  diff_summary: Record<string, unknown> | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  created_at: string;
};

export type CaseRevisionRecord = {
  id: string;
  workspace_id: string;
  project_id: string;
  test_case_id: string;
  revision_number: number;
  module_id: string | null;
  module_path_label: string;
  content_snapshot: Record<string, unknown>;
  change_summary: string;
  created_by: string;
  created_at: string;
};

export type TestCasePayload = {
  module_id?: string | null;
  title: string;
  steps: CaseStep[];
  priority: string;
  risk: string;
  tags: string[];
  custom_fields: Record<string, unknown>;
  source_type?: "manual" | "import" | "ai_suggestion" | "active_edit";
  source_ref?: Record<string, unknown>;
};

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init
  });

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;
    try {
      const payload = (await response.json()) as { detail?: string };
      detail = payload.detail ?? detail;
    } catch {
      // Keep the HTTP status fallback when the response is not JSON.
    }
    throw new Error(detail);
  }

  return response.json() as Promise<T>;
}

async function requestNoContent(path: string, init?: RequestInit): Promise<void> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init
  });

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;
    try {
      const payload = (await response.json()) as { detail?: string };
      detail = payload.detail ?? detail;
    } catch {
      // Keep the HTTP status fallback when the response is not JSON.
    }
    throw new Error(detail);
  }
}

async function requestFormJson<T>(path: string, init: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;
    try {
      const payload = (await response.json()) as { detail?: string };
      detail = payload.detail ?? detail;
    } catch {
      // Keep the HTTP status fallback when the response is not JSON.
    }
    throw new Error(detail);
  }

  return response.json() as Promise<T>;
}

export function login(payload: LoginPayload): Promise<Session> {
  return requestJson<Session>("/auth/login", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function getHealth(): Promise<HealthPayload> {
  return requestJson<HealthPayload>("/health/detailed");
}

export function getDashboardSummary(): Promise<DashboardSummary> {
  return requestJson<DashboardSummary>("/dashboard/summary");
}

export function listWorkspaces(actorEmail: string): Promise<WorkspaceRecord[]> {
  return requestJson<WorkspaceRecord[]>(`/workspaces?actor_email=${encodeURIComponent(actorEmail)}`);
}

export function createWorkspace(payload: {
  name: string;
  owner_email: string;
  owner_display_name: string;
}): Promise<WorkspaceRecord> {
  return requestJson<WorkspaceRecord>("/workspaces", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function listMembers(workspaceId: string): Promise<MemberRecord[]> {
  return requestJson<MemberRecord[]>(`/workspaces/${workspaceId}/members`);
}

export function getCurrentMember(workspaceId: string, actorEmail: string): Promise<MemberRecord> {
  return requestJson<MemberRecord>(`/workspaces/${workspaceId}/members/me?actor_email=${encodeURIComponent(actorEmail)}`);
}

export function addMember(
  workspaceId: string,
  actorEmail: string,
  payload: { email: string; display_name: string; role: "WorkspaceOwner" | "WorkspaceMember" }
): Promise<MemberRecord> {
  return requestJson<MemberRecord>(`/workspaces/${workspaceId}/members?actor_email=${encodeURIComponent(actorEmail)}`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function removeMember(workspaceId: string, memberId: string, actorEmail: string): Promise<void> {
  return requestNoContent(
    `/workspaces/${workspaceId}/members/${memberId}?actor_email=${encodeURIComponent(actorEmail)}`,
    { method: "DELETE" }
  );
}

export function listProjects(workspaceId: string): Promise<ProjectRecord[]> {
  return requestJson<ProjectRecord[]>(`/workspaces/${workspaceId}/projects`);
}

export function createProject(
  workspaceId: string,
  actorEmail: string,
  payload: { name: string; key: string; description: string }
): Promise<ProjectRecord> {
  return requestJson<ProjectRecord>(`/workspaces/${workspaceId}/projects?actor_email=${encodeURIComponent(actorEmail)}`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function updateProject(
  workspaceId: string,
  projectId: string,
  actorEmail: string,
  payload: { name?: string; description?: string; status?: "active" | "archived" }
): Promise<ProjectRecord> {
  return requestJson<ProjectRecord>(
    `/workspaces/${workspaceId}/projects/${projectId}?actor_email=${encodeURIComponent(actorEmail)}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload)
    }
  );
}

export function listAuditLogs(workspaceId: string, actorEmail: string): Promise<AuditLogRecord[]> {
  return requestJson<AuditLogRecord[]>(`/workspaces/${workspaceId}/audit-logs?actor_email=${encodeURIComponent(actorEmail)}`);
}

export function getAISettings(workspaceId: string): Promise<AISettingsRecord> {
  return requestJson<AISettingsRecord>(`/workspaces/${workspaceId}/ai-settings`);
}

export function updateAISettings(workspaceId: string, actorEmail: string, dataPolicy: AIDataPolicy): Promise<AISettingsRecord> {
  return requestJson<AISettingsRecord>(`/workspaces/${workspaceId}/ai-settings?actor_email=${encodeURIComponent(actorEmail)}`, {
    method: "PUT",
    body: JSON.stringify({ data_policy: dataPolicy })
  });
}

export function listLLMProviders(workspaceId: string): Promise<LLMProviderRecord[]> {
  return requestJson<LLMProviderRecord[]>(`/workspaces/${workspaceId}/llm-providers`);
}

export function createLLMProvider(
  workspaceId: string,
  actorEmail: string,
  payload: {
    name: string;
    api_base_url: string;
    api_key: string;
    default_headers: Record<string, string>;
    organization: string;
  }
): Promise<LLMProviderRecord> {
  return requestJson<LLMProviderRecord>(`/workspaces/${workspaceId}/llm-providers?actor_email=${encodeURIComponent(actorEmail)}`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function listModelProfiles(workspaceId: string): Promise<ModelProfileRecord[]> {
  return requestJson<ModelProfileRecord[]>(`/workspaces/${workspaceId}/model-profiles`);
}

export function upsertModelProfile(
  workspaceId: string,
  actorEmail: string,
  payload: {
    provider_id: string;
    purpose: AIPurpose;
    model_name: string;
    reasoning_effort: "low" | "medium" | "high" | "xhigh";
    max_context_tokens: number;
    max_output_tokens: number;
    input_token_price: string;
    output_token_price: string;
    cache_policy: "disabled" | "prompt" | "semantic";
    timeout_seconds: number;
    retry_count: number;
    budget_limit: string;
  }
): Promise<ModelProfileRecord> {
  return requestJson<ModelProfileRecord>(`/workspaces/${workspaceId}/model-profiles?actor_email=${encodeURIComponent(actorEmail)}`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function startAIInvocation(
  workspaceId: string,
  actorEmail: string,
  payload: {
    purpose: AIPurpose;
    input_summary: string;
    input_data_types: string[];
    includes_source_code: boolean;
  }
): Promise<AIInvocationRecord> {
  return requestJson<AIInvocationRecord>(`/workspaces/${workspaceId}/ai-invocations?actor_email=${encodeURIComponent(actorEmail)}`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function completeAIInvocation(
  workspaceId: string,
  invocationId: string,
  actorEmail: string,
  payload: {
    status: "succeeded" | "failed";
    token_prompt: number;
    token_completion: number;
    cache_hit: boolean;
    latency_ms: number;
    failure_reason: string;
  }
): Promise<AIInvocationRecord> {
  return requestJson<AIInvocationRecord>(
    `/workspaces/${workspaceId}/ai-invocations/${invocationId}?actor_email=${encodeURIComponent(actorEmail)}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload)
    }
  );
}

export function listAIInvocations(workspaceId: string): Promise<AIInvocationRecord[]> {
  return requestJson<AIInvocationRecord[]>(`/workspaces/${workspaceId}/ai-invocations`);
}

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

export function getGitLabToken(workspaceId: string): Promise<GitLabTokenRecord | null> {
  return requestJson<GitLabTokenRecord | null>(`/workspaces/${workspaceId}/gitlab-token`);
}

export function upsertGitLabToken(
  workspaceId: string,
  actorEmail: string,
  payload: { gitlab_base_url: string; token: string }
): Promise<GitLabTokenRecord> {
  return requestJson<GitLabTokenRecord>(`/workspaces/${workspaceId}/gitlab-token?actor_email=${encodeURIComponent(actorEmail)}`, {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

export function listRepositories(workspaceId: string, projectId?: string): Promise<GitRepositoryRecord[]> {
  const suffix = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
  return requestJson<GitRepositoryRecord[]>(`/workspaces/${workspaceId}/repositories${suffix}`);
}

export function bindRepository(
  workspaceId: string,
  actorEmail: string,
  payload: {
    project_id: string;
    name: string;
    remote_url: string;
    default_branch: string;
    repo_size_limit_mb?: number;
    diff_file_limit?: number;
    sync_timeout_seconds?: number;
  }
): Promise<GitRepositoryRecord> {
  return requestJson<GitRepositoryRecord>(`/workspaces/${workspaceId}/repositories?actor_email=${encodeURIComponent(actorEmail)}`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function syncRepository(workspaceId: string, repositoryId: string, actorEmail: string): Promise<JobRecord> {
  return requestJson<JobRecord>(
    `/workspaces/${workspaceId}/repositories/${repositoryId}/sync?actor_email=${encodeURIComponent(actorEmail)}`,
    { method: "POST" }
  );
}

export function listJobs(workspaceId: string, repositoryId?: string): Promise<JobRecord[]> {
  const suffix = repositoryId ? `?repository_id=${encodeURIComponent(repositoryId)}` : "";
  return requestJson<JobRecord[]>(`/workspaces/${workspaceId}/jobs${suffix}`);
}

export function createDiffAnalysis(
  workspaceId: string,
  projectId: string,
  actorEmail: string,
  payload: { repository_id: string; base_ref: string; target_ref: string }
): Promise<DiffAnalysisRecord> {
  return requestJson<DiffAnalysisRecord>(
    `/workspaces/${workspaceId}/projects/${projectId}/diff-analyses?actor_email=${encodeURIComponent(actorEmail)}`,
    {
      method: "POST",
      body: JSON.stringify(payload)
    }
  );
}

export function listDiffAnalyses(workspaceId: string, projectId: string, repositoryId?: string): Promise<DiffAnalysisRecord[]> {
  const suffix = repositoryId ? `?repository_id=${encodeURIComponent(repositoryId)}` : "";
  return requestJson<DiffAnalysisRecord[]>(`/workspaces/${workspaceId}/projects/${projectId}/diff-analyses${suffix}`);
}

export function getDiffAnalysis(workspaceId: string, projectId: string, analysisId: string): Promise<DiffAnalysisRecord> {
  return requestJson<DiffAnalysisRecord>(`/workspaces/${workspaceId}/projects/${projectId}/diff-analyses/${analysisId}`);
}

export function generateAISuggestions(workspaceId: string, projectId: string, analysisId: string, actorEmail: string): Promise<AISuggestionRecord[]> {
  return requestJson<AISuggestionRecord[]>(
    `/workspaces/${workspaceId}/projects/${projectId}/diff-analyses/${analysisId}/ai-suggestions?actor_email=${encodeURIComponent(actorEmail)}`,
    { method: "POST" }
  );
}

export function listAISuggestions(workspaceId: string, projectId: string, analysisId: string): Promise<AISuggestionRecord[]> {
  return requestJson<AISuggestionRecord[]>(`/workspaces/${workspaceId}/projects/${projectId}/diff-analyses/${analysisId}/ai-suggestions`);
}

export function updateAISuggestion(
  workspaceId: string,
  projectId: string,
  suggestionId: string,
  actorEmail: string,
  payload: { status?: AISuggestionStatus; title?: string; feedback_comment?: string; selected_case_ids?: string[] }
): Promise<AISuggestionRecord> {
  return requestJson<AISuggestionRecord>(
    `/workspaces/${workspaceId}/projects/${projectId}/ai-suggestions/${suggestionId}?actor_email=${encodeURIComponent(actorEmail)}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload)
    }
  );
}

export function createCandidateFromSuggestion(
  workspaceId: string,
  projectId: string,
  suggestionId: string,
  actorEmail: string
): Promise<{ test_case: TestCaseRecord; suggestion: AISuggestionRecord }> {
  return requestJson<{ test_case: TestCaseRecord; suggestion: AISuggestionRecord }>(
    `/workspaces/${workspaceId}/projects/${projectId}/ai-suggestions/${suggestionId}/candidate?actor_email=${encodeURIComponent(actorEmail)}`,
    { method: "POST" }
  );
}

export function createSuggestionPlanItems(
  workspaceId: string,
  projectId: string,
  suggestionId: string,
  actorEmail: string,
  payload: { plan_id?: string; version_ref?: string; test_case_ids?: string[]; include_ai_candidate?: boolean }
): Promise<{ plan: Pick<TestPlanRecord, "id" | "name" | "plan_type" | "status" | "version_ref">; items: PlanItemRecord[]; suggestion: AISuggestionRecord }> {
  return requestJson<{ plan: Pick<TestPlanRecord, "id" | "name" | "plan_type" | "status" | "version_ref">; items: PlanItemRecord[]; suggestion: AISuggestionRecord }>(
    `/workspaces/${workspaceId}/projects/${projectId}/ai-suggestions/${suggestionId}/plan-items?actor_email=${encodeURIComponent(actorEmail)}`,
    {
      method: "POST",
      body: JSON.stringify(payload)
    }
  );
}

export function listTestPlans(workspaceId: string, projectId: string): Promise<TestPlanRecord[]> {
  return requestJson<TestPlanRecord[]>(`/workspaces/${workspaceId}/projects/${projectId}/plans`);
}

export function createTestPlan(
  workspaceId: string,
  projectId: string,
  actorEmail: string,
  payload: { name: string; plan_type: TestPlanRecord["plan_type"]; scope_summary?: string; version_ref?: string; owner_email?: string }
): Promise<TestPlanRecord> {
  return requestJson<TestPlanRecord>(
    `/workspaces/${workspaceId}/projects/${projectId}/plans?actor_email=${encodeURIComponent(actorEmail)}`,
    {
      method: "POST",
      body: JSON.stringify(payload)
    }
  );
}

export function listPlanItems(workspaceId: string, projectId: string, planId: string): Promise<PlanItemRecord[]> {
  return requestJson<PlanItemRecord[]>(`/workspaces/${workspaceId}/projects/${projectId}/plans/${planId}/items`);
}

export function createPlanItem(
  workspaceId: string,
  projectId: string,
  planId: string,
  actorEmail: string,
  payload: { source_type: PlanItemRecord["source_type"]; source_id?: string | null; title?: string; snapshot?: Record<string, unknown>; rationale?: string }
): Promise<PlanItemRecord> {
  return requestJson<PlanItemRecord>(
    `/workspaces/${workspaceId}/projects/${projectId}/plans/${planId}/items?actor_email=${encodeURIComponent(actorEmail)}`,
    {
      method: "POST",
      body: JSON.stringify(payload)
    }
  );
}

export function updatePlanItemExecution(
  workspaceId: string,
  projectId: string,
  planId: string,
  itemId: string,
  actorEmail: string,
  payload: {
    status: Exclude<PlanItemRecord["status"], "todo" | "in_progress">;
    assignee_email?: string | null;
    actual_result?: string;
    failure_reason?: string;
    defect_links?: string[];
  }
): Promise<PlanItemRecord> {
  return requestJson<PlanItemRecord>(
    `/workspaces/${workspaceId}/projects/${projectId}/plans/${planId}/items/${itemId}/execution?actor_email=${encodeURIComponent(actorEmail)}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload)
    }
  );
}

export function uploadPlanItemEvidence(
  workspaceId: string,
  projectId: string,
  planId: string,
  itemId: string,
  actorEmail: string,
  file: File,
  note: string
): Promise<PlanItemRecord> {
  const body = new FormData();
  body.append("file", file);
  body.append("note", note);
  return requestFormJson<PlanItemRecord>(
    `/workspaces/${workspaceId}/projects/${projectId}/plans/${planId}/items/${itemId}/evidence?actor_email=${encodeURIComponent(actorEmail)}`,
    {
      method: "POST",
      body
    }
  );
}

export function listReleaseReports(workspaceId: string, projectId: string, planId: string): Promise<ReleaseReportRecord[]> {
  return requestJson<ReleaseReportRecord[]>(`/workspaces/${workspaceId}/projects/${projectId}/plans/${planId}/reports`);
}

export function createReleaseReportDraft(workspaceId: string, projectId: string, planId: string, actorEmail: string): Promise<ReleaseReportRecord> {
  return requestJson<ReleaseReportRecord>(
    `/workspaces/${workspaceId}/projects/${projectId}/plans/${planId}/reports/draft?actor_email=${encodeURIComponent(actorEmail)}`,
    { method: "POST" }
  );
}

export function confirmReleaseReportDecision(
  workspaceId: string,
  projectId: string,
  reportId: string,
  actorEmail: string,
  payload: { release_decision: string; decision_comment?: string }
): Promise<ReleaseReportRecord> {
  return requestJson<ReleaseReportRecord>(
    `/workspaces/${workspaceId}/projects/${projectId}/reports/${reportId}/decision?actor_email=${encodeURIComponent(actorEmail)}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload)
    }
  );
}

export async function exportReleaseReportMarkdown(workspaceId: string, projectId: string, reportId: string): Promise<string> {
  const response = await fetch(`${API_BASE}/workspaces/${workspaceId}/projects/${projectId}/reports/${reportId}/markdown`);
  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }
  return response.text();
}

export function listModules(workspaceId: string, projectId: string, includeArchived = false): Promise<ProjectModuleRecord[]> {
  const suffix = includeArchived ? "?include_archived_modules=true" : "";
  return requestJson<ProjectModuleRecord[]>(`/workspaces/${workspaceId}/projects/${projectId}/modules${suffix}`);
}

export function listModuleTree(workspaceId: string, projectId: string, includeArchived = false): Promise<ModuleTreeNode[]> {
  const suffix = includeArchived ? "?include_archived_modules=true" : "";
  return requestJson<ModuleTreeNode[]>(`/workspaces/${workspaceId}/projects/${projectId}/modules/tree${suffix}`);
}

export function createModule(
  workspaceId: string,
  projectId: string,
  actorEmail: string,
  payload: { key?: string; code?: string; name: string; slug?: string; parent_id?: string | null; description: string; owner: string; sort_order?: number }
): Promise<ProjectModuleRecord> {
  return requestJson<ProjectModuleRecord>(
    `/workspaces/${workspaceId}/projects/${projectId}/modules?actor_email=${encodeURIComponent(actorEmail)}`,
    {
      method: "POST",
      body: JSON.stringify(payload)
    }
  );
}

export function updateModule(
  workspaceId: string,
  projectId: string,
  moduleId: string,
  actorEmail: string,
  payload: { name?: string; slug?: string; code?: string; parent_id?: string | null; description?: string; owner?: string; sort_order?: number; status?: "active" | "archived" }
): Promise<ProjectModuleRecord> {
  return requestJson<ProjectModuleRecord>(
    `/workspaces/${workspaceId}/projects/${projectId}/modules/${moduleId}?actor_email=${encodeURIComponent(actorEmail)}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload)
    }
  );
}

export function deleteModule(workspaceId: string, projectId: string, moduleId: string, actorEmail: string): Promise<void> {
  return requestNoContent(
    `/workspaces/${workspaceId}/projects/${projectId}/modules/${moduleId}?actor_email=${encodeURIComponent(actorEmail)}`,
    { method: "DELETE" }
  );
}

export function listMappingRules(
  workspaceId: string,
  projectId: string,
  filters?: { moduleId?: string; ruleType?: MappingRuleType; source?: MappingSource }
): Promise<ModuleMappingRuleRecord[]> {
  const params = new URLSearchParams();
  if (filters?.moduleId) params.set("module_id", filters.moduleId);
  if (filters?.ruleType) params.set("rule_type", filters.ruleType);
  if (filters?.source) params.set("source", filters.source);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<ModuleMappingRuleRecord[]>(`/workspaces/${workspaceId}/projects/${projectId}/mapping-rules${suffix}`);
}

export function createMappingRule(
  workspaceId: string,
  projectId: string,
  moduleId: string,
  actorEmail: string,
  payload: {
    rule_type: MappingRuleType;
    pattern: string;
    source: MappingSource;
    description: string;
    confidence: number;
  }
): Promise<ModuleMappingRuleRecord> {
  return requestJson<ModuleMappingRuleRecord>(
    `/workspaces/${workspaceId}/projects/${projectId}/modules/${moduleId}/mapping-rules?actor_email=${encodeURIComponent(actorEmail)}`,
    {
      method: "POST",
      body: JSON.stringify(payload)
    }
  );
}

export function updateMappingRule(
  workspaceId: string,
  projectId: string,
  moduleId: string,
  ruleId: string,
  actorEmail: string,
  payload: {
    rule_type?: MappingRuleType;
    pattern?: string;
    source?: MappingSource;
    description?: string;
    confidence?: number;
  }
): Promise<ModuleMappingRuleRecord> {
  return requestJson<ModuleMappingRuleRecord>(
    `/workspaces/${workspaceId}/projects/${projectId}/modules/${moduleId}/mapping-rules/${ruleId}?actor_email=${encodeURIComponent(actorEmail)}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload)
    }
  );
}

export function deleteMappingRule(
  workspaceId: string,
  projectId: string,
  moduleId: string,
  ruleId: string,
  actorEmail: string
): Promise<void> {
  return requestNoContent(
    `/workspaces/${workspaceId}/projects/${projectId}/modules/${moduleId}/mapping-rules/${ruleId}?actor_email=${encodeURIComponent(actorEmail)}`,
    { method: "DELETE" }
  );
}

export function uploadImportBatch(workspaceId: string, projectId: string, actorEmail: string, file: File): Promise<ImportBatchRecord> {
  const body = new FormData();
  body.append("file", file);
  return requestFormJson<ImportBatchRecord>(
    `/workspaces/${workspaceId}/projects/${projectId}/imports?actor_email=${encodeURIComponent(actorEmail)}`,
    {
      method: "POST",
      body
    }
  );
}

export function listImportBatches(workspaceId: string, projectId: string): Promise<ImportBatchRecord[]> {
  return requestJson<ImportBatchRecord[]>(`/workspaces/${workspaceId}/projects/${projectId}/imports`);
}

export function getImportBatch(workspaceId: string, projectId: string, batchId: string): Promise<ImportBatchRecord> {
  return requestJson<ImportBatchRecord>(`/workspaces/${workspaceId}/projects/${projectId}/imports/${batchId}`);
}

export function listImportDrafts(workspaceId: string, projectId: string, batchId: string): Promise<ImportDraftRecord[]> {
  return requestJson<ImportDraftRecord[]>(`/workspaces/${workspaceId}/projects/${projectId}/imports/${batchId}/drafts`);
}

export function updateImportDraft(
  workspaceId: string,
  projectId: string,
  batchId: string,
  draftId: string,
  actorEmail: string,
  payload: Partial<Pick<ImportDraftRecord, "module_id" | "title" | "steps" | "priority" | "risk" | "tags" | "custom_fields">>
): Promise<ImportDraftRecord> {
  return requestJson<ImportDraftRecord>(
    `/workspaces/${workspaceId}/projects/${projectId}/imports/${batchId}/drafts/${draftId}?actor_email=${encodeURIComponent(actorEmail)}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload)
    }
  );
}

export function bulkUpdateImportDrafts(
  workspaceId: string,
  projectId: string,
  batchId: string,
  actorEmail: string,
  payload: Partial<Pick<ImportDraftRecord, "module_id" | "title" | "steps" | "priority" | "risk" | "tags" | "custom_fields">> & {
    draft_ids?: string[];
  }
): Promise<ImportDraftRecord[]> {
  return requestJson<ImportDraftRecord[]>(
    `/workspaces/${workspaceId}/projects/${projectId}/imports/${batchId}/drafts-bulk?actor_email=${encodeURIComponent(actorEmail)}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload)
    }
  );
}

export function submitImportReview(workspaceId: string, projectId: string, batchId: string, actorEmail: string): Promise<ImportBatchRecord> {
  return requestJson<ImportBatchRecord>(
    `/workspaces/${workspaceId}/projects/${projectId}/imports/${batchId}/submit-review?actor_email=${encodeURIComponent(actorEmail)}`,
    { method: "POST" }
  );
}

export function bulkImportTestCases(workspaceId: string, projectId: string, batchId: string, actorEmail: string): Promise<ImportResultRecord> {
  return requestJson<ImportResultRecord>(
    `/workspaces/${workspaceId}/projects/${projectId}/imports/${batchId}/bulk-import?actor_email=${encodeURIComponent(actorEmail)}`,
    { method: "POST" }
  );
}

export function listTestCases(
  workspaceId: string,
  projectId: string,
  moduleId?: string,
  status?: TestCaseRecord["lifecycle_status"] | "approved" | "pending_review" | "changes_requested",
  filters?: { includeDescendants?: boolean; sourceType?: string; priority?: string; tag?: string; search?: string }
): Promise<TestCaseRecord[]> {
  const params = new URLSearchParams();
  if (moduleId) params.set("module_id", moduleId);
  if (filters?.includeDescendants === false) params.set("include_descendants", "false");
  if (status === "approved") params.set("lifecycle_status", "active");
  else if (status === "pending_review" || status === "changes_requested") params.set("review_status", status);
  else if (status) params.set("lifecycle_status", status);
  if (filters?.sourceType) params.set("source_type", filters.sourceType);
  if (filters?.priority) params.set("priority", filters.priority);
  if (filters?.tag) params.set("tag", filters.tag);
  if (filters?.search) params.set("search", filters.search);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<TestCaseRecord[]>(`/workspaces/${workspaceId}/projects/${projectId}/test-cases${suffix}`);
}

export function getTestCase(workspaceId: string, projectId: string, caseId: string): Promise<TestCaseRecord> {
  return requestJson<TestCaseRecord>(`/workspaces/${workspaceId}/projects/${projectId}/test-cases/${caseId}`);
}

export function listReviewQueue(workspaceId: string, projectId: string): Promise<TestCaseRecord[]> {
  return requestJson<TestCaseRecord[]>(`/workspaces/${workspaceId}/projects/${projectId}/review-cycles?status=pending_review`);
}

export function getReviewSettings(workspaceId: string): Promise<ReviewSettingsRecord> {
  return requestJson<ReviewSettingsRecord>(`/workspaces/${workspaceId}/review-settings`);
}

export function updateReviewSettings(
  workspaceId: string,
  actorEmail: string,
  payload: {
    allow_self_review: boolean;
    require_review_on_case_update: boolean;
    allow_direct_revision_for_active_case?: boolean;
    direct_revision_roles?: string[];
  }
): Promise<ReviewSettingsRecord> {
  return requestJson<ReviewSettingsRecord>(`/workspaces/${workspaceId}/review-settings?actor_email=${encodeURIComponent(actorEmail)}`, {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

export function createTestCase(
  workspaceId: string,
  projectId: string,
  actorEmail: string,
  payload: TestCasePayload
): Promise<TestCaseRecord> {
  return requestJson<TestCaseRecord>(
    `/workspaces/${workspaceId}/projects/${projectId}/test-cases?actor_email=${encodeURIComponent(actorEmail)}`,
    {
      method: "POST",
      body: JSON.stringify(payload)
    }
  );
}

export function updateTestCase(
  workspaceId: string,
  projectId: string,
  caseId: string,
  actorEmail: string,
  payload: Partial<TestCasePayload>
): Promise<TestCaseRecord> {
  return requestJson<TestCaseRecord>(
    `/workspaces/${workspaceId}/projects/${projectId}/test-cases/${caseId}?actor_email=${encodeURIComponent(actorEmail)}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload)
    }
  );
}

export function submitTestCaseReview(workspaceId: string, projectId: string, caseId: string, actorEmail: string): Promise<TestCaseRecord> {
  return requestJson<TestCaseRecord>(
    `/workspaces/${workspaceId}/projects/${projectId}/test-cases/${caseId}/submit-review?actor_email=${encodeURIComponent(actorEmail)}`,
    { method: "POST" }
  );
}

export function createActiveEditDraft(workspaceId: string, projectId: string, caseId: string, actorEmail: string): Promise<CaseDraftRecord> {
  return requestJson<CaseDraftRecord>(
    `/workspaces/${workspaceId}/projects/${projectId}/test-cases/${caseId}/drafts?actor_email=${encodeURIComponent(actorEmail)}`,
    { method: "POST" }
  );
}

export function updateCaseDraft(
  workspaceId: string,
  projectId: string,
  draftId: string,
  actorEmail: string,
  payload: Partial<TestCasePayload>
): Promise<CaseDraftRecord> {
  return requestJson<CaseDraftRecord>(
    `/workspaces/${workspaceId}/projects/${projectId}/case-drafts/${draftId}?actor_email=${encodeURIComponent(actorEmail)}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload)
    }
  );
}

export function submitCaseDraftReview(workspaceId: string, projectId: string, draftId: string, actorEmail: string): Promise<ReviewCycleRecord> {
  return requestJson<ReviewCycleRecord>(
    `/workspaces/${workspaceId}/projects/${projectId}/case-drafts/${draftId}/submit-review?actor_email=${encodeURIComponent(actorEmail)}`,
    { method: "POST" }
  );
}

export function requestReviewChanges(workspaceId: string, projectId: string, cycleId: string, actorEmail: string, comment: string): Promise<CaseReviewRecord> {
  return requestJson<CaseReviewRecord>(
    `/workspaces/${workspaceId}/projects/${projectId}/review-cycles/${cycleId}/request-changes?actor_email=${encodeURIComponent(actorEmail)}`,
    {
      method: "POST",
      body: JSON.stringify({ comment })
    }
  );
}

export function addressReviewChanges(
  workspaceId: string,
  projectId: string,
  cycleId: string,
  actorEmail: string,
  payload: { comment: string; diff_summary?: Record<string, unknown> }
): Promise<CaseReviewRecord> {
  return requestJson<CaseReviewRecord>(
    `/workspaces/${workspaceId}/projects/${projectId}/review-cycles/${cycleId}/address-changes?actor_email=${encodeURIComponent(actorEmail)}`,
    {
      method: "POST",
      body: JSON.stringify(payload)
    }
  );
}

export function approveReviewCycle(workspaceId: string, projectId: string, cycleId: string, actorEmail: string, comment: string): Promise<CaseReviewRecord> {
  return requestJson<CaseReviewRecord>(
    `/workspaces/${workspaceId}/projects/${projectId}/review-cycles/${cycleId}/approve?actor_email=${encodeURIComponent(actorEmail)}`,
    {
      method: "POST",
      body: JSON.stringify({ comment })
    }
  );
}

export function rejectReviewCycle(workspaceId: string, projectId: string, cycleId: string, actorEmail: string, comment: string): Promise<CaseReviewRecord> {
  return requestJson<CaseReviewRecord>(
    `/workspaces/${workspaceId}/projects/${projectId}/review-cycles/${cycleId}/reject?actor_email=${encodeURIComponent(actorEmail)}`,
    {
      method: "POST",
      body: JSON.stringify({ comment })
    }
  );
}

export function reviewTestCase(
  workspaceId: string,
  projectId: string,
  caseId: string,
  actorEmail: string,
  payload: {
    action: CaseReviewAction;
    comment: string;
    edits?: Partial<TestCasePayload>;
  }
): Promise<CaseReviewRecord> {
  return requestJson<CaseReviewRecord>(
    `/workspaces/${workspaceId}/projects/${projectId}/test-cases/${caseId}/reviews?actor_email=${encodeURIComponent(actorEmail)}`,
    {
      method: "POST",
      body: JSON.stringify(payload)
    }
  );
}

export function listCaseReviews(workspaceId: string, projectId: string, caseId: string): Promise<CaseReviewRecord[]> {
  return requestJson<CaseReviewRecord[]>(`/workspaces/${workspaceId}/projects/${projectId}/test-cases/${caseId}/reviews`);
}

export function listCaseRevisions(workspaceId: string, projectId: string, caseId: string): Promise<CaseRevisionRecord[]> {
  return requestJson<CaseRevisionRecord[]>(`/workspaces/${workspaceId}/projects/${projectId}/test-cases/${caseId}/revisions`);
}
