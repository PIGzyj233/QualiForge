import { requestJson } from "./client";
import type { PlanItemRecord, TestPlanRecord } from "./planning";
import type { AISuggestionJobResponse, AISuggestionRecord, DiffAnalysisRecord, AISuggestionStatus, TestCaseRecord } from "./cases.types";

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

export function generateAISuggestions(
  workspaceId: string,
  projectId: string,
  analysisId: string,
  actorEmail: string,
  options: { force?: boolean } = {}
): Promise<AISuggestionJobResponse> {
  const forceSuffix = options.force ? "&force=true" : "";
  return requestJson<AISuggestionJobResponse>(
    `/workspaces/${workspaceId}/projects/${projectId}/diff-analyses/${analysisId}/ai-suggestions?actor_email=${encodeURIComponent(actorEmail)}${forceSuffix}`,
    { method: "POST" }
  );
}

export function getAISuggestionStatus(
  workspaceId: string,
  projectId: string,
  analysisId: string,
  actorEmail: string
): Promise<AISuggestionJobResponse> {
  return requestJson<AISuggestionJobResponse>(
    `/workspaces/${workspaceId}/projects/${projectId}/diff-analyses/${analysisId}/ai-suggestions/status?actor_email=${encodeURIComponent(actorEmail)}`
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
