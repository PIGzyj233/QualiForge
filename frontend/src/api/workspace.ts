import { requestJson, requestNoContent } from "./client";

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
