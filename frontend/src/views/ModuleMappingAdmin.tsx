import { FormEvent, useEffect, useMemo, useState } from "react";
import { FolderPlus, GitBranch, Network, PencilLine, Plus, Trash2 } from "lucide-react";
import { useParams } from "react-router-dom";
import { AgentStagedOutputRecord, decideAgentStagedOutput } from "../api/agents";
import { createMappingRule, createModule, deleteMappingRule, deleteModule, generateModuleTreeDraft, listMappingRules, listModuleTree, listModuleTreeDrafts, MappingRelationship, MappingRulePreflightRecord, MappingRuleType, MappingSource, MappingStatus, ModuleMappingRuleRecord, ModuleTreeNode, preflightMappingRule, ProjectModuleRecord, updateMappingRule, updateModule } from "../api/cases";
import { GitRepositoryRecord, listRepositories } from "../api/git";
import { listProjects, listWorkspaces, ProjectRecord, Session, WorkspaceRecord } from "../api/workspace";
import { useSessionStore } from "@/stores/session-store";
import { mappingRelationshipLabel, mappingRuleTypeLabel, mappingSourceLabel, mappingStatusLabel } from "../lib/labels";
import { pickExistingId } from "../lib/selection";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

type DialogMode = { kind: "create"; parentId: string | null } | { kind: "edit"; module: ProjectModuleRecord } | null;

const NONE = "__none__";
const eyebrowCls = "text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)]";
const fieldLabelCls = "text-xs font-medium text-[var(--muted-foreground)]";

function flattenTree(nodes: ModuleTreeNode[], acc: ProjectModuleRecord[] = []): ProjectModuleRecord[] {
  for (const node of nodes) {
    acc.push(node);
    flattenTree(node.children, acc);
  }
  return acc;
}

function splitTextList(value: string): string[] {
  const seen = new Set<string>();
  return value
    .split(/[,\n]/)
    .map((item) => item.trim())
    .filter((item) => {
      const key = item.toLowerCase();
      if (!item || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}

function parseJsonObjectList(value: string): Record<string, unknown>[] {
  const parsed = JSON.parse(value.trim() || "[]") as unknown;
  if (!Array.isArray(parsed) || parsed.some((item) => !item || typeof item !== "object" || Array.isArray(item))) {
    throw new Error("证据引用必须是 JSON 对象数组");
  }
  return parsed as Record<string, unknown>[];
}

type ModuleDraftItem = {
  draft_id: string;
  parent_draft_id?: string | null;
  name: string;
  slug: string;
  code?: string;
  description?: string;
  keywords?: string[];
  source_paths?: string[];
  rationale?: string;
  confidence?: number;
  evidence_refs?: Record<string, unknown>[];
};

function moduleDraftItems(output: AgentStagedOutputRecord): ModuleDraftItem[] {
  const items = output.payload.items;
  if (!Array.isArray(items)) return [];
  return items.filter((item): item is ModuleDraftItem => Boolean(item && typeof item === "object" && "draft_id" in item && "name" in item));
}

function resetRuleDefaults() {
  return {
    repositoryId: "",
    type: "directory" as MappingRuleType,
    pattern: "",
    relationship: "primary" as MappingRelationship,
    status: "active" as MappingStatus,
    source: "manual" as MappingSource,
    description: "",
    aiConfidence: "0",
    confidence: "90",
    evidenceRefs: "[]",
    staleReason: ""
  };
}

function TreeNode({
  node,
  selectedId,
  onSelect,
  onAddChild,
  onEdit,
  onDelete
}: {
  node: ModuleTreeNode;
  selectedId: string;
  onSelect: (id: string) => void;
  onAddChild: (parentId: string) => void;
  onEdit: (module: ProjectModuleRecord) => void;
  onDelete: (id: string) => void;
}) {
  const active = selectedId === node.id;
  return (
    <li>
      <div
        className={cn(
          "group flex items-center gap-1 rounded-[var(--radius-sm)] pr-1 transition-colors hover:bg-[var(--muted)]/50",
          active && "bg-[var(--accent)]"
        )}
        style={{ paddingLeft: 6 + node.depth * 16 }}
      >
        <button
          className="flex min-w-0 flex-1 flex-col items-start gap-0.5 px-2 py-1.5 text-left"
          type="button"
          onClick={() => onSelect(node.id)}
        >
          <span className="truncate text-sm font-medium">{node.name}</span>
          <small className="truncate text-[11px] text-[var(--muted-foreground)]">
            {node.key || "—"} · {node.reference_count} 引用 · {node.mapping_rules.length} 映射
          </small>
        </button>
        <div className="flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
          <Button variant="ghost" size="icon" className="h-6 w-6" type="button" onClick={() => onAddChild(node.id)} title="新增子模块">
            <FolderPlus size={13} aria-hidden="true" />
          </Button>
          <Button variant="ghost" size="icon" className="h-6 w-6" type="button" onClick={() => onEdit(node)} title="编辑模块">
            <PencilLine size={13} aria-hidden="true" />
          </Button>
          <Button variant="ghost" size="icon" className="h-6 w-6" type="button" onClick={() => onDelete(node.id)} title="删除模块">
            <Trash2 size={13} aria-hidden="true" />
          </Button>
        </div>
      </div>
      {node.children.length ? (
        <ul className="flex flex-col gap-0.5">
          {node.children.map((child) => (
            <TreeNode
              key={child.id}
              node={child}
              selectedId={selectedId}
              onSelect={onSelect}
              onAddChild={onAddChild}
              onEdit={onEdit}
              onDelete={onDelete}
            />
          ))}
        </ul>
      ) : null}
    </li>
  );
}

function ModuleDialog({
  mode,
  busy,
  onClose,
  onSubmit
}: {
  mode: DialogMode;
  busy: boolean;
  onClose: () => void;
  onSubmit: (payload: {
    name: string;
    code: string;
    slug: string;
    description: string;
    owner: string;
    keywords: string[];
    status: "active" | "archived";
  }) => Promise<void>;
}) {
  const isEdit = mode?.kind === "edit";
  const module = mode?.kind === "edit" ? mode.module : null;
  const [name, setName] = useState(module?.name ?? "");
  const [code, setCode] = useState(module?.key ?? "");
  const [slug, setSlug] = useState(module?.slug ?? "");
  const [description, setDescription] = useState(module?.description ?? "");
  const [owner, setOwner] = useState(module?.owner ?? "");
  const [keywords, setKeywords] = useState((module?.keywords ?? []).join(", "));
  const [status, setStatus] = useState<"active" | "archived">(module?.status ?? "active");

  useEffect(() => {
    if (mode?.kind === "edit") {
      setName(mode.module.name);
      setCode(mode.module.key);
      setSlug(mode.module.slug);
      setDescription(mode.module.description);
      setOwner(mode.module.owner);
      setKeywords(mode.module.keywords.join(", "));
      setStatus(mode.module.status);
    } else if (mode?.kind === "create") {
      setName("");
      setCode("");
      setSlug("");
      setDescription("");
      setOwner("");
      setKeywords("");
      setStatus("active");
    }
  }, [mode]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onSubmit({ name, code, slug, description, owner, keywords: splitTextList(keywords), status });
  }

  return (
    <Dialog open={!!mode} onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent className="max-h-[90vh] max-w-lg overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isEdit ? `编辑模块 · ${module?.path_label ?? ""}` : "新建模块"}</DialogTitle>
        </DialogHeader>
        {!isEdit && mode?.kind === "create" && mode.parentId ? (
          <p className="text-xs text-[var(--muted-foreground)]">将作为子模块新增。</p>
        ) : null}
        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label className={fieldLabelCls}>名称</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} required autoFocus className="h-8 text-sm" />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label className={fieldLabelCls}>编号</Label>
              <Input value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="可选" className="h-8 text-sm" />
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label className={fieldLabelCls}>Slug</Label>
            <Input value={slug} onChange={(e) => setSlug(e.target.value)} placeholder="留空自动生成" className="h-8 text-sm" />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label className={fieldLabelCls}>描述</Label>
            <Input value={description} onChange={(e) => setDescription(e.target.value)} className="h-8 text-sm" />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label className={fieldLabelCls}>关键词</Label>
            <Input value={keywords} onChange={(e) => setKeywords(e.target.value)} placeholder="payment, refund" className="h-8 text-sm" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label className={fieldLabelCls}>Owner</Label>
              <Input value={owner} onChange={(e) => setOwner(e.target.value)} className="h-8 text-sm" />
            </div>
            {isEdit ? (
              <div className="flex flex-col gap-1.5">
                <Label className={fieldLabelCls}>状态</Label>
                <Select value={status} onValueChange={(v) => setStatus(v as "active" | "archived")}>
                  <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="active">Active</SelectItem>
                    <SelectItem value="archived">Archived</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            ) : null}
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="outline" size="sm" onClick={onClose} disabled={busy}>
              取消
            </Button>
            <Button type="submit" size="sm" disabled={busy || !name.trim()}>
              {isEdit ? "保存" : "创建"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function ModuleMappingAdmin() {
  const session = useSessionStore((s) => s.session);
  const actorEmail = session?.user.email ?? "";
  const { wid: routeWorkspaceId = "", pid: routeProjectId = "" } = useParams<{ wid: string; pid: string }>();
  const [workspaces, setWorkspaces] = useState<WorkspaceRecord[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState("");
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [repositories, setRepositories] = useState<GitRepositoryRecord[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [tree, setTree] = useState<ModuleTreeNode[]>([]);
  const [mappingRules, setMappingRules] = useState<ModuleMappingRuleRecord[]>([]);
  const [moduleDrafts, setModuleDrafts] = useState<AgentStagedOutputRecord[]>([]);
  const [selectedModuleId, setSelectedModuleId] = useState("");
  const [dialog, setDialog] = useState<DialogMode>(null);
  const [draftRepositoryId, setDraftRepositoryId] = useState("");
  const [draftRef, setDraftRef] = useState("");
  const [draftGuidance, setDraftGuidance] = useState("");
  const [draftMaxModules, setDraftMaxModules] = useState("24");

  // Rule editor state
  const [ruleRepositoryId, setRuleRepositoryId] = useState(resetRuleDefaults().repositoryId);
  const [ruleType, setRuleType] = useState<MappingRuleType>(resetRuleDefaults().type);
  const [rulePattern, setRulePattern] = useState(resetRuleDefaults().pattern);
  const [ruleRelationship, setRuleRelationship] = useState<MappingRelationship>(resetRuleDefaults().relationship);
  const [ruleStatus, setRuleStatus] = useState<MappingStatus>(resetRuleDefaults().status);
  const [ruleSource, setRuleSource] = useState<MappingSource>(resetRuleDefaults().source);
  const [ruleDescription, setRuleDescription] = useState(resetRuleDefaults().description);
  const [ruleAiConfidence, setRuleAiConfidence] = useState(resetRuleDefaults().aiConfidence);
  const [ruleConfidence, setRuleConfidence] = useState(resetRuleDefaults().confidence);
  const [ruleEvidenceRefs, setRuleEvidenceRefs] = useState(resetRuleDefaults().evidenceRefs);
  const [ruleStaleReason, setRuleStaleReason] = useState(resetRuleDefaults().staleReason);
  const [editingRuleId, setEditingRuleId] = useState<string | null>(null);
  const [rulePreflight, setRulePreflight] = useState<MappingRulePreflightRecord | null>(null);

  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const allModules = useMemo(() => flattenTree(tree), [tree]);
  const selectedModule = allModules.find((m) => m.id === selectedModuleId) ?? null;
  const ruleList = useMemo(() => mappingRules.filter((r) => r.module_id === selectedModuleId), [mappingRules, selectedModuleId]);

  function resetRuleForm() {
    const defaults = resetRuleDefaults();
    setRuleRepositoryId(defaults.repositoryId);
    setRuleType(defaults.type);
    setRulePattern(defaults.pattern);
    setRuleRelationship(defaults.relationship);
    setRuleStatus(defaults.status);
    setRuleSource(defaults.source);
    setRuleDescription(defaults.description);
    setRuleAiConfidence(defaults.aiConfidence);
    setRuleConfidence(defaults.confidence);
    setRuleEvidenceRefs(defaults.evidenceRefs);
    setRuleStaleReason(defaults.staleReason);
    setEditingRuleId(null);
    setRulePreflight(null);
  }

  async function refreshProjectModules(workspaceId: string, projectId: string) {
    const [nextTree, nextRules, nextRepositories, nextDrafts] = await Promise.all([
      listModuleTree(workspaceId, projectId, false, "all"),
      listMappingRules(workspaceId, projectId, { status: "all" }),
      listRepositories(workspaceId, projectId),
      listModuleTreeDrafts(workspaceId, projectId, "staged")
    ]);
    setTree(nextTree);
    setMappingRules(nextRules);
    setRepositories(nextRepositories);
    setModuleDrafts(nextDrafts);
    setDraftRepositoryId((current) => (nextRepositories.some((repo) => repo.id === current) ? current : nextRepositories[0]?.id || ""));
    const flattened = flattenTree(nextTree);
    if (!flattened.some((m) => m.id === selectedModuleId)) {
      setSelectedModuleId(flattened[0]?.id ?? "");
    }
  }

  async function refreshWorkspaces(preferredWorkspaceId?: string, preferredProjectId?: string) {
    setBusy(true);
    setMessage(null);
    try {
      const ws = await listWorkspaces(actorEmail);
      setWorkspaces(ws);
      const wid = pickExistingId(ws, preferredWorkspaceId, selectedWorkspaceId);
      setSelectedWorkspaceId(wid);
      if (!wid) {
        setProjects([]);
        setRepositories([]);
        setTree([]);
        setMappingRules([]);
        setModuleDrafts([]);
        setDraftRepositoryId("");
        return;
      }
      const ps = await listProjects(wid);
      setProjects(ps);
      const pid = pickExistingId(ps, preferredProjectId, selectedProjectId);
      setSelectedProjectId(pid);
      if (pid) {
        await refreshProjectModules(wid, pid);
      } else {
        setRepositories([]);
        setTree([]);
        setMappingRules([]);
        setModuleDrafts([]);
        setDraftRepositoryId("");
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "模块数据加载失败");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void refreshWorkspaces(routeWorkspaceId || undefined, routeProjectId || undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routeWorkspaceId, routeProjectId]);

  async function handleProjectSwitch(pid: string) {
    setSelectedProjectId(pid);
    if (!selectedWorkspaceId || !pid) return;
    setBusy(true);
    try {
      await refreshProjectModules(selectedWorkspaceId, pid);
    } finally {
      setBusy(false);
    }
  }

  async function handleWorkspaceSwitch(wid: string) {
    setSelectedWorkspaceId(wid);
    setBusy(true);
    try {
      const ps = await listProjects(wid);
      setProjects(ps);
      const pid = ps[0]?.id ?? "";
      setSelectedProjectId(pid);
      if (pid) {
        await refreshProjectModules(wid, pid);
      } else {
        setRepositories([]);
        setTree([]);
        setMappingRules([]);
        setModuleDrafts([]);
        setDraftRepositoryId("");
      }
    } finally {
      setBusy(false);
    }
  }

  async function handleSubmitModule(payload: {
    name: string;
    code: string;
    slug: string;
    description: string;
    owner: string;
    keywords: string[];
    status: "active" | "archived";
  }) {
    if (!selectedWorkspaceId || !selectedProjectId || !dialog) return;
    setBusy(true);
    setMessage(null);
    try {
      if (dialog.kind === "edit") {
        await updateModule(selectedWorkspaceId, selectedProjectId, dialog.module.id, actorEmail, {
          name: payload.name,
          code: payload.code || undefined,
          slug: payload.slug || undefined,
          description: payload.description,
          owner: payload.owner,
          keywords: payload.keywords,
          status: payload.status
        });
        setMessage(`已更新模块 ${payload.name}`);
      } else {
        const created = await createModule(selectedWorkspaceId, selectedProjectId, actorEmail, {
          name: payload.name,
          code: payload.code || undefined,
          slug: payload.slug || undefined,
          parent_id: dialog.parentId,
          description: payload.description,
          owner: payload.owner,
          keywords: payload.keywords
        });
        setMessage(`已创建模块 ${payload.name}`);
        setSelectedModuleId(created.id);
      }
      setDialog(null);
      await refreshProjectModules(selectedWorkspaceId, selectedProjectId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "模块保存失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteModule(id: string) {
    if (!selectedWorkspaceId || !selectedProjectId) return;
    if (!window.confirm("确认删除此模块？子模块或绑定关系会阻止删除。")) return;
    setBusy(true);
    try {
      await deleteModule(selectedWorkspaceId, selectedProjectId, id, actorEmail);
      setMessage("已删除模块");
      await refreshProjectModules(selectedWorkspaceId, selectedProjectId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "模块删除失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleRuleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedWorkspaceId || !selectedProjectId || !selectedModuleId) return;
    setBusy(true);
    setMessage(null);
    try {
      const evidenceRefs = parseJsonObjectList(ruleEvidenceRefs);
      const payload = {
        repository_id: ruleRepositoryId || null,
        rule_type: ruleType,
        pattern: rulePattern,
        relationship: ruleRelationship,
        status: ruleStatus,
        source: ruleSource,
        description: ruleDescription,
        ai_confidence: Number(ruleAiConfidence || 0),
        confidence: Number(ruleConfidence || 0),
        evidence_refs: evidenceRefs,
        stale_reason: ruleStatus === "stale" ? ruleStaleReason : ""
      };
      const preflight = await preflightMappingRule(selectedWorkspaceId, selectedProjectId, {
        ...payload,
        module_id: selectedModuleId,
        rule_id: editingRuleId
      });
      setRulePreflight(preflight);
      if (preflight.blocker_count > 0) {
        setMessage("映射规则预检未通过");
        return;
      }
      if (editingRuleId) {
        await updateMappingRule(selectedWorkspaceId, selectedProjectId, selectedModuleId, editingRuleId, actorEmail, payload);
        setMessage("已更新映射规则");
      } else {
        await createMappingRule(selectedWorkspaceId, selectedProjectId, selectedModuleId, actorEmail, payload);
        setMessage("已新增映射规则");
      }
      resetRuleForm();
      await refreshProjectModules(selectedWorkspaceId, selectedProjectId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "映射规则保存失败");
    } finally {
      setBusy(false);
    }
  }

  function editRule(rule: ModuleMappingRuleRecord) {
    setEditingRuleId(rule.id);
    setRulePreflight(null);
    setRuleRepositoryId(rule.repository_id ?? "");
    setRuleType(rule.rule_type);
    setRulePattern(rule.pattern);
    setRuleRelationship(rule.relationship);
    setRuleStatus(rule.status);
    setRuleSource(rule.source);
    setRuleDescription(rule.description);
    setRuleAiConfidence(String(rule.ai_confidence));
    setRuleConfidence(String(rule.confidence));
    setRuleEvidenceRefs(JSON.stringify(rule.evidence_refs ?? [], null, 2));
    setRuleStaleReason(rule.stale_reason);
  }

  async function deleteRule(rule: ModuleMappingRuleRecord) {
    if (!selectedWorkspaceId || !selectedProjectId) return;
    setBusy(true);
    try {
      await deleteMappingRule(selectedWorkspaceId, selectedProjectId, rule.module_id, rule.id, actorEmail);
      setMessage("已删除映射规则");
      await refreshProjectModules(selectedWorkspaceId, selectedProjectId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "映射规则删除失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleGenerateDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedWorkspaceId || !selectedProjectId || !draftRepositoryId) return;
    setBusy(true);
    setMessage(null);
    try {
      const draft = await generateModuleTreeDraft(selectedWorkspaceId, selectedProjectId, actorEmail, {
        repository_id: draftRepositoryId,
        ref: draftRef || undefined,
        guidance: draftGuidance || undefined,
        max_modules: Number(draftMaxModules || 24),
        max_depth: 3
      });
      if ("staged_outputs" in draft) {
        setMessage(draft.staged_outputs[0] ? `已生成模块目录草稿：${moduleDraftItems(draft.staged_outputs[0]).length} 个候选模块` : "模块目录草稿生成任务已启动");
      } else {
        setMessage(`已生成模块目录草稿：${moduleDraftItems(draft).length} 个候选模块`);
      }
      await refreshProjectModules(selectedWorkspaceId, selectedProjectId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "模块目录草稿生成失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleDraftDecision(output: AgentStagedOutputRecord, status: "accepted" | "rejected") {
    if (!selectedWorkspaceId || !selectedProjectId) return;
    setBusy(true);
    setMessage(null);
    try {
      const decided = await decideAgentStagedOutput(selectedWorkspaceId, output.id, actorEmail, {
        status,
        decision_summary: status === "accepted" ? "Accepted module tree draft from Module Mapping admin" : "Rejected module tree draft from Module Mapping admin"
      });
      const result = decided.payload.acceptance_result as { created_count?: number; reused_count?: number } | undefined;
      setMessage(
        status === "accepted"
          ? `已确认模块草稿：新增 ${result?.created_count ?? 0} 个，复用 ${result?.reused_count ?? 0} 个`
          : "已拒绝模块草稿"
      );
      await refreshProjectModules(selectedWorkspaceId, selectedProjectId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "模块草稿确认失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className={cn(eyebrowCls, "mb-1")}>Modules</p>
          <h1 className="font-heading text-2xl font-bold">模块目录与代码映射</h1>
          <p className="mt-1 text-sm text-[var(--muted-foreground)]">维护人类确认的功能/能力树，并把代码路径、API、配置、协议、符号等证据绑定到模块。</p>
        </div>
        <Network size={20} aria-hidden="true" className="mt-1 shrink-0 text-[var(--muted-foreground)]" />
      </div>

      {workspaces.length > 1 || projects.length > 1 ? (
        <div className="flex flex-wrap gap-2">
          {workspaces.length > 1 ? (
            <div className="flex flex-col gap-1.5">
              <Label className={fieldLabelCls}>Workspace</Label>
              <Select value={selectedWorkspaceId || undefined} onValueChange={(v) => void handleWorkspaceSwitch(v)} disabled={busy}>
                <SelectTrigger className="h-8 w-48 text-xs"><SelectValue placeholder="选择 Workspace" /></SelectTrigger>
                <SelectContent>
                  {workspaces.map((w) => (
                    <SelectItem key={w.id} value={w.id}>{w.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          ) : null}
          {projects.length > 1 ? (
            <div className="flex flex-col gap-1.5">
              <Label className={fieldLabelCls}>Project</Label>
              <Select value={selectedProjectId || undefined} onValueChange={(v) => void handleProjectSwitch(v)} disabled={busy}>
                <SelectTrigger className="h-8 w-56 text-xs"><SelectValue placeholder="选择 Project" /></SelectTrigger>
                <SelectContent>
                  {projects.map((p) => (
                    <SelectItem key={p.id} value={p.id}>{p.key} · {p.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          ) : null}
        </div>
      ) : null}

      {message ? <Alert><AlertDescription>{message}</AlertDescription></Alert> : null}

      {/* Agent module-tree draft */}
      <Card>
        <CardContent className="flex flex-col gap-3 p-4">
          <div className="flex items-center justify-between gap-2">
            <h2 className="flex items-center gap-1.5 font-heading text-sm font-bold">
              <Network size={14} aria-hidden="true" /> Agent 模块目录草稿
            </h2>
            <span className="text-xs text-[var(--muted-foreground)]">{moduleDrafts.length} 个待确认</span>
          </div>
          <form onSubmit={handleGenerateDraft} className="flex flex-col gap-3">
            <div className="flex flex-wrap gap-3">
              <div className="flex min-w-[180px] flex-1 flex-col gap-1.5">
                <Label className={fieldLabelCls}>仓库</Label>
                <Select value={draftRepositoryId || undefined} onValueChange={setDraftRepositoryId} disabled={busy || repositories.length === 0}>
                  <SelectTrigger className="h-8 text-xs"><SelectValue placeholder={repositories.length === 0 ? "无可用仓库" : "选择仓库"} /></SelectTrigger>
                  <SelectContent>
                    {repositories.map((repository) => (
                      <SelectItem key={repository.id} value={repository.id}>{repository.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex w-40 flex-col gap-1.5">
                <Label className={fieldLabelCls}>Ref</Label>
                <Input value={draftRef} onChange={(event) => setDraftRef(event.target.value)} placeholder="默认分支" className="h-8 text-sm" />
              </div>
              <div className="flex w-28 flex-col gap-1.5">
                <Label className={fieldLabelCls}>模块上限</Label>
                <Input type="number" min="3" max="80" value={draftMaxModules} onChange={(event) => setDraftMaxModules(event.target.value)} className="h-8 text-sm" />
              </div>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label className={fieldLabelCls}>生成要求</Label>
              <Input value={draftGuidance} onChange={(event) => setDraftGuidance(event.target.value)} placeholder="例如：优先按业务能力分组" className="h-8 text-sm" />
            </div>
            <div>
              <Button type="submit" size="sm" disabled={busy || !draftRepositoryId}>
                生成草稿
              </Button>
            </div>
          </form>

          <div className="flex flex-col gap-2">
            {moduleDrafts.map((draft) => {
              const items = moduleDraftItems(draft);
              return (
                <div key={draft.id} className="flex items-start justify-between gap-3 rounded-[var(--radius-md)] border border-[var(--border)] p-3">
                  <div className="flex min-w-0 flex-col gap-0.5">
                    <strong className="text-sm">{draft.title}</strong>
                    <span className="text-xs text-[var(--muted-foreground)]">{items.length} 个候选模块 · {String(draft.payload.generated_by || "agent")}</span>
                    {items.slice(0, 6).map((item) => (
                      <small key={item.draft_id} className="truncate text-[11px] text-[var(--muted-foreground)]">
                        {item.parent_draft_id ? "↳ " : ""}
                        {item.name} · {(item.source_paths ?? []).slice(0, 2).join(", ") || item.slug}
                      </small>
                    ))}
                    {items.length > 6 ? <small className="text-[11px] text-[var(--muted-foreground)]">另有 {items.length - 6} 个候选模块</small> : null}
                  </div>
                  <div className="flex shrink-0 gap-1.5">
                    <Button variant="outline" size="sm" type="button" onClick={() => void handleDraftDecision(draft, "accepted")} disabled={busy}>
                      确认
                    </Button>
                    <Button variant="outline" size="sm" type="button" onClick={() => void handleDraftDecision(draft, "rejected")} disabled={busy}>
                      拒绝
                    </Button>
                  </div>
                </div>
              );
            })}
            {moduleDrafts.length === 0 ? <p className="text-sm text-[var(--muted-foreground)]">暂无待确认模块草稿。</p> : null}
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 items-start gap-5 xl:grid-cols-[minmax(260px,360px)_minmax(0,1fr)]">
        {/* Module tree */}
        <Card className="min-w-0">
          <CardContent className="flex flex-col gap-2 p-3">
            <div className="flex items-center justify-between gap-2">
              <strong className="text-sm">模块树</strong>
              <Button variant="outline" size="sm" type="button" onClick={() => setDialog({ kind: "create", parentId: null })} disabled={busy || !selectedProjectId}>
                <Plus size={14} aria-hidden="true" />
                新增根模块
              </Button>
            </div>
            {tree.length === 0 ? (
              <p className="py-6 text-center text-sm text-[var(--muted-foreground)]">尚无模块，点击「新增根模块」开始。</p>
            ) : (
              <ul className="flex flex-col gap-0.5">
                {tree.map((root) => (
                  <TreeNode
                    key={root.id}
                    node={root}
                    selectedId={selectedModuleId}
                    onSelect={setSelectedModuleId}
                    onAddChild={(parentId) => setDialog({ kind: "create", parentId })}
                    onEdit={(m) => setDialog({ kind: "edit", module: m })}
                    onDelete={(id) => void handleDeleteModule(id)}
                  />
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        {/* Module detail */}
        <Card className="min-w-0">
          <CardContent className="p-4">
            {selectedModule ? (
              <div className="flex flex-col gap-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className={eyebrowCls}>已选模块</p>
                    <h3 className="font-heading text-lg font-bold">{selectedModule.path_label}</h3>
                    <p className="text-sm text-[var(--muted-foreground)]">{selectedModule.description || "暂无描述"} · Owner {selectedModule.owner || "未指定"}</p>
                    {selectedModule.keywords.length ? <p className="text-xs text-[var(--muted-foreground)]">关键词 {selectedModule.keywords.join(" · ")}</p> : null}
                  </div>
                  <div className="flex shrink-0 gap-1.5">
                    <Button variant="outline" size="sm" type="button" onClick={() => setDialog({ kind: "create", parentId: selectedModule.id })} disabled={busy}>
                      <FolderPlus size={14} aria-hidden="true" /> 新增子模块
                    </Button>
                    <Button variant="outline" size="sm" type="button" onClick={() => setDialog({ kind: "edit", module: selectedModule })} disabled={busy}>
                      <PencilLine size={14} aria-hidden="true" /> 编辑
                    </Button>
                  </div>
                </div>

                <div className="flex flex-col gap-3 border-t border-[var(--border)] pt-4">
                  <div className="flex items-center justify-between gap-2">
                    <h4 className="flex items-center gap-1.5 text-sm font-bold">
                      <GitBranch size={14} aria-hidden="true" /> 映射规则
                    </h4>
                    <span className="text-xs text-[var(--muted-foreground)]">{ruleList.length} 条规则</span>
                  </div>

                  <form onSubmit={handleRuleSubmit} className="flex flex-col gap-3 rounded-[var(--radius-md)] border border-[var(--border)] p-3">
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                      <div className="flex flex-col gap-1.5">
                        <Label className={fieldLabelCls}>仓库</Label>
                        <Select value={ruleRepositoryId || NONE} onValueChange={(v) => setRuleRepositoryId(v === NONE ? "" : v)}>
                          <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value={NONE}>项目通用</SelectItem>
                            {repositories.map((repository) => (
                              <SelectItem key={repository.id} value={repository.id}>{repository.name}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="flex flex-col gap-1.5">
                        <Label className={fieldLabelCls}>类型</Label>
                        <Select value={ruleType} onValueChange={(v) => setRuleType(v as MappingRuleType)}>
                          <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {(Object.keys(mappingRuleTypeLabel) as MappingRuleType[]).map((type) => (
                              <SelectItem key={type} value={type}>{mappingRuleTypeLabel[type]}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                    </div>
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                      <div className="flex flex-col gap-1.5">
                        <Label className={fieldLabelCls}>关系</Label>
                        <Select value={ruleRelationship} onValueChange={(v) => setRuleRelationship(v as MappingRelationship)}>
                          <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {(Object.keys(mappingRelationshipLabel) as MappingRelationship[]).map((relationship) => (
                              <SelectItem key={relationship} value={relationship}>{mappingRelationshipLabel[relationship]}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="flex flex-col gap-1.5">
                        <Label className={fieldLabelCls}>状态</Label>
                        <Select value={ruleStatus} onValueChange={(v) => setRuleStatus(v as MappingStatus)}>
                          <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {(Object.keys(mappingStatusLabel) as MappingStatus[]).map((item) => (
                              <SelectItem key={item} value={item}>{mappingStatusLabel[item]}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="flex flex-col gap-1.5">
                        <Label className={fieldLabelCls}>来源</Label>
                        <Select value={ruleSource} onValueChange={(v) => setRuleSource(v as MappingSource)}>
                          <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {(Object.keys(mappingSourceLabel) as MappingSource[]).map((src) => (
                              <SelectItem key={src} value={src}>{mappingSourceLabel[src]}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                    </div>
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                      <div className="flex flex-col gap-1.5">
                        <Label className={fieldLabelCls}>Pattern</Label>
                        <Input value={rulePattern} onChange={(e) => setRulePattern(e.target.value)} required className="h-8 text-sm" />
                      </div>
                      <div className="flex flex-col gap-1.5">
                        <Label className={fieldLabelCls}>AI 置信度</Label>
                        <Input type="number" min="0" max="100" value={ruleAiConfidence} onChange={(e) => setRuleAiConfidence(e.target.value)} className="h-8 text-sm" />
                      </div>
                      <div className="flex flex-col gap-1.5">
                        <Label className={fieldLabelCls}>当前置信度</Label>
                        <Input type="number" min="0" max="100" value={ruleConfidence} onChange={(e) => setRuleConfidence(e.target.value)} className="h-8 text-sm" />
                      </div>
                    </div>
                    <div className="flex flex-col gap-1.5">
                      <Label className={fieldLabelCls}>说明</Label>
                      <Input value={ruleDescription} onChange={(e) => setRuleDescription(e.target.value)} className="h-8 text-sm" />
                    </div>
                    {ruleStatus === "stale" ? (
                      <div className="flex flex-col gap-1.5">
                        <Label className={fieldLabelCls}>复核原因</Label>
                        <Input value={ruleStaleReason} onChange={(e) => setRuleStaleReason(e.target.value)} className="h-8 text-sm" />
                      </div>
                    ) : null}
                    <div className="flex flex-col gap-1.5">
                      <Label className={fieldLabelCls}>Evidence refs JSON</Label>
                      <Textarea value={ruleEvidenceRefs} onChange={(e) => setRuleEvidenceRefs(e.target.value)} rows={4} className="font-mono text-xs" />
                    </div>
                    {rulePreflight ? (
                      <div className={cn(
                        "flex flex-col gap-1 rounded-[var(--radius-sm)] border p-2.5 text-xs",
                        rulePreflight.blocker_count > 0
                          ? "border-[var(--destructive)] bg-[var(--destructive)]/10"
                          : "border-[var(--border)] bg-[var(--muted)]/40"
                      )}>
                        <strong>
                          预检 {rulePreflight.blocker_count > 0 ? `${rulePreflight.blocker_count} 个阻断` : `${rulePreflight.warning_count} 个提醒`}
                        </strong>
                        {rulePreflight.matched_sample_count ? <span>样本命中 {rulePreflight.matched_sample_count} 个路径</span> : null}
                        {rulePreflight.issues.slice(0, 5).map((issue, index) => (
                          <small key={`${issue.code}-${index}`} className="text-[var(--muted-foreground)]">
                            {issue.severity === "blocker" ? "阻断" : "提醒"} · {issue.reason}
                            {issue.path ? ` · ${issue.path}` : ""}
                          </small>
                        ))}
                      </div>
                    ) : null}
                    <div className="flex gap-2">
                      <Button type="submit" size="sm" disabled={busy}>
                        {editingRuleId ? "保存规则" : "新增规则"}
                      </Button>
                      {editingRuleId ? (
                        <Button type="button" variant="outline" size="sm" onClick={resetRuleForm}>
                          取消
                        </Button>
                      ) : null}
                    </div>
                  </form>

                  <div className="flex flex-col gap-2">
                    {ruleList.map((rule) => (
                      <div key={rule.id} className="flex items-start justify-between gap-3 rounded-[var(--radius-md)] border border-[var(--border)] p-3">
                        <div className="flex min-w-0 flex-col gap-0.5">
                          <strong className="text-sm">
                            {mappingRuleTypeLabel[rule.rule_type]} · {rule.pattern}
                          </strong>
                          <span className="text-xs text-[var(--muted-foreground)]">
                            {mappingRelationshipLabel[rule.relationship]} · {mappingStatusLabel[rule.status]} · {mappingSourceLabel[rule.source]}
                          </span>
                          <span className="text-xs text-[var(--muted-foreground)]">
                            {rule.repository_id ? repositories.find((repo) => repo.id === rule.repository_id)?.name ?? "已绑定仓库" : "项目通用"} · AI {rule.ai_confidence}% · 当前 {rule.confidence}%
                          </span>
                          {rule.evidence_refs.length ? <small className="text-[11px] text-[var(--muted-foreground)]">证据 {rule.evidence_refs.length} 条</small> : null}
                          {rule.stale_reason ? <small className="text-[11px] text-[var(--muted-foreground)]">复核原因：{rule.stale_reason}</small> : null}
                          <small className="text-[11px] text-[var(--muted-foreground)]">{rule.description || "无说明"}</small>
                        </div>
                        <div className="flex shrink-0 items-center gap-0.5">
                          <Button variant="ghost" size="icon" className="h-7 w-7" type="button" onClick={() => editRule(rule)} title="编辑">
                            <PencilLine size={14} aria-hidden="true" />
                          </Button>
                          <Button variant="ghost" size="icon" className="h-7 w-7" type="button" onClick={() => void deleteRule(rule)} title="删除">
                            <Trash2 size={14} aria-hidden="true" />
                          </Button>
                        </div>
                      </div>
                    ))}
                    {ruleList.length === 0 ? <p className="text-sm text-[var(--muted-foreground)]">尚无映射规则，使用上方表单新增。</p> : null}
                  </div>
                </div>
              </div>
            ) : (
              <p className="py-10 text-center text-sm text-[var(--muted-foreground)]">从左侧选择或新建模块。</p>
            )}
          </CardContent>
        </Card>
      </div>

      <ModuleDialog mode={dialog} busy={busy} onClose={() => setDialog(null)} onSubmit={handleSubmitModule} />
    </div>
  );
}
