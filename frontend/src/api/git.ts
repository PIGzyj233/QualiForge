import { requestJson } from "./client";

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
