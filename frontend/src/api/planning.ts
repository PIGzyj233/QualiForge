import { API_BASE, requestFormJson, requestJson } from "./client";

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
