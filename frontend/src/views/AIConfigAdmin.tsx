import { FormEvent, useEffect, useState } from "react";
import { BrainCircuit, KeyRound, ShieldAlert } from "lucide-react";
import { useParams } from "react-router-dom";
import {
  type AIDataPolicy, type AIInvocationRecord, type AIPurpose, type AISettingsRecord,
  completeAIInvocation, createLLMProvider, getAISettings, listAIInvocations,
  listLLMProviders, listModelProfiles, type LLMProviderRecord, type ModelProfileRecord,
  startAIInvocation, updateAISettings, upsertModelProfile
} from "@/api/ai";
import { useCurrentWorkspace } from "@/stores/workspace-store";
import { useSessionStore } from "@/stores/session-store";
import { Pagination } from "@/components/Pagination";
import { usePagination } from "@/hooks/usePagination";
import { statusLabel, purposeLabel, policyLabel } from "@/lib/labels";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export function AIConfigAdmin() {
  const session = useSessionStore((s) => s.session);
  const ws = useCurrentWorkspace();
  const actorEmail = session?.user.email ?? "";
  const wid = ws?.id ?? "";

  const [settings, setSettings] = useState<AISettingsRecord | null>(null);
  const [providers, setProviders] = useState<LLMProviderRecord[]>([]);
  const [profiles, setProfiles] = useState<ModelProfileRecord[]>([]);
  const [invocations, setInvocations] = useState<AIInvocationRecord[]>([]);
  const [providerName, setProviderName] = useState("OpenAI Compatible");
  const [apiBaseUrl, setApiBaseUrl] = useState("https://api.openai.example/v1");
  const [apiKey, setApiKey] = useState("");
  const [headersText, setHeadersText] = useState('{"X-Team":"qa"}');
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

  async function refreshConfig() {
    if (!wid) return;
    const [s, p, pr, inv] = await Promise.all([getAISettings(wid), listLLMProviders(wid), listModelProfiles(wid), listAIInvocations(wid)]);
    setSettings(s); setPolicy(s.data_policy); setProviders(p); setProfiles(pr); setInvocations(inv);
    if (!profileProviderId && p[0]) setProfileProviderId(p[0].id);
  }

  useEffect(() => { if (wid) void refreshConfig(); }, [wid]);

  async function handleProviderCreate(e: FormEvent) {
    e.preventDefault();
    if (!wid) return;
    setBusy(true); setMessage(null);
    try {
      const headers = headersText.trim() ? (JSON.parse(headersText) as Record<string, string>) : {};
      const p = await createLLMProvider(wid, actorEmail, { name: providerName, api_base_url: apiBaseUrl, api_key: apiKey, default_headers: headers, organization });
      setMessage(`已创建 Provider：${p.name}`); setProfileProviderId(p.id); setApiKey("");
      await refreshConfig();
    } catch (err) { setMessage(err instanceof Error ? err.message : "Provider 创建失败"); }
    finally { setBusy(false); }
  }

  async function handlePolicyUpdate(e: FormEvent) {
    e.preventDefault();
    if (!wid) return;
    setBusy(true); setMessage(null);
    try {
      const s = await updateAISettings(wid, actorEmail, policy);
      setSettings(s); setMessage(`已更新 AI 数据策略：${s.data_policy}`);
    } catch (err) { setMessage(err instanceof Error ? err.message : "策略更新失败"); }
    finally { setBusy(false); }
  }

  async function handleProfileSave(e: FormEvent) {
    e.preventDefault();
    if (!wid || !profileProviderId) return;
    setBusy(true); setMessage(null);
    try {
      const p = await upsertModelProfile(wid, actorEmail, { provider_id: profileProviderId, purpose: profilePurpose, model_name: modelName, reasoning_effort: reasoningEffort, max_context_tokens: 128000, max_output_tokens: 4096, input_token_price: inputTokenPrice, output_token_price: outputTokenPrice, cache_policy: "semantic", timeout_seconds: 90, retry_count: 2, budget_limit: "25.00" });
      setMessage(`已配置 Model Profile：${purposeLabel[p.purpose]}`);
      await refreshConfig();
    } catch (err) { setMessage(err instanceof Error ? err.message : "Model Profile 保存失败"); }
    finally { setBusy(false); }
  }

  async function handleInvocationStart(e: FormEvent) {
    e.preventDefault();
    if (!wid) return;
    setBusy(true); setMessage(null);
    try {
      const inv = await startAIInvocation(wid, actorEmail, { purpose: invocationPurpose, input_summary: invocationSummary, input_data_types: includesSourceCode ? ["diff", "source_code"] : ["test_cases", "summary"], includes_source_code: includesSourceCode });
      setMessage(`已排队：${purposeLabel[inv.purpose]}`);
      await refreshConfig();
    } catch (err) { setMessage(err instanceof Error ? err.message : "AI 任务启动失败"); await refreshConfig(); }
    finally { setBusy(false); }
  }

  async function handleCompleteLatest() {
    if (!wid) return;
    const queued = invocations.find((i) => i.status === "queued");
    if (!queued) { setMessage("没有可记录摘要的排队 AI 任务"); return; }
    setBusy(true); setMessage(null);
    try {
      await completeAIInvocation(wid, queued.id, actorEmail, { status: "succeeded", token_prompt: 1200, token_completion: 480, cache_hit: false, latency_ms: 1420, failure_reason: "" });
      setMessage("已记录 AI 调用摘要");
      await refreshConfig();
    } catch (err) { setMessage(err instanceof Error ? err.message : "记录失败"); }
    finally { setBusy(false); }
  }

  const fieldCls = "flex flex-col gap-1.5";

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)] mb-1">AI Platform</p>
          <h1 className="font-heading text-2xl font-bold">模型配置和数据策略</h1>
        </div>
        <BrainCircuit size={20} className="text-[var(--muted-foreground)]" />
      </div>

      {message && <Alert><AlertDescription>{message}</AlertDescription></Alert>}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Provider */}
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><KeyRound size={16} />LLM Provider</CardTitle></CardHeader>
          <CardContent>
            <form onSubmit={handleProviderCreate} className="flex flex-col gap-3">
              <div className={fieldCls}><Label>名称</Label><Input value={providerName} onChange={(e) => setProviderName(e.target.value)} required /></div>
              <div className={fieldCls}><Label>API Base URL</Label><Input value={apiBaseUrl} onChange={(e) => setApiBaseUrl(e.target.value)} required /></div>
              <div className={fieldCls}><Label>API Key</Label><Input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} required /></div>
              <div className={fieldCls}><Label>默认 Header JSON</Label><Input value={headersText} onChange={(e) => setHeadersText(e.target.value)} /></div>
              <div className={fieldCls}><Label>组织</Label><Input value={organization} onChange={(e) => setOrganization(e.target.value)} /></div>
              <Button type="submit" disabled={busy || !wid} className="self-start">创建 Provider</Button>
            </form>
            {providers.length > 0 && (
              <div className="mt-4 flex flex-col gap-1.5">
                {providers.map((p) => (
                  <div key={p.id} className="flex items-center justify-between rounded-[var(--radius-sm)] border px-3 py-2 text-sm">
                    <span className="font-semibold">{p.name}</span>
                    <span className="text-xs text-[var(--muted-foreground)] truncate max-w-[180px]">{p.api_base_url}</span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Data Policy */}
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><ShieldAlert size={16} />AI 数据策略</CardTitle></CardHeader>
          <CardContent>
            <form onSubmit={handlePolicyUpdate} className="flex flex-col gap-3">
              <div className={fieldCls}>
                <Label>策略</Label>
                <Select value={policy} onValueChange={(v) => setPolicy(v as AIDataPolicy)} disabled={!wid}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {(Object.keys(policyLabel) as AIDataPolicy[]).map((k) => <SelectItem key={k} value={k}>{policyLabel[k]}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              {settings && <p className="text-xs text-[var(--muted-foreground)]">当前：{settings.data_policy} · 更新者 {settings.updated_by}</p>}
              <Button type="submit" disabled={busy || !wid} className="self-start">保存策略</Button>
            </form>
          </CardContent>
        </Card>

        {/* Model Profile */}
        <Card>
          <CardHeader><CardTitle>Model Profile</CardTitle></CardHeader>
          <CardContent>
            <form onSubmit={handleProfileSave} className="flex flex-col gap-3">
              <div className={fieldCls}>
                <Label>Provider</Label>
                <Select value={profileProviderId} onValueChange={setProfileProviderId} disabled={providers.length === 0}>
                  <SelectTrigger><SelectValue placeholder="选择 Provider" /></SelectTrigger>
                  <SelectContent>{providers.map((p) => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className={fieldCls}>
                <Label>用途</Label>
                <Select value={profilePurpose} onValueChange={(v) => setProfilePurpose(v as AIPurpose)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{(Object.keys(purposeLabel) as AIPurpose[]).map((k) => <SelectItem key={k} value={k}>{purposeLabel[k]}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className={fieldCls}><Label>模型名称</Label><Input value={modelName} onChange={(e) => setModelName(e.target.value)} required /></div>
                <div className={fieldCls}>
                  <Label>推理强度</Label>
                  <Select value={reasoningEffort} onValueChange={(v) => setReasoningEffort(v as typeof reasoningEffort)}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {["low", "medium", "high", "xhigh"].map((v) => <SelectItem key={v} value={v}>{v}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className={fieldCls}><Label>输入价格 ($/1M)</Label><Input value={inputTokenPrice} onChange={(e) => setInputTokenPrice(e.target.value)} /></div>
                <div className={fieldCls}><Label>输出价格 ($/1M)</Label><Input value={outputTokenPrice} onChange={(e) => setOutputTokenPrice(e.target.value)} /></div>
              </div>
              <Button type="submit" disabled={busy || !wid || !profileProviderId} className="self-start">保存 Profile</Button>
            </form>
            {profiles.length > 0 && (
              <div className="mt-4 flex flex-col gap-1.5">
                {profiles.map((p) => (
                  <div key={p.id} className="flex items-center justify-between rounded-[var(--radius-sm)] border px-3 py-2 text-sm">
                    <span className="font-semibold">{purposeLabel[p.purpose] ?? p.purpose}</span>
                    <span className="text-xs text-[var(--muted-foreground)]">{p.model_name}</span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Invocations */}
        <Card>
          <CardHeader><CardTitle>AI 调用记录</CardTitle></CardHeader>
          <CardContent>
            <form onSubmit={handleInvocationStart} className="flex flex-col gap-3 mb-4">
              <div className={fieldCls}>
                <Label>用途</Label>
                <Select value={invocationPurpose} onValueChange={(v) => setInvocationPurpose(v as AIPurpose)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{(Object.keys(purposeLabel) as AIPurpose[]).map((k) => <SelectItem key={k} value={k}>{purposeLabel[k]}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className={fieldCls}><Label>摘要</Label><Input value={invocationSummary} onChange={(e) => setInvocationSummary(e.target.value)} /></div>
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input type="checkbox" checked={includesSourceCode} onChange={(e) => setIncludesSourceCode(e.target.checked)} />
                包含源代码
              </label>
              <div className="flex gap-2">
                <Button type="submit" disabled={busy || !wid}>启动 AI 任务</Button>
                <Button type="button" variant="outline" disabled={busy || !wid} onClick={handleCompleteLatest}>记录最新摘要</Button>
              </div>
            </form>
            <div className="flex flex-col gap-1">
              {invocationsPagination.currentItems.map((inv) => (
                <div key={inv.id} className="flex items-center justify-between rounded-[var(--radius-sm)] border px-3 py-2 text-sm">
                  <div className="min-w-0">
                    <p className="font-semibold truncate">{purposeLabel[inv.purpose] ?? inv.purpose}</p>
                    <p className="text-xs text-[var(--muted-foreground)] truncate">{inv.input_summary}</p>
                  </div>
                  <span className="text-xs text-[var(--muted-foreground)] shrink-0 ml-2">{statusLabel[inv.status] ?? inv.status}</span>
                </div>
              ))}
              {invocations.length === 0 && <p className="text-sm text-[var(--muted-foreground)]">暂无调用记录</p>}
            </div>
            <Pagination currentPage={invocationsPagination.currentPage} totalPages={invocationsPagination.totalPages} totalItems={invocationsPagination.totalItems} onPageChange={invocationsPagination.goToPage} itemsPerPage={8} />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
