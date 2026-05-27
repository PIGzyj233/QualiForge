import { requestFormJson, requestJson } from "./client";
import type { CaseStep, ImportBatchRecord, ImportDraftRecord, ImportResultRecord } from "./cases.types";

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
