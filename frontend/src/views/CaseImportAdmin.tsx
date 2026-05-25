import { FormEvent, useEffect, useState } from "react";
import { ClipboardCheck, FileText, PencilLine } from "lucide-react";
import {
  bulkImportTestCases,
  bulkUpdateImportDrafts,
  CaseStep,
  ImportBatchRecord,
  ImportDraftRecord,
  listImportBatches,
  listImportDrafts,
  listModules,
  listProjects,
  listTestCases,
  listWorkspaces,
  ProjectRecord,
  ProjectModuleRecord,
  Session,
  submitImportReview,
  TestCaseRecord,
  uploadImportBatch,
  WorkspaceRecord
} from "../api";
import { Pagination } from "../components/Pagination";
import { StepsEditor } from "../components/StepsEditor";
import { usePagination } from "../hooks/usePagination";
import { statusLabel } from "../lib/labels";

export function CaseImportAdmin({ session }: { session: Session }) {
  const actorEmail = session.user.email;
  const [workspaces, setWorkspaces] = useState<WorkspaceRecord[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState("");
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [modules, setModules] = useState<ProjectModuleRecord[]>([]);
  const [batches, setBatches] = useState<ImportBatchRecord[]>([]);
  const [selectedBatchId, setSelectedBatchId] = useState("");
  const [drafts, setDrafts] = useState<ImportDraftRecord[]>([]);
  const [testCases, setTestCases] = useState<TestCaseRecord[]>([]);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [bulkTitle, setBulkTitle] = useState("");
  const [bulkModuleId, setBulkModuleId] = useState("");
  const [bulkSteps, setBulkSteps] = useState<CaseStep[]>([]);
  const [bulkPriority, setBulkPriority] = useState("P1");
  const [bulkRisk, setBulkRisk] = useState("high");
  const [bulkTags, setBulkTags] = useState("checkout, imported");
  const [bulkCustomFields, setBulkCustomFields] = useState("{\"source\":\"legacy\"}");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const draftsPagination = usePagination(drafts, 10);

  async function refreshImportProject(workspaceId: string, projectId: string, preferredBatchId?: string) {
    const [nextModules, nextBatches, nextTestCases] = await Promise.all([
      listModules(workspaceId, projectId),
      listImportBatches(workspaceId, projectId),
      listTestCases(workspaceId, projectId)
    ]);
    setModules(nextModules);
    setBatches(nextBatches);
    setTestCases(nextTestCases);
    const nextBatchId = preferredBatchId || selectedBatchId || nextBatches[0]?.id || "";
    setSelectedBatchId(nextBatchId);
    setDrafts(nextBatchId ? await listImportDrafts(workspaceId, projectId, nextBatchId) : []);
    if (!bulkModuleId && nextModules[0]) {
      setBulkModuleId(nextModules[0].id);
    }
  }

  async function refreshImportWorkspaces(preferredWorkspaceId?: string, preferredProjectId?: string, preferredBatchId?: string) {
    setBusy(true);
    setMessage(null);
    try {
      const nextWorkspaces = await listWorkspaces(actorEmail);
      setWorkspaces(nextWorkspaces);
      const nextWorkspaceId = preferredWorkspaceId || selectedWorkspaceId || nextWorkspaces[0]?.id || "";
      setSelectedWorkspaceId(nextWorkspaceId);
      if (!nextWorkspaceId) return;
      const nextProjects = await listProjects(nextWorkspaceId);
      setProjects(nextProjects);
      const nextProjectId = preferredProjectId || selectedProjectId || nextProjects[0]?.id || "";
      setSelectedProjectId(nextProjectId);
      if (nextProjectId) {
        await refreshImportProject(nextWorkspaceId, nextProjectId, preferredBatchId);
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "导入数据加载失败");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void refreshImportWorkspaces();
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
        await refreshImportProject(workspaceId, nextProjectId);
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "导入 Workspace 切换失败");
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
      await refreshImportProject(selectedWorkspaceId, projectId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "导入 Project 切换失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleBatchSelect(batchId: string) {
    setSelectedBatchId(batchId);
    if (!selectedWorkspaceId || !selectedProjectId || !batchId) return;
    setBusy(true);
    setMessage(null);
    try {
      setDrafts(await listImportDrafts(selectedWorkspaceId, selectedProjectId, batchId));
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "导入草稿加载失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedWorkspaceId || !selectedProjectId || !importFile) return;
    setBusy(true);
    setMessage(null);
    try {
      const batch = await uploadImportBatch(selectedWorkspaceId, selectedProjectId, actorEmail, importFile);
      await new Promise((resolve) => window.setTimeout(resolve, 700));
      setMessage(`已上传并创建导入 Job：${batch.file_name}`);
      setImportFile(null);
      await refreshImportProject(selectedWorkspaceId, selectedProjectId, batch.id);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "文件上传失败");
    } finally {
      setBusy(false);
    }
  }

  function parseTagsInput(value: string): string[] {
    return value.split(/[,，;；\s]+/).map((item) => item.trim()).filter(Boolean);
  }

  function buildBulkPayload() {
    const payload: Record<string, unknown> = {};
    if (bulkTitle.trim()) payload.title = bulkTitle.trim();
    if (bulkModuleId) payload.module_id = bulkModuleId;
    const cleanedSteps = bulkSteps.filter((s) => s.action.trim() || s.expected.trim());
    if (cleanedSteps.length) payload.steps = cleanedSteps;
    if (bulkPriority.trim()) payload.priority = bulkPriority.trim();
    if (bulkRisk.trim()) payload.risk = bulkRisk.trim();
    const tags = parseTagsInput(bulkTags);
    if (tags.length) payload.tags = tags;
    if (bulkCustomFields.trim()) {
      payload.custom_fields = JSON.parse(bulkCustomFields) as Record<string, string>;
    }
    return payload;
  }

  async function handleBulkUpdate() {
    if (!selectedWorkspaceId || !selectedProjectId || !selectedBatchId) return;
    setBusy(true);
    setMessage(null);
    try {
      await bulkUpdateImportDrafts(selectedWorkspaceId, selectedProjectId, selectedBatchId, actorEmail, buildBulkPayload());
      setMessage("已批量修正导入草稿");
      await refreshImportProject(selectedWorkspaceId, selectedProjectId, selectedBatchId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "批量修正失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleSubmitReview() {
    if (!selectedWorkspaceId || !selectedProjectId || !selectedBatchId) return;
    setBusy(true);
    setMessage(null);
    try {
      const batch = await submitImportReview(selectedWorkspaceId, selectedProjectId, selectedBatchId, actorEmail);
      setMessage(`已提交评审：${statusLabel[batch.status]}`);
      await refreshImportProject(selectedWorkspaceId, selectedProjectId, selectedBatchId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "提交评审失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleBulkImport() {
    if (!selectedWorkspaceId || !selectedProjectId || !selectedBatchId) return;
    setBusy(true);
    setMessage(null);
    try {
      const result = await bulkImportTestCases(selectedWorkspaceId, selectedProjectId, selectedBatchId, actorEmail);
      setMessage(`已完成入库：${result.imported_count} 条已通过评审的用例`);
      await refreshImportProject(selectedWorkspaceId, selectedProjectId, selectedBatchId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "完成入库失败");
    } finally {
      setBusy(false);
    }
  }

  const selectedProject = projects.find((project) => project.id === selectedProjectId);
  const selectedBatch = batches.find((batch) => batch.id === selectedBatchId);
  const moduleById = new Map(modules.map((module) => [module.id, module]));

  return (
    <section className="section-block import-admin">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Case Import</span>
          <h2>历史用例导入</h2>
        </div>
        <ClipboardCheck size={20} aria-hidden="true" />
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
          <strong>{selectedProject ? `${selectedProject.key} · ${selectedProject.name}` : "尚未选择 Project"}</strong>
          <span>{batches.length} import batches · {drafts.length} preview drafts · {testCases.length} formal cases</span>
        </div>

        <div className="admin-grid">
          <section className="admin-pane" aria-label="上传历史用例">
            <div className="pane-heading">
              <div>
                <span className="eyebrow">Upload</span>
                <h3>Excel / CSV</h3>
              </div>
              <FileText size={18} aria-hidden="true" />
            </div>
            <form className="stack-form" onSubmit={handleUpload}>
              <label>
                文件
                <input
                  type="file"
                  accept=".csv,.xlsx"
                  onChange={(event) => setImportFile(event.target.files?.[0] ?? null)}
                  required
                />
              </label>
              <button className="ghost-button" type="submit" disabled={busy || !selectedWorkspaceId || !selectedProjectId || !importFile}>
                上传并解析
              </button>
            </form>
            <div className="data-list">
              {batches.map((batch) => (
                <div className="data-row module-row" key={batch.id}>
                  <div>
                    <strong>{batch.file_name} · {statusLabel[batch.status]}</strong>
                    <span>{batch.row_count} rows · job {batch.job_id?.slice(0, 8) ?? "none"}</span>
                    <small>{batch.original_file_path}</small>
                  </div>
                  <button className="ghost-button" type="button" onClick={() => void handleBatchSelect(batch.id)}>
                    查看
                  </button>
                </div>
              ))}
              {batches.length === 0 ? <p className="empty-state">暂无导入批次</p> : null}
            </div>
          </section>

          <section className="admin-pane" aria-label="批量修正导入草稿">
            <div className="pane-heading">
              <div>
                <span className="eyebrow">Bulk Fix</span>
                <h3>预览批量修正</h3>
              </div>
              <PencilLine size={18} aria-hidden="true" />
            </div>
            <form className="stack-form" onSubmit={(event) => event.preventDefault()}>
              <div className="form-row">
                <label>
                  标题
                  <input value={bulkTitle} onChange={(event) => setBulkTitle(event.target.value)} />
                </label>
                <label>
                  模块
                  <select value={bulkModuleId} onChange={(event) => setBulkModuleId(event.target.value)}>
                    <option value="">不修改</option>
                    {modules.map((module) => (
                      <option value={module.id} key={module.id}>
                        {module.key} · {module.name}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <StepsEditor steps={bulkSteps} onChange={setBulkSteps} disabled={busy} />
              <div className="form-row">
                <label>
                  优先级
                  <input value={bulkPriority} onChange={(event) => setBulkPriority(event.target.value)} />
                </label>
                <label>
                  风险
                  <input value={bulkRisk} onChange={(event) => setBulkRisk(event.target.value)} />
                </label>
              </div>
              <label>
                标签
                <input value={bulkTags} onChange={(event) => setBulkTags(event.target.value)} />
              </label>
              <label>
                自定义字段 JSON
                <input value={bulkCustomFields} onChange={(event) => setBulkCustomFields(event.target.value)} />
              </label>
              <div className="form-row compact">
                <button className="ghost-button" type="button" onClick={() => void handleBulkUpdate()} disabled={busy || !selectedBatchId || drafts.length === 0}>
                  批量修正
                </button>
                <button className="ghost-button" type="button" onClick={() => void handleSubmitReview()} disabled={busy || !selectedBatchId || drafts.length === 0}>
                  提交评审
                </button>
                <button className="primary-button small" type="button" onClick={() => void handleBulkImport()} disabled={busy || !selectedBatchId || drafts.length === 0}>
                  完成入库
                </button>
              </div>
            </form>
          </section>
        </div>

        <section className="audit-pane" aria-label="导入草稿预览">
          <div className="pane-heading">
            <div>
              <span className="eyebrow">Preview</span>
              <h3>导入草稿</h3>
            </div>
            <ClipboardCheck size={18} aria-hidden="true" />
          </div>
          <div className="data-list">
            {draftsPagination.currentItems.map((draft) => (
              <div className="data-row wide" key={draft.id}>
                <div>
                  <strong>
                    #{draft.source_row_index} {draft.title} · {statusLabel[draft.status]}
                  </strong>
                  <span>
                    {moduleById.get(draft.module_id ?? "")?.key ?? "未归属"} · {draft.priority} · {draft.risk} · {draft.tags.join(", ") || "no tags"}
                  </span>
                  <small>
                    {draft.steps.length} 个步骤 ·{" "}
                    {draft.steps.filter((s) => s.expected).length} 个步骤有预期
                  </small>
                </div>
              </div>
            ))}
            {drafts.length === 0 ? <p className="empty-state">{selectedBatch ? "暂无草稿" : "选择或上传导入批次"}</p> : null}
          </div>
          <Pagination
            currentPage={draftsPagination.currentPage}
            totalPages={draftsPagination.totalPages}
            totalItems={draftsPagination.totalItems}
            onPageChange={draftsPagination.goToPage}
          />
        </section>
      </div>
    </section>
  );
}
