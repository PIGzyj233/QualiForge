const API_BASE = import.meta.env.VITE_API_URL ?? "/api";

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
  actor_email: string;
  purpose: AIPurpose;
  data_policy: AIDataPolicy;
  status: "queued" | "rejected" | "succeeded" | "failed";
  input_summary: string;
  input_data_types: string[];
  includes_source_code: boolean;
  token_prompt: number;
  token_completion: number;
  estimated_cost: string;
  cache_hit: boolean;
  latency_ms: number;
  failure_reason: string;
  created_at: string;
  completed_at: string | null;
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
  key: string;
  name: string;
  description: string;
  owner: string;
  mapping_rules: ModuleMappingRuleRecord[];
  created_at: string;
  updated_at: string;
};

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
  title: string;
  steps: string[];
  expected_result: string;
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
  module_id: string | null;
  import_batch_id: string | null;
  title: string;
  steps: string[];
  expected_result: string;
  priority: string;
  risk: string;
  tags: string[];
  custom_fields: Record<string, string>;
  created_at: string;
  updated_at: string;
};

export type ImportResultRecord = {
  batch: ImportBatchRecord;
  imported_count: number;
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

export function listAuditLogs(workspaceId: string): Promise<AuditLogRecord[]> {
  return requestJson<AuditLogRecord[]>(`/workspaces/${workspaceId}/audit-logs`);
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

export function listModules(workspaceId: string, projectId: string): Promise<ProjectModuleRecord[]> {
  return requestJson<ProjectModuleRecord[]>(`/workspaces/${workspaceId}/projects/${projectId}/modules`);
}

export function createModule(
  workspaceId: string,
  projectId: string,
  actorEmail: string,
  payload: { key: string; name: string; description: string; owner: string }
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
  payload: { name?: string; description?: string; owner?: string }
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
  payload: Partial<Pick<ImportDraftRecord, "module_id" | "title" | "steps" | "expected_result" | "priority" | "risk" | "tags" | "custom_fields">>
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
  payload: Partial<Pick<ImportDraftRecord, "module_id" | "title" | "steps" | "expected_result" | "priority" | "risk" | "tags" | "custom_fields">> & {
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

export function listTestCases(workspaceId: string, projectId: string, moduleId?: string): Promise<TestCaseRecord[]> {
  const suffix = moduleId ? `?module_id=${encodeURIComponent(moduleId)}` : "";
  return requestJson<TestCaseRecord[]>(`/workspaces/${workspaceId}/projects/${projectId}/test-cases${suffix}`);
}
