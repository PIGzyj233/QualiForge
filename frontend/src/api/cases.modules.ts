import { requestJson, requestNoContent } from "./client";
import type { AgentStagedOutputRecord } from "./agents";
import type { MappingRelationship, MappingRulePreflightRecord, MappingRuleType, MappingSource, MappingStatus, MappingStatusFilter, ModuleMappingRuleRecord, ModuleTreeDraftGenerateResponse, ModuleTreeNode, ProjectModuleRecord } from "./cases.types";

export function listModules(
  workspaceId: string,
  projectId: string,
  includeArchived = false,
  mappingRuleStatus?: MappingStatusFilter
): Promise<ProjectModuleRecord[]> {
  const params = new URLSearchParams();
  if (includeArchived) params.set("include_archived_modules", "true");
  if (mappingRuleStatus) params.set("mapping_rule_status", mappingRuleStatus);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<ProjectModuleRecord[]>(`/workspaces/${workspaceId}/projects/${projectId}/modules${suffix}`);
}

export function listModuleTree(
  workspaceId: string,
  projectId: string,
  includeArchived = false,
  mappingRuleStatus?: MappingStatusFilter
): Promise<ModuleTreeNode[]> {
  const params = new URLSearchParams();
  if (includeArchived) params.set("include_archived_modules", "true");
  if (mappingRuleStatus) params.set("mapping_rule_status", mappingRuleStatus);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<ModuleTreeNode[]>(`/workspaces/${workspaceId}/projects/${projectId}/modules/tree${suffix}`);
}

export function createModule(
  workspaceId: string,
  projectId: string,
  actorEmail: string,
  payload: { key?: string; code?: string; name: string; slug?: string; parent_id?: string | null; description: string; owner: string; keywords?: string[]; sort_order?: number }
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
  payload: { name?: string; slug?: string; code?: string; parent_id?: string | null; description?: string; owner?: string; keywords?: string[]; sort_order?: number; status?: "active" | "archived" }
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

export function listModuleTreeDrafts(
  workspaceId: string,
  projectId: string,
  status: "staged" | "accepted" | "rejected" | "all" = "staged"
): Promise<AgentStagedOutputRecord[]> {
  return requestJson<AgentStagedOutputRecord[]>(
    `/workspaces/${workspaceId}/projects/${projectId}/module-tree-drafts?status=${encodeURIComponent(status)}`
  );
}

export function generateModuleTreeDraft(
  workspaceId: string,
  projectId: string,
  actorEmail: string,
  payload: {
    repository_id: string;
    ref?: string;
    guidance?: string;
    max_depth?: number;
    max_modules?: number;
    min_files?: number;
    include_tests?: boolean;
  }
): Promise<ModuleTreeDraftGenerateResponse> {
  return requestJson<ModuleTreeDraftGenerateResponse>(
    `/workspaces/${workspaceId}/projects/${projectId}/module-tree-drafts/generate?actor_email=${encodeURIComponent(actorEmail)}`,
    {
      method: "POST",
      body: JSON.stringify(payload)
    }
  );
}

export function listMappingRules(
  workspaceId: string,
  projectId: string,
  filters?: {
    moduleId?: string;
    repositoryId?: string;
    ruleType?: MappingRuleType;
    relationship?: MappingRelationship;
    status?: MappingStatusFilter;
    source?: MappingSource;
  }
): Promise<ModuleMappingRuleRecord[]> {
  const params = new URLSearchParams();
  if (filters?.moduleId) params.set("module_id", filters.moduleId);
  if (filters?.repositoryId) params.set("repository_id", filters.repositoryId);
  if (filters?.ruleType) params.set("rule_type", filters.ruleType);
  if (filters?.relationship) params.set("relationship", filters.relationship);
  if (filters?.status) params.set("status", filters.status);
  if (filters?.source) params.set("source", filters.source);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<ModuleMappingRuleRecord[]>(`/workspaces/${workspaceId}/projects/${projectId}/mapping-rules${suffix}`);
}

export function preflightMappingRule(
  workspaceId: string,
  projectId: string,
  payload: {
    module_id: string;
    rule_id?: string | null;
    repository_id?: string | null;
    rule_type: MappingRuleType;
    pattern: string;
    relationship?: MappingRelationship;
    status?: MappingStatus;
    source: MappingSource;
    description: string;
    ai_confidence?: number;
    confidence: number;
    evidence_refs?: Record<string, unknown>[];
    accepted_from_output_id?: string | null;
    stale_reason?: string;
    conditions?: Record<string, unknown>;
    case_sensitive?: boolean | null;
  }
): Promise<MappingRulePreflightRecord> {
  return requestJson<MappingRulePreflightRecord>(`/workspaces/${workspaceId}/projects/${projectId}/mapping-rules/preflight`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function createMappingRule(
  workspaceId: string,
  projectId: string,
  moduleId: string,
  actorEmail: string,
  payload: {
    repository_id?: string | null;
    rule_type: MappingRuleType;
    pattern: string;
    relationship?: MappingRelationship;
    status?: MappingStatus;
    source: MappingSource;
    description: string;
    ai_confidence?: number;
    confidence: number;
    evidence_refs?: Record<string, unknown>[];
    accepted_from_output_id?: string | null;
    stale_reason?: string;
    conditions?: Record<string, unknown>;
    case_sensitive?: boolean | null;
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
    repository_id?: string | null;
    rule_type?: MappingRuleType;
    pattern?: string;
    relationship?: MappingRelationship;
    status?: MappingStatus;
    source?: MappingSource;
    description?: string;
    ai_confidence?: number;
    confidence?: number;
    evidence_refs?: Record<string, unknown>[];
    accepted_from_output_id?: string | null;
    stale_reason?: string;
    conditions?: Record<string, unknown>;
    case_sensitive?: boolean | null;
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
