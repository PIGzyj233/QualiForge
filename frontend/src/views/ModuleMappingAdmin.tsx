import { FormEvent, useEffect, useState } from "react";
import { FileText, FolderKanban, GitBranch, Network, PencilLine, Trash2 } from "lucide-react";
import {
  createMappingRule,
  createModule,
  deleteMappingRule,
  deleteModule,
  listMappingRules,
  listModules,
  listProjects,
  listWorkspaces,
  MappingRuleType,
  MappingSource,
  ModuleMappingRuleRecord,
  ProjectRecord,
  ProjectModuleRecord,
  Session,
  updateMappingRule,
  updateModule,
  WorkspaceRecord
} from "../api";
import { mappingRuleTypeLabel, mappingSourceLabel } from "../lib/labels";

export function ModuleMappingAdmin({ session }: { session: Session }) {
  const actorEmail = session.user.email;
  const [workspaces, setWorkspaces] = useState<WorkspaceRecord[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState("");
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [modules, setModules] = useState<ProjectModuleRecord[]>([]);
  const [mappingRules, setMappingRules] = useState<ModuleMappingRuleRecord[]>([]);
  const [moduleKey, setModuleKey] = useState("PAYMENT");
  const [moduleName, setModuleName] = useState("支付与退款");
  const [moduleDescription, setModuleDescription] = useState("Checkout payment and refund behavior");
  const [moduleOwner, setModuleOwner] = useState("Checkout QA");
  const [editingModuleId, setEditingModuleId] = useState<string | null>(null);
  const [ruleModuleId, setRuleModuleId] = useState("");
  const [ruleType, setRuleType] = useState<MappingRuleType>("directory");
  const [rulePattern, setRulePattern] = useState("backend/app/payments/**");
  const [ruleSource, setRuleSource] = useState<MappingSource>("manual");
  const [ruleDescription, setRuleDescription] = useState("Payment implementation surface");
  const [ruleConfidence, setRuleConfidence] = useState("90");
  const [editingRuleId, setEditingRuleId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function refreshProjectModules(workspaceId: string, projectId: string) {
    const [nextModules, nextRules] = await Promise.all([listModules(workspaceId, projectId), listMappingRules(workspaceId, projectId)]);
    setModules(nextModules);
    setMappingRules(nextRules);
    if (!ruleModuleId || !nextModules.some((module) => module.id === ruleModuleId)) {
      setRuleModuleId(nextModules[0]?.id ?? "");
    }
  }

  async function refreshModuleWorkspaces(preferredWorkspaceId?: string, preferredProjectId?: string) {
    setBusy(true);
    setMessage(null);
    try {
      const nextWorkspaces = await listWorkspaces(actorEmail);
      setWorkspaces(nextWorkspaces);
      const nextWorkspaceId = preferredWorkspaceId || selectedWorkspaceId || nextWorkspaces[0]?.id || "";
      setSelectedWorkspaceId(nextWorkspaceId);
      if (!nextWorkspaceId) {
        setProjects([]);
        setModules([]);
        setMappingRules([]);
        return;
      }

      const nextProjects = await listProjects(nextWorkspaceId);
      setProjects(nextProjects);
      const nextProjectId = preferredProjectId || selectedProjectId || nextProjects[0]?.id || "";
      setSelectedProjectId(nextProjectId);
      if (nextProjectId) {
        await refreshProjectModules(nextWorkspaceId, nextProjectId);
      } else {
        setModules([]);
        setMappingRules([]);
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "模块配置加载失败");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void refreshModuleWorkspaces();
  }, []);

  async function handleWorkspaceSwitch(workspaceId: string) {
    setSelectedWorkspaceId(workspaceId);
    setBusy(true);
    setMessage(null);
    try {
      const nextProjects = await listProjects(workspaceId);
      setProjects(nextProjects);
      const nextProjectId = nextProjects[0]?.id ?? "";
      setSelectedProjectId(nextProjectId);
      if (nextProjectId) {
        await refreshProjectModules(workspaceId, nextProjectId);
      } else {
        setModules([]);
        setMappingRules([]);
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "模块 Workspace 切换失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleProjectSwitch(projectId: string) {
    setSelectedProjectId(projectId);
    if (!selectedWorkspaceId || !projectId) return;
    setBusy(true);
    setMessage(null);
    try {
      await refreshProjectModules(selectedWorkspaceId, projectId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "模块项目切换失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleModuleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedWorkspaceId || !selectedProjectId) return;
    setBusy(true);
    setMessage(null);
    try {
      if (editingModuleId) {
        const module = await updateModule(selectedWorkspaceId, selectedProjectId, editingModuleId, actorEmail, {
          name: moduleName,
          description: moduleDescription,
          owner: moduleOwner
        });
        setMessage(`已更新模块：${module.key}`);
      } else {
        const module = await createModule(selectedWorkspaceId, selectedProjectId, actorEmail, {
          key: moduleKey,
          name: moduleName,
          description: moduleDescription,
          owner: moduleOwner
        });
        setRuleModuleId(module.id);
        setMessage(`已创建模块：${module.key}`);
      }
      clearModuleForm();
      await refreshProjectModules(selectedWorkspaceId, selectedProjectId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "模块保存失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleModuleDelete(moduleId: string) {
    if (!selectedWorkspaceId || !selectedProjectId) return;
    setBusy(true);
    setMessage(null);
    try {
      await deleteModule(selectedWorkspaceId, selectedProjectId, moduleId, actorEmail);
      setMessage("已删除模块");
      await refreshProjectModules(selectedWorkspaceId, selectedProjectId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "模块删除失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleRuleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedWorkspaceId || !selectedProjectId || !ruleModuleId) return;
    setBusy(true);
    setMessage(null);
    try {
      if (editingRuleId) {
        const rule = await updateMappingRule(selectedWorkspaceId, selectedProjectId, ruleModuleId, editingRuleId, actorEmail, {
          rule_type: ruleType,
          pattern: rulePattern,
          source: ruleSource,
          description: ruleDescription,
          confidence: Number(ruleConfidence)
        });
        setMessage(`已更新映射规则：${mappingRuleTypeLabel[rule.rule_type]}`);
      } else {
        const rule = await createMappingRule(selectedWorkspaceId, selectedProjectId, ruleModuleId, actorEmail, {
          rule_type: ruleType,
          pattern: rulePattern,
          source: ruleSource,
          description: ruleDescription,
          confidence: Number(ruleConfidence)
        });
        setMessage(`已创建映射规则：${mappingRuleTypeLabel[rule.rule_type]}`);
      }
      clearRuleForm();
      await refreshProjectModules(selectedWorkspaceId, selectedProjectId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "映射规则保存失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleRuleDelete(rule: ModuleMappingRuleRecord) {
    if (!selectedWorkspaceId || !selectedProjectId) return;
    setBusy(true);
    setMessage(null);
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

  function editModule(module: ProjectModuleRecord) {
    setEditingModuleId(module.id);
    setModuleKey(module.key);
    setModuleName(module.name);
    setModuleDescription(module.description);
    setModuleOwner(module.owner);
  }

  function editRule(rule: ModuleMappingRuleRecord) {
    setEditingRuleId(rule.id);
    setRuleModuleId(rule.module_id);
    setRuleType(rule.rule_type);
    setRulePattern(rule.pattern);
    setRuleSource(rule.source);
    setRuleDescription(rule.description);
    setRuleConfidence(String(rule.confidence));
  }

  function clearModuleForm() {
    setEditingModuleId(null);
    setModuleKey("");
    setModuleName("");
    setModuleDescription("");
    setModuleOwner("");
  }

  function clearRuleForm() {
    setEditingRuleId(null);
    setRuleType("directory");
    setRulePattern("");
    setRuleSource("manual");
    setRuleDescription("");
    setRuleConfidence("90");
  }

  const selectedWorkspace = workspaces.find((workspace) => workspace.id === selectedWorkspaceId);
  const selectedProject = projects.find((project) => project.id === selectedProjectId);
  const moduleById = new Map(modules.map((module) => [module.id, module]));

  return (
    <section className="section-block module-admin">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Module Mapping</span>
          <h2>模块和映射规则</h2>
        </div>
        <Network size={20} aria-hidden="true" />
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
          <label className="select-label">
            当前 Project
            <select
              value={selectedProjectId}
              onChange={(event) => void handleProjectSwitch(event.target.value)}
              disabled={busy || projects.length === 0}
            >
              <option value="">未选择</option>
              {projects.map((project) => (
                <option value={project.id} key={project.id}>
                  {project.key} · {project.name}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="admin-context">
          <strong>{selectedProject ? `${selectedProject.key} · ${selectedProject.name}` : selectedWorkspace?.name ?? "尚未选择 Project"}</strong>
          <span>{selectedProject ? `${modules.length} modules · ${mappingRules.length} mapping rules` : "先创建 Project，然后维护业务模块和技术映射。"}</span>
        </div>

        <div className="admin-grid">
          <section className="admin-pane" aria-label="模块管理">
            <div className="pane-heading">
              <div>
                <span className="eyebrow">Modules</span>
                <h3>模块/功能域</h3>
              </div>
              <FolderKanban size={18} aria-hidden="true" />
            </div>
            <form className="stack-form" onSubmit={handleModuleSave}>
              <div className="form-row">
                <label>
                  Key
                  <input
                    value={moduleKey}
                    onChange={(event) => setModuleKey(event.target.value.toUpperCase())}
                    disabled={Boolean(editingModuleId)}
                    required
                  />
                </label>
                <label>
                  名称
                  <input value={moduleName} onChange={(event) => setModuleName(event.target.value)} required />
                </label>
              </div>
              <label>
                描述
                <input value={moduleDescription} onChange={(event) => setModuleDescription(event.target.value)} />
              </label>
              <div className="form-row compact">
                <label>
                  Owner
                  <input value={moduleOwner} onChange={(event) => setModuleOwner(event.target.value)} />
                </label>
                <button className="ghost-button" type="submit" disabled={busy || !selectedWorkspaceId || !selectedProjectId}>
                  {editingModuleId ? "保存模块" : "创建模块"}
                </button>
                {editingModuleId ? (
                  <button className="ghost-button" type="button" onClick={clearModuleForm}>
                    取消
                  </button>
                ) : null}
              </div>
            </form>
            <div className="data-list">
              {modules.map((module) => (
                <div className="data-row module-row" key={module.id}>
                  <div>
                    <strong>{module.key} · {module.name}</strong>
                    <span>{module.description || "无描述"} · owner {module.owner || "none"} · {module.mapping_rules.length} rules</span>
                  </div>
                  <button className="icon-button subtle" type="button" onClick={() => editModule(module)} title="编辑模块">
                    <PencilLine size={16} aria-hidden="true" />
                  </button>
                  <button className="icon-button subtle" type="button" disabled={busy} onClick={() => void handleModuleDelete(module.id)} title="删除模块">
                    <Trash2 size={16} aria-hidden="true" />
                  </button>
                </div>
              ))}
              {modules.length === 0 ? <p className="empty-state">暂无模块</p> : null}
            </div>
          </section>

          <section className="admin-pane" aria-label="映射规则管理">
            <div className="pane-heading">
              <div>
                <span className="eyebrow">Mapping Rules</span>
                <h3>技术对象映射</h3>
              </div>
              <GitBranch size={18} aria-hidden="true" />
            </div>
            <form className="stack-form" onSubmit={handleRuleSave}>
              <label>
                模块
                <select
                  value={ruleModuleId}
                  onChange={(event) => setRuleModuleId(event.target.value)}
                  disabled={Boolean(editingRuleId)}
                  required
                >
                  <option value="">未选择</option>
                  {modules.map((module) => (
                    <option value={module.id} key={module.id}>
                      {module.key} · {module.name}
                    </option>
                  ))}
                </select>
              </label>
              <div className="form-row">
                <label>
                  类型
                  <select value={ruleType} onChange={(event) => setRuleType(event.target.value as MappingRuleType)}>
                    {(Object.keys(mappingRuleTypeLabel) as MappingRuleType[]).map((item) => (
                      <option value={item} key={item}>
                        {mappingRuleTypeLabel[item]}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  来源
                  <select value={ruleSource} onChange={(event) => setRuleSource(event.target.value as MappingSource)}>
                    {(Object.keys(mappingSourceLabel) as MappingSource[]).map((item) => (
                      <option value={item} key={item}>
                        {mappingSourceLabel[item]}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <label>
                Pattern
                <input value={rulePattern} onChange={(event) => setRulePattern(event.target.value)} required />
              </label>
              <div className="form-row compact">
                <label>
                  说明
                  <input value={ruleDescription} onChange={(event) => setRuleDescription(event.target.value)} />
                </label>
                <label>
                  置信度
                  <input type="number" min="0" max="100" value={ruleConfidence} onChange={(event) => setRuleConfidence(event.target.value)} />
                </label>
                <button className="ghost-button" type="submit" disabled={busy || !selectedWorkspaceId || !selectedProjectId || modules.length === 0}>
                  {editingRuleId ? "保存规则" : "添加规则"}
                </button>
                {editingRuleId ? (
                  <button className="ghost-button" type="button" onClick={clearRuleForm}>
                    取消
                  </button>
                ) : null}
              </div>
            </form>
          </section>
        </div>

        <section className="audit-pane" aria-label="Module Mapping 列表">
          <div className="pane-heading">
            <div>
              <span className="eyebrow">Reusable References</span>
              <h3>可引用映射规则</h3>
            </div>
            <FileText size={18} aria-hidden="true" />
          </div>
          <div className="data-list">
            {mappingRules.map((rule) => (
              <div className="data-row module-row" key={rule.id}>
                <div>
                  <strong>{moduleById.get(rule.module_id)?.key ?? "UNKNOWN"} · {mappingRuleTypeLabel[rule.rule_type]} · {rule.pattern}</strong>
                  <span>{mappingSourceLabel[rule.source]} · confidence {rule.confidence}% · id {rule.id}</span>
                  <small>{rule.description || "无说明"}</small>
                </div>
                <button className="icon-button subtle" type="button" onClick={() => editRule(rule)} title="编辑映射规则">
                  <PencilLine size={16} aria-hidden="true" />
                </button>
                <button className="icon-button subtle" type="button" disabled={busy} onClick={() => void handleRuleDelete(rule)} title="删除映射规则">
                  <Trash2 size={16} aria-hidden="true" />
                </button>
              </div>
            ))}
            {mappingRules.length === 0 ? <p className="empty-state">暂无映射规则</p> : null}
          </div>
        </section>
      </div>
    </section>
  );
}
