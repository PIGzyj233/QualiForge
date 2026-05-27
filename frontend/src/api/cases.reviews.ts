import { requestJson } from "./client";
import type { CaseDraftRecord, CaseReviewAction, CaseReviewRecord, CaseRevisionRecord, ImportDraftRecord, ReviewCycleRecord, ReviewSettingsRecord, TestCasePayload, TestCaseRecord } from "./cases.types";

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
