import { requestJson } from "./client";

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
