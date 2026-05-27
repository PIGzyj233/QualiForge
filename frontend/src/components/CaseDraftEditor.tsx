import { FormEvent, useEffect, useState } from "react";
import type { CaseDraftRecord, CaseStep, ProjectModuleRecord, TestCasePayload } from "../api/cases";
import { StepsEditor } from "./StepsEditor";

function splitList(value: string) {
  return value
    .split(/\r?\n|[,，;；]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function CaseDraftEditor({
  draft,
  modules,
  busy,
  onSave,
  onSubmitReview,
  onAddressChanges
}: {
  draft: CaseDraftRecord;
  modules: ProjectModuleRecord[];
  busy: boolean;
  onSave: (payload: Partial<TestCasePayload>) => Promise<void>;
  onSubmitReview?: () => Promise<void>;
  onAddressChanges?: (comment: string) => Promise<void>;
}) {
  const [moduleId, setModuleId] = useState(draft.module_id ?? "");
  const [title, setTitle] = useState(draft.title);
  const [steps, setSteps] = useState<CaseStep[]>(draft.steps);
  const [priority, setPriority] = useState(draft.priority);
  const [risk, setRisk] = useState(draft.risk);
  const [tags, setTags] = useState(draft.tags.join(", "));
  const [changeComment, setChangeComment] = useState("已按意见完成修改");

  useEffect(() => {
    setModuleId(draft.module_id ?? "");
    setTitle(draft.title);
    setSteps(draft.steps);
    setPriority(draft.priority);
    setRisk(draft.risk);
    setTags(draft.tags.join(", "));
  }, [draft]);

  async function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onSave({
      module_id: moduleId || null,
      title,
      steps,
      priority,
      risk,
      tags: splitList(tags),
      custom_fields: draft.custom_fields
    });
  }

  const canSubmit = Boolean(moduleId) && draft.draft_status === "editing";

  return (
    <form className="stack-form case-draft-editor" onSubmit={(event) => void handleSave(event)}>
      <label>
        模块
        <select value={moduleId} onChange={(event) => setModuleId(event.target.value)} disabled={busy}>
          <option value="">未归属</option>
          {modules.map((module) => (
            <option value={module.id} key={module.id}>
              {module.path_label}
            </option>
          ))}
        </select>
      </label>
      <label>
        标题
        <input value={title} onChange={(event) => setTitle(event.target.value)} disabled={busy} required />
      </label>
      <StepsEditor steps={steps} onChange={setSteps} disabled={busy} />
      <div className="form-row">
        <label>
          优先级
          <input value={priority} onChange={(event) => setPriority(event.target.value)} disabled={busy} />
        </label>
        <label>
          风险
          <input value={risk} onChange={(event) => setRisk(event.target.value)} disabled={busy} />
        </label>
      </div>
      <label>
        标签
        <input value={tags} onChange={(event) => setTags(event.target.value)} disabled={busy} />
      </label>
      <div className="form-row compact case-action-row">
        <button className="ghost-button" type="submit" disabled={busy}>
          保存草稿
        </button>
        {onSubmitReview ? (
          <button className="primary-button small" type="button" disabled={busy || !canSubmit} onClick={() => void onSubmitReview()}>
            提交评审
          </button>
        ) : null}
      </div>
      {onAddressChanges ? (
        <div className="form-row compact case-action-row">
          <label>
            复审说明
            <input value={changeComment} onChange={(event) => setChangeComment(event.target.value)} disabled={busy} />
          </label>
          <button className="primary-button small" type="button" disabled={busy || !changeComment.trim()} onClick={() => void onAddressChanges(changeComment)}>
            标记已修改
          </button>
        </div>
      ) : null}
      {!moduleId ? <span className="helper-copy">未选择模块的草稿不能提交评审。</span> : null}
    </form>
  );
}

