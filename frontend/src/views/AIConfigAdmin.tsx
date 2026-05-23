import { FormEvent, useEffect, useState } from "react";
import { BrainCircuit, KeyRound, Settings2, ShieldAlert } from "lucide-react";
import {
  AIDataPolicy,
  AIInvocationRecord,
  AIPurpose,
  AISettingsRecord,
  completeAIInvocation,
  createLLMProvider,
  getAISettings,
  listAIInvocations,
  listLLMProviders,
  listModelProfiles,
  listWorkspaces,
  LLMProviderRecord,
  ModelProfileRecord,
  Session,
  startAIInvocation,
  updateAISettings,
  upsertModelProfile,
  WorkspaceRecord
} from "../api";
import { Pagination } from "../components/Pagination";
import { usePagination } from "../hooks/usePagination";
import { statusLabel, purposeLabel, policyLabel } from "../lib/labels";

export function AIConfigAdmin({ session }: { session: Session }) {
  const actorEmail = session.user.email;
  const [workspaces, setWorkspaces] = useState<WorkspaceRecord[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState("");
  const [settings, setSettings] = useState<AISettingsRecord | null>(null);
  const [providers, setProviders] = useState<LLMProviderRecord[]>([]);
  const [profiles, setProfiles] = useState<ModelProfileRecord[]>([]);
  const [invocations, setInvocations] = useState<AIInvocationRecord[]>([]);
  const [providerName, setProviderName] = useState("OpenAI Compatible");
  const [apiBaseUrl, setApiBaseUrl] = useState("https://api.openai.example/v1");
  const [apiKey, setApiKey] = useState("");
  const [headersText, setHeadersText] = useState("{\"X-Team\":\"qa\"}");
  const [organization, setOrganization] = useState("qualiforge");
  const [policy, setPolicy] = useState<AIDataPolicy>("ExternalAllowed");
  const [profileProviderId, setProfileProviderId] = useState("");
  const [profilePurpose, setProfilePurpose] = useState<AIPurpose>("import_cleanup");
  const [modelName, setModelName] = useState("gpt-test");
  const [reasoningEffort, setReasoningEffort] = useState<"low" | "medium" | "high" | "xhigh">("medium");
  const [inputTokenPrice, setInputTokenPrice] = useState("2.00");
  const [outputTokenPrice, setOutputTokenPrice] = useState("8.00");
  const [invocationPurpose, setInvocationPurpose] = useState<AIPurpose>("import_cleanup");
  const [invocationSummary, setInvocationSummary] = useState("Normalize imported checkout test cases");
  const [includesSourceCode, setIncludesSourceCode] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const invocationsPagination = usePagination(invocations, 8);

  async function refreshAIWorkspaces(preferredWorkspaceId?: string) {
    setBusy(true);
    setMessage(null);
    try {
      const nextWorkspaces = await listWorkspaces(actorEmail);
      setWorkspaces(nextWorkspaces);
      const nextSelectedId = preferredWorkspaceId || selectedWorkspaceId || nextWorkspaces[0]?.id || "";
      setSelectedWorkspaceId(nextSelectedId);
      if (nextSelectedId) {
        await refreshAIConfig(nextSelectedId);
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "AI 配置加载失败");
    } finally {
      setBusy(false);
    }
  }

  async function refreshAIConfig(workspaceId: string) {
    const [nextSettings, nextProviders, nextProfiles, nextInvocations] = await Promise.all([
      getAISettings(workspaceId),
      listLLMProviders(workspaceId),
      listModelProfiles(workspaceId),
      listAIInvocations(workspaceId)
    ]);
    setSettings(nextSettings);
    setPolicy(nextSettings.data_policy);
    setProviders(nextProviders);
    setProfiles(nextProfiles);
    setInvocations(nextInvocations);
    if (!profileProviderId && nextProviders[0]) {
      setProfileProviderId(nextProviders[0].id);
    }
  }

  useEffect(() => {
    void refreshAIWorkspaces();
  }, []);

  async function handleWorkspaceSwitch(workspaceId: string) {
    setSelectedWorkspaceId(workspaceId);
    setBusy(true);
    setMessage(null);
    try {
      await refreshAIConfig(workspaceId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "AI Workspace 切换失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleProviderCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedWorkspaceId) return;
    setBusy(true);
    setMessage(null);
    try {
      const defaultHeaders = headersText.trim() ? (JSON.parse(headersText) as Record<string, string>) : {};
      const provider = await createLLMProvider(selectedWorkspaceId, actorEmail, {
        name: providerName,
        api_base_url: apiBaseUrl,
        api_key: apiKey,
        default_headers: defaultHeaders,
        organization
      });
      setMessage(`已创建 Provider：${provider.name}`);
      setProfileProviderId(provider.id);
      setApiKey("");
      await refreshAIConfig(selectedWorkspaceId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Provider 创建失败");
    } finally {
      setBusy(false);
    }
  }

  async function handlePolicyUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedWorkspaceId) return;
    setBusy(true);
    setMessage(null);
    try {
      const nextSettings = await updateAISettings(selectedWorkspaceId, actorEmail, policy);
      setSettings(nextSettings);
      setMessage(`已更新 AI 数据策略：${nextSettings.data_policy}`);
      await refreshAIConfig(selectedWorkspaceId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "AI 数据策略更新失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleProfileSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedWorkspaceId || !profileProviderId) return;
    setBusy(true);
    setMessage(null);
    try {
      const profile = await upsertModelProfile(selectedWorkspaceId, actorEmail, {
        provider_id: profileProviderId,
        purpose: profilePurpose,
        model_name: modelName,
        reasoning_effort: reasoningEffort,
        max_context_tokens: 128000,
        max_output_tokens: 4096,
        input_token_price: inputTokenPrice,
        output_token_price: outputTokenPrice,
        cache_policy: "semantic",
        timeout_seconds: 90,
        retry_count: 2,
        budget_limit: "25.00"
      });
      setMessage(`已配置 Model Profile：${purposeLabel[profile.purpose]}`);
      await refreshAIConfig(selectedWorkspaceId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Model Profile 保存失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleInvocationStart(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedWorkspaceId) return;
    setBusy(true);
    setMessage(null);
    try {
      const invocation = await startAIInvocation(selectedWorkspaceId, actorEmail, {
        purpose: invocationPurpose,
        input_summary: invocationSummary,
        input_data_types: includesSourceCode ? ["diff", "source_code"] : ["test_cases", "summary"],
        includes_source_code: includesSourceCode
      });
      setMessage(`已通过策略检查并排队：${purposeLabel[invocation.purpose]}`);
      await refreshAIConfig(selectedWorkspaceId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "AI 任务启动失败");
      await refreshAIConfig(selectedWorkspaceId);
    } finally {
      setBusy(false);
    }
  }

  async function handleCompleteLatest() {
    if (!selectedWorkspaceId) return;
    const queued = invocations.find((invocation) => invocation.status === "queued");
    if (!queued) {
      setMessage("没有可记录摘要的排队 AI 任务");
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      await completeAIInvocation(selectedWorkspaceId, queued.id, actorEmail, {
        status: "succeeded",
        token_prompt: 1200,
        token_completion: 480,
        cache_hit: false,
        latency_ms: 1420,
        failure_reason: ""
      });
      setMessage("已记录 AI 调用摘要");
      await refreshAIConfig(selectedWorkspaceId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "AI 调用摘要记录失败");
    } finally {
      setBusy(false);
    }
  }

  const selectedWorkspace = workspaces.find((workspace) => workspace.id === selectedWorkspaceId);

  return (
    <section className="section-block ai-admin">
      <div className="section-heading">
        <div>
          <span className="eyebrow">AI Platform</span>
          <h2>模型配置和数据策略</h2>
        </div>
        <BrainCircuit size={20} aria-hidden="true" />
      </div>
      <div className="admin-body">
        {message ? <div className="inline-notice">{message}</div> : null}

        <div className="admin-toolbar">
          <label className="select-label">
            当前 Workspace
            <select
              value={selectedWorkspaceId}
              onChange={(event) => void handleWorkspaceSwitch(event.target.value)}
              disabled={busy || workspaces.length === 0}
            >
              <option value="">未选择</option>
              {workspaces.map((workspace) => (
                <option value={workspace.id} key={workspace.id}>
                  {workspace.name}
                </option>
              ))}
            </select>
          </label>
          <form className="compact-form" onSubmit={handlePolicyUpdate}>
            <label>
              AI 数据策略
              <select value={policy} onChange={(event) => setPolicy(event.target.value as AIDataPolicy)} disabled={!selectedWorkspaceId}>
                {(Object.keys(policyLabel) as AIDataPolicy[]).map((item) => (
                  <option value={item} key={item}>
                    {policyLabel[item]}
                  </option>
                ))}
              </select>
            </label>
            <button className="primary-button small" type="submit" disabled={busy || !selectedWorkspaceId}>
              <ShieldAlert size={16} aria-hidden="true" />
              <span>保存</span>
            </button>
          </form>
        </div>

        <div className="admin-context">
          <strong>{selectedWorkspace?.name ?? "尚未选择 Workspace"}</strong>
          <span>{settings ? `Policy ${settings.data_policy} · updated by ${settings.updated_by}` : "创建 Workspace 后配置 AI Provider、模型用途和数据策略。"}</span>
        </div>

        <div className="admin-grid">
          <section className="admin-pane" aria-label="LLM Provider 配置">
            <div className="pane-heading">
              <div>
                <span className="eyebrow">Provider</span>
                <h3>OpenAI-compatible Provider</h3>
              </div>
              <KeyRound size={18} aria-hidden="true" />
            </div>
            <form className="stack-form" onSubmit={handleProviderCreate}>
              <label>
                名称
                <input value={providerName} onChange={(event) => setProviderName(event.target.value)} required />
              </label>
              <label>
                API Base URL
                <input value={apiBaseUrl} onChange={(event) => setApiBaseUrl(event.target.value)} required />
              </label>
              <label>
                API Key
                <input value={apiKey} onChange={(event) => setApiKey(event.target.value)} required />
              </label>
              <label>
                默认 Header JSON
                <input value={headersText} onChange={(event) => setHeadersText(event.target.value)} />
              </label>
              <div className="form-row compact">
                <label>
                  组织
                  <input value={organization} onChange={(event) => setOrganization(event.target.value)} />
                </label>
                <button className="ghost-button" type="submit" disabled={busy || !selectedWorkspaceId}>
                  创建 Provider
                </button>
              </div>
            </form>
            <div className="data-list">
              {providers.map((provider) => (
                <div className="data-row wide" key={provider.id}>
                  <div>
                    <strong>{provider.name}</strong>
                    <span>{provider.api_base_url} · key {provider.api_key_masked} · org {provider.organization || "none"}</span>
                  </div>
                </div>
              ))}
              {providers.length === 0 ? <p className="empty-state">暂无 Provider</p> : null}
            </div>
          </section>

          <section className="admin-pane" aria-label="Model Profile 配置">
            <div className="pane-heading">
              <div>
                <span className="eyebrow">Model Profiles</span>
                <h3>用途模型</h3>
              </div>
              <Settings2 size={18} aria-hidden="true" />
            </div>
            <form className="stack-form" onSubmit={handleProfileSave}>
              <label>
                Provider
                <select value={profileProviderId} onChange={(event) => setProfileProviderId(event.target.value)} required>
                  <option value="">未选择</option>
                  {providers.map((provider) => (
                    <option value={provider.id} key={provider.id}>
                      {provider.name}
                    </option>
                  ))}
                </select>
              </label>
              <div className="form-row">
                <label>
                  用途
                  <select value={profilePurpose} onChange={(event) => setProfilePurpose(event.target.value as AIPurpose)}>
                    {(Object.keys(purposeLabel) as AIPurpose[]).map((purpose) => (
                      <option value={purpose} key={purpose}>
                        {purposeLabel[purpose]}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  模型
                  <input value={modelName} onChange={(event) => setModelName(event.target.value)} required />
                </label>
              </div>
              <div className="form-row">
                <label>
                  思考等级
                  <select value={reasoningEffort} onChange={(event) => setReasoningEffort(event.target.value as "low" | "medium" | "high" | "xhigh")}>
                    <option value="low">low</option>
                    <option value="medium">medium</option>
                    <option value="high">high</option>
                    <option value="xhigh">xhigh</option>
                  </select>
                </label>
                <label>
                  输入价格 / 1M
                  <input value={inputTokenPrice} onChange={(event) => setInputTokenPrice(event.target.value)} />
                </label>
              </div>
              <div className="form-row compact">
                <label>
                  输出价格 / 1M
                  <input value={outputTokenPrice} onChange={(event) => setOutputTokenPrice(event.target.value)} />
                </label>
                <button className="ghost-button" type="submit" disabled={busy || !selectedWorkspaceId || providers.length === 0}>
                  保存用途
                </button>
              </div>
            </form>
            <div className="data-list">
              {profiles.map((profile) => (
                <div className="data-row wide" key={profile.id}>
                  <div>
                    <strong>{purposeLabel[profile.purpose]} · {profile.model_name}</strong>
                    <span>{profile.reasoning_effort} · cache {profile.cache_policy} · ${profile.input_token_price}/${profile.output_token_price}</span>
                  </div>
                </div>
              ))}
              {profiles.length === 0 ? <p className="empty-state">暂无 Model Profile</p> : null}
            </div>
          </section>
        </div>

        <section className="audit-pane" aria-label="AI 调用摘要">
          <div className="pane-heading">
            <div>
              <span className="eyebrow">AI Task Gate</span>
              <h3>策略检查和调用摘要</h3>
            </div>
            <BrainCircuit size={18} aria-hidden="true" />
          </div>
          <form className="stack-form" onSubmit={handleInvocationStart}>
            <div className="form-row">
              <label>
                用途
                <select value={invocationPurpose} onChange={(event) => setInvocationPurpose(event.target.value as AIPurpose)}>
                  {(Object.keys(purposeLabel) as AIPurpose[]).map((purpose) => (
                    <option value={purpose} key={purpose}>
                      {purposeLabel[purpose]}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                输入摘要
                <input value={invocationSummary} onChange={(event) => setInvocationSummary(event.target.value)} required />
              </label>
            </div>
            <div className="form-row compact">
              <label className="checkbox-label">
                <input type="checkbox" checked={includesSourceCode} onChange={(event) => setIncludesSourceCode(event.target.checked)} />
                包含源码
              </label>
              <button className="ghost-button" type="submit" disabled={busy || !selectedWorkspaceId}>
                启动 AI 任务
              </button>
              <button className="ghost-button" type="button" onClick={() => void handleCompleteLatest()} disabled={busy || !selectedWorkspaceId}>
                记录摘要
              </button>
            </div>
          </form>
          <div className="audit-list">
            {invocationsPagination.currentItems.map((invocation) => (
              <div className="audit-row" key={invocation.id}>
                <span>{statusLabel[invocation.status]}</span>
                <strong>{purposeLabel[invocation.purpose]} · {invocation.input_summary}</strong>
                <small>
                  {invocation.token_prompt + invocation.token_completion} tokens · ${invocation.estimated_cost}
                  {invocation.failure_reason ? ` · ${invocation.failure_reason}` : ""}
                </small>
              </div>
            ))}
            {invocations.length === 0 ? <p className="empty-state">暂无 AI 调用摘要</p> : null}
          </div>
          <Pagination
            currentPage={invocationsPagination.currentPage}
            totalPages={invocationsPagination.totalPages}
            totalItems={invocationsPagination.totalItems}
            onPageChange={invocationsPagination.goToPage}
            itemsPerPage={8}
          />
        </section>
      </div>
    </section>
  );
}
