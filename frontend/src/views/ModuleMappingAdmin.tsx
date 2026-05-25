import { FormEvent, useEffect, useMemo, useState } from "react";
import { FolderPlus, GitBranch, Network, PencilLine, Plus, Trash2 } from "lucide-react";
import {
  createMappingRule,
  createModule,
  deleteMappingRule,
  deleteModule,
  listMappingRules,
  listModuleTree,
  listProjects,
  listWorkspaces,
  MappingRuleType,
  MappingSource,
  ModuleMappingRuleRecord,
  ModuleTreeNode,
  ProjectModuleRecord,
  ProjectRecord,
  Session,
  updateMappingRule,
  updateModule,
  WorkspaceRecord
} from "../api";
import { mappingRuleTypeLabel, mappingSourceLabel } from "../lib/labels";

type DialogMode = { kind: "create"; parentId: string | null } | { kind: "edit"; module: ProjectModuleRecord } | null;

function flattenTree(nodes: ModuleTreeNode[], acc: ProjectModuleRecord[] = []): ProjectModuleRecord[] {
  for (const node of nodes) {
    acc.push(node);
    flattenTree(node.children, acc);
  }
  return acc;
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
  const [status, setStatus] = useState<"active" | "archived">(module?.status ?? "active");

  useEffect(() => {
    if (mode?.kind === "edit") {
      setName(mode.module.name);
      setCode(mode.module.key);
      setSlug(mode.module.slug);
      setDescription(mode.module.description);
      setOwner(mode.module.owner);
      setStatus(mode.module.status);
    } else if (mode?.kind === "create") {
      setName("");
      setCode("");
      setSlug("");
      setDescription("");
      setOwner("");
      setStatus("active");
    }
  }, [mode]);

  if (!mode) return null;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onSubmit({ name, code, slug, description, owner, status });
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
  const [workspaces, setWorkspaces] = useState<WorkspaceRecord[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState("");
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [tree, setTree] = useState<ModuleTreeNode[]>([]);
  const [mappingRules, setMappingRules] = useState<ModuleMappingRuleRecord[]>([]);
  const [selectedModuleId, setSelectedModuleId] = useState("");
  const [dialog, setDialog] = useState<DialogMode>(null);

  // Rule editor state
  const [ruleType, setRuleType] = useState<MappingRuleType>("directory");
  const [rulePattern, setRulePattern] = useState("backend/app/payments/**");
  const [ruleSource, setRuleSource] = useState<MappingSource>("manual");
  const [ruleDescription, setRuleDescription] = useState("Payment implementation surface");
  const [ruleConfidence, setRuleConfidence] = useState("90");
  const [editingRuleId, setEditingRuleId] = useState<string | null>(null);

  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const allModules = useMemo(() => flattenTree(tree), [tree]);
  const selectedModule = allModules.find((m) => m.id === selectedModuleId) ?? null;
  const ruleList = useMemo(() => mappingRules.filter((r) => r.module_id === selectedModuleId), [mappingRules, selectedModuleId]);

  async function refreshProjectModules(workspaceId: string, projectId: string) {
    const [nextTree, nextRules] = await Promise.all([
      listModuleTree(workspaceId, projectId),
      listMappingRules(workspaceId, projectId)
    ]);
    setTree(nextTree);
    setMappingRules(nextRules);
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
      const wid = preferredWorkspaceId || selectedWorkspaceId || ws[0]?.id || "";
      setSelectedWorkspaceId(wid);
      if (!wid) {
        setProjects([]);
        setTree([]);
        setMappingRules([]);
        return;
      }
      const ps = await listProjects(wid);
      setProjects(ps);
      const pid = preferredProjectId || selectedProjectId || ps[0]?.id || "";
      setSelectedProjectId(pid);
      if (pid) await refreshProjectModules(wid, pid);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "模块数据加载失败");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void refreshWorkspaces();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
      if (pid) await refreshProjectModules(wid, pid);
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
          owner: payload.owner
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
      if (editingRuleId) {
        await updateMappingRule(selectedWorkspaceId, selectedProjectId, selectedModuleId, editingRuleId, actorEmail, {
          rule_type: ruleType,
          pattern: rulePattern,
          source: ruleSource,
          description: ruleDescription,
          confidence: Number(ruleConfidence)
        });
        setMessage("已更新映射规则");
      } else {
        await createMappingRule(selectedWorkspaceId, selectedProjectId, selectedModuleId, actorEmail, {
          rule_type: ruleType,
          pattern: rulePattern,
          source: ruleSource,
          description: ruleDescription,
          confidence: Number(ruleConfidence)
        });
        setMessage("已新增映射规则");
      }
      setEditingRuleId(null);
      setRulePattern("");
      setRuleDescription("");
      await refreshProjectModules(selectedWorkspaceId, selectedProjectId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "映射规则保存失败");
    } finally {
      setBusy(false);
    }
  }

  function editRule(rule: ModuleMappingRuleRecord) {
    setEditingRuleId(rule.id);
    setRuleType(rule.rule_type);
    setRulePattern(rule.pattern);
    setRuleSource(rule.source);
    setRuleDescription(rule.description);
    setRuleConfidence(String(rule.confidence));
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

  return (
    <section className="panel module-admin-panel">
      <header className="panel-head">
        <div>
          <span className="eyebrow">Modules</span>
          <h2>模块目录与代码映射</h2>
          <p className="panel-sub">维护功能模块层级，并在每个模块上绑定代码路径、API、配置等映射规则。</p>
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
                      类型
                      <select value={ruleType} onChange={(e) => setRuleType(e.target.value as MappingRuleType)}>
                        {(Object.keys(mappingRuleTypeLabel) as MappingRuleType[]).map((type) => (
                          <option key={type} value={type}>
                            {mappingRuleTypeLabel[type]}
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
                  <label>
                    Pattern
                    <input value={rulePattern} onChange={(e) => setRulePattern(e.target.value)} required />
                  </label>
                  <div className="form-row">
                    <label>
                      说明
                      <input value={ruleDescription} onChange={(e) => setRuleDescription(e.target.value)} />
                    </label>
                    <label>
                      置信度
                      <input type="number" min="0" max="100" value={ruleConfidence} onChange={(e) => setRuleConfidence(e.target.value)} />
                    </label>
                  </div>
                  <div className="form-row compact">
                    <button type="submit" className="primary-button small" disabled={busy}>
                      {editingRuleId ? "保存规则" : "新增规则"}
                    </button>
                    {editingRuleId ? (
                      <button type="button" className="ghost-button small" onClick={() => setEditingRuleId(null)}>
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
                          {mappingSourceLabel[rule.source]} · 置信度 {rule.confidence}%
                        </span>
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
