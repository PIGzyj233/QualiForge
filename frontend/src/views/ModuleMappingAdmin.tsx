import { FormEvent, useEffect, useMemo, useState } from "react";
import { FolderPlus, GitBranch, Network, PencilLine, Plus, Trash2 } from "lucide-react";
import { useParams } from "react-router-dom";
import {
  AgentStagedOutputRecord,
  createMappingRule,
  createModule,
  decideAgentStagedOutput,
  deleteMappingRule,
  deleteModule,
  generateModuleTreeDraft,
  GitRepositoryRecord,
  listMappingRules,
  listModuleTree,
  listModuleTreeDrafts,
  listProjects,
  listRepositories,
  listWorkspaces,
  MappingRelationship,
  MappingRuleType,
  MappingSource,
  MappingStatus,
  ModuleMappingRuleRecord,
  ModuleTreeNode,
  ProjectModuleRecord,
  ProjectRecord,
  Session,
  updateMappingRule,
  updateModule,
  WorkspaceRecord
} from "../api";
import { mappingRelationshipLabel, mappingRuleTypeLabel, mappingSourceLabel, mappingStatusLabel } from "../lib/labels";
import { pickExistingId } from "../lib/selection";

type DialogMode = { kind: "create"; parentId: string | null } | { kind: "edit"; module: ProjectModuleRecord } | null;

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
    <li className="module-tree-node">
      <div className={active ? "module-tree-row active" : "module-tree-row"} style={{ paddingLeft: 6 + node.depth * 16 }}>
        <button className="module-tree-label" type="button" onClick={() => onSelect(node.id)}>
          <span>{node.name}</span>
          <small>
            {node.key || "—"} · {node.reference_count} 引用 · {node.mapping_rules.length} 映射
          </small>
        </button>
        <div className="module-tree-actions">
          <button className="icon-button subtle" type="button" onClick={() => onAddChild(node.id)} title="新增子模块">
            <FolderPlus size={14} aria-hidden="true" />
          </button>
          <button className="icon-button subtle" type="button" onClick={() => onEdit(node)} title="编辑模块">
            <PencilLine size={14} aria-hidden="true" />
          </button>
          <button className="icon-button subtle" type="button" onClick={() => onDelete(node.id)} title="删除模块">
            <Trash2 size={14} aria-hidden="true" />
          </button>
        </div>
      </div>
      {node.children.length ? (
        <ul className="module-tree-children">
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

  if (!mode) return null;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onSubmit({ name, code, slug, description, owner, keywords: splitTextList(keywords), status });
  }

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <form className="dialog" onClick={(e) => e.stopPropagation()} onSubmit={handleSubmit}>
        <h3>{isEdit ? `编辑模块 · ${module?.path_label ?? ""}` : "新建模块"}</h3>
        {!isEdit && mode.parentId ? <p className="panel-sub">将作为子模块新增。</p> : null}
        <div className="form-row">
          <label>
            名称
            <input value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
          </label>
          <label>
            编号
            <input value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="可选" />
          </label>
        </div>
        <label>
          Slug
          <input value={slug} onChange={(e) => setSlug(e.target.value)} placeholder="留空自动生成" />
        </label>
        <label>
          描述
          <input value={description} onChange={(e) => setDescription(e.target.value)} />
        </label>
        <label>
          关键词
          <input value={keywords} onChange={(e) => setKeywords(e.target.value)} placeholder="payment, refund" />
        </label>
        <div className="form-row">
          <label>
            Owner
            <input value={owner} onChange={(e) => setOwner(e.target.value)} />
          </label>
          {isEdit ? (
            <label>
              状态
              <select value={status} onChange={(e) => setStatus(e.target.value as "active" | "archived")}>
                <option value="active">Active</option>
                <option value="archived">Archived</option>
              </select>
            </label>
          ) : null}
        </div>
        <div className="form-row compact">
          <button type="button" className="ghost-button" onClick={onClose} disabled={busy}>
            取消
          </button>
          <button type="submit" className="primary-button" disabled={busy || !name.trim()}>
            {isEdit ? "保存" : "创建"}
          </button>
        </div>
      </form>
    </div>
  );
}

export function ModuleMappingAdmin({ session }: { session: Session }) {
  const actorEmail = session.user.email;
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
    <section className="panel module-admin-panel">
      <header className="panel-head">
        <div>
          <span className="eyebrow">Modules</span>
          <h2>模块目录与代码映射</h2>
          <p className="panel-sub">维护人类确认的功能/能力树，并把代码路径、API、配置、协议、符号等证据绑定到模块。</p>
        </div>
        <Network size={20} aria-hidden="true" />
      </header>

      {(workspaces.length > 1 || projects.length > 1) ? (
        <div className="form-row compact">
          {workspaces.length > 1 ? (
            <label className="select-label">
              Workspace
              <select value={selectedWorkspaceId} onChange={(e) => void handleWorkspaceSwitch(e.target.value)} disabled={busy}>
                {workspaces.map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.name}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          {projects.length > 1 ? (
            <label className="select-label">
              Project
              <select value={selectedProjectId} onChange={(e) => void handleProjectSwitch(e.target.value)} disabled={busy}>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.key} · {p.name}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
        </div>
      ) : null}

      {message ? <div className="inline-notice">{message}</div> : null}

      <section className="rule-section">
        <header className="rule-section-head">
          <h4>
            <Network size={14} aria-hidden="true" /> Agent 模块目录草稿
          </h4>
          <small>{moduleDrafts.length} 个待确认</small>
        </header>
        <form className="card-form" onSubmit={handleGenerateDraft}>
          <div className="form-row">
            <label>
              仓库
              <select value={draftRepositoryId} onChange={(event) => setDraftRepositoryId(event.target.value)} disabled={busy || repositories.length === 0}>
                {repositories.map((repository) => (
                  <option key={repository.id} value={repository.id}>
                    {repository.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Ref
              <input value={draftRef} onChange={(event) => setDraftRef(event.target.value)} placeholder="默认分支" />
            </label>
            <label>
              模块上限
              <input type="number" min="3" max="80" value={draftMaxModules} onChange={(event) => setDraftMaxModules(event.target.value)} />
            </label>
          </div>
          <label>
            生成要求
            <input value={draftGuidance} onChange={(event) => setDraftGuidance(event.target.value)} placeholder="例如：优先按业务能力分组" />
          </label>
          <div className="form-row compact">
            <button type="submit" className="primary-button small" disabled={busy || !draftRepositoryId}>
              生成草稿
            </button>
          </div>
        </form>

        <div className="card-list">
          {moduleDrafts.map((draft) => {
            const items = moduleDraftItems(draft);
            return (
              <article className="member-card" key={draft.id}>
                <div>
                  <strong>{draft.title}</strong>
                  <span>{items.length} 个候选模块 · {String(draft.payload.generated_by || "agent")}</span>
                  {items.slice(0, 6).map((item) => (
                    <small key={item.draft_id}>
                      {item.parent_draft_id ? "↳ " : ""}
                      {item.name} · {(item.source_paths ?? []).slice(0, 2).join(", ") || item.slug}
                    </small>
                  ))}
                  {items.length > 6 ? <small>另有 {items.length - 6} 个候选模块</small> : null}
                </div>
                <div className="member-card-actions">
                  <button className="ghost-button small" type="button" onClick={() => void handleDraftDecision(draft, "accepted")} disabled={busy}>
                    确认
                  </button>
                  <button className="ghost-button small" type="button" onClick={() => void handleDraftDecision(draft, "rejected")} disabled={busy}>
                    拒绝
                  </button>
                </div>
              </article>
            );
          })}
          {moduleDrafts.length === 0 ? <p className="empty-state">暂无待确认模块草稿。</p> : null}
        </div>
      </section>

      <div className="module-admin-split">
        <aside className="module-tree-panel">
          <div className="module-tree-head">
            <strong>模块树</strong>
            <button className="ghost-button small" type="button" onClick={() => setDialog({ kind: "create", parentId: null })} disabled={busy || !selectedProjectId}>
              <Plus size={14} aria-hidden="true" />
              新增根模块
            </button>
          </div>
          {tree.length === 0 ? (
            <p className="empty-state">尚无模块，点击「新增根模块」开始。</p>
          ) : (
            <ul className="module-tree-list">
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
        </aside>

        <section className="module-detail-panel">
          {selectedModule ? (
            <>
              <header className="module-detail-head">
                <div>
                  <span className="eyebrow">已选模块</span>
                  <h3>{selectedModule.path_label}</h3>
                  <p>{selectedModule.description || "暂无描述"} · Owner {selectedModule.owner || "未指定"}</p>
                  {selectedModule.keywords.length ? <p>关键词 {selectedModule.keywords.join(" · ")}</p> : null}
                </div>
                <div className="module-detail-actions">
                  <button className="ghost-button small" type="button" onClick={() => setDialog({ kind: "create", parentId: selectedModule.id })} disabled={busy}>
                    <FolderPlus size={14} aria-hidden="true" /> 新增子模块
                  </button>
                  <button className="ghost-button small" type="button" onClick={() => setDialog({ kind: "edit", module: selectedModule })} disabled={busy}>
                    <PencilLine size={14} aria-hidden="true" /> 编辑
                  </button>
                </div>
              </header>

              <section className="rule-section">
                <header className="rule-section-head">
                  <h4>
                    <GitBranch size={14} aria-hidden="true" /> 映射规则
                  </h4>
                  <small>{ruleList.length} 条规则</small>
                </header>

                <form className="card-form" onSubmit={handleRuleSubmit}>
                  <div className="form-row">
                    <label>
                      仓库
                      <select value={ruleRepositoryId} onChange={(e) => setRuleRepositoryId(e.target.value)}>
                        <option value="">项目通用</option>
                        {repositories.map((repository) => (
                          <option key={repository.id} value={repository.id}>
                            {repository.name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      类型
                      <select value={ruleType} onChange={(e) => setRuleType(e.target.value as MappingRuleType)}>
                        {(Object.keys(mappingRuleTypeLabel) as MappingRuleType[]).map((type) => (
                          <option key={type} value={type}>
                            {mappingRuleTypeLabel[type]}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>
                  <div className="form-row">
                    <label>
                      关系
                      <select value={ruleRelationship} onChange={(e) => setRuleRelationship(e.target.value as MappingRelationship)}>
                        {(Object.keys(mappingRelationshipLabel) as MappingRelationship[]).map((relationship) => (
                          <option key={relationship} value={relationship}>
                            {mappingRelationshipLabel[relationship]}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      状态
                      <select value={ruleStatus} onChange={(e) => setRuleStatus(e.target.value as MappingStatus)}>
                        {(Object.keys(mappingStatusLabel) as MappingStatus[]).map((item) => (
                          <option key={item} value={item}>
                            {mappingStatusLabel[item]}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      来源
                      <select value={ruleSource} onChange={(e) => setRuleSource(e.target.value as MappingSource)}>
                        {(Object.keys(mappingSourceLabel) as MappingSource[]).map((src) => (
                          <option key={src} value={src}>
                            {mappingSourceLabel[src]}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>
                  <div className="form-row">
                    <label>
                      Pattern
                      <input value={rulePattern} onChange={(e) => setRulePattern(e.target.value)} required />
                    </label>
                    <label>
                      AI 置信度
                      <input type="number" min="0" max="100" value={ruleAiConfidence} onChange={(e) => setRuleAiConfidence(e.target.value)} />
                    </label>
                    <label>
                      当前置信度
                      <input type="number" min="0" max="100" value={ruleConfidence} onChange={(e) => setRuleConfidence(e.target.value)} />
                    </label>
                  </div>
                  <label>
                    说明
                    <input value={ruleDescription} onChange={(e) => setRuleDescription(e.target.value)} />
                  </label>
                  {ruleStatus === "stale" ? (
                    <label>
                      复核原因
                      <input value={ruleStaleReason} onChange={(e) => setRuleStaleReason(e.target.value)} />
                    </label>
                  ) : null}
                  <label>
                    Evidence refs JSON
                    <textarea value={ruleEvidenceRefs} onChange={(e) => setRuleEvidenceRefs(e.target.value)} rows={4} />
                  </label>
                  <div className="form-row compact">
                    <button type="submit" className="primary-button small" disabled={busy}>
                      {editingRuleId ? "保存规则" : "新增规则"}
                    </button>
                    {editingRuleId ? (
                      <button type="button" className="ghost-button small" onClick={resetRuleForm}>
                        取消
                      </button>
                    ) : null}
                  </div>
                </form>

                <div className="card-list">
                  {ruleList.map((rule) => (
                    <article className="member-card" key={rule.id}>
                      <div>
                        <strong>
                          {mappingRuleTypeLabel[rule.rule_type]} · {rule.pattern}
                        </strong>
                        <span>
                          {mappingRelationshipLabel[rule.relationship]} · {mappingStatusLabel[rule.status]} · {mappingSourceLabel[rule.source]}
                        </span>
                        <span>
                          {rule.repository_id ? repositories.find((repo) => repo.id === rule.repository_id)?.name ?? "已绑定仓库" : "项目通用"} · AI {rule.ai_confidence}% · 当前 {rule.confidence}%
                        </span>
                        {rule.evidence_refs.length ? <small>证据 {rule.evidence_refs.length} 条</small> : null}
                        {rule.stale_reason ? <small>复核原因：{rule.stale_reason}</small> : null}
                        <small>{rule.description || "无说明"}</small>
                      </div>
                      <div className="member-card-actions">
                        <button className="icon-button subtle" type="button" onClick={() => editRule(rule)} title="编辑">
                          <PencilLine size={14} aria-hidden="true" />
                        </button>
                        <button className="icon-button subtle" type="button" onClick={() => void deleteRule(rule)} title="删除">
                          <Trash2 size={14} aria-hidden="true" />
                        </button>
                      </div>
                    </article>
                  ))}
                  {ruleList.length === 0 ? <p className="empty-state">尚无映射规则，使用上方表单新增。</p> : null}
                </div>
              </section>
            </>
          ) : (
            <p className="empty-state">从左侧选择或新建模块。</p>
          )}
        </section>
      </div>

      <ModuleDialog mode={dialog} busy={busy} onClose={() => setDialog(null)} onSubmit={handleSubmitModule} />
    </section>
  );
}
