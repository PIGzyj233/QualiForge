import { FormEvent, useEffect, useState } from "react";
import type { CaseDraftRecord, CaseStep, ProjectModuleRecord, TestCasePayload } from "@/api/cases";
import { StepsEditor } from "./StepsEditor";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

function splitList(value: string) {
  return value.split(/\r?\n|[,，;；]/).map((s) => s.trim()).filter(Boolean);
}

export function CaseDraftEditor({
  draft, modules, busy, onSave, onSubmitReview, onAddressChanges
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
    setModuleId(draft.module_id ?? ""); setTitle(draft.title); setSteps(draft.steps);
    setPriority(draft.priority); setRisk(draft.risk); setTags(draft.tags.join(", "));
  }, [draft]);

  async function handleSave(e: FormEvent) {
    e.preventDefault();
    await onSave({ module_id: moduleId || null, title, steps, priority, risk, tags: splitList(tags), custom_fields: draft.custom_fields });
  }

  const canSubmit = Boolean(moduleId) && draft.draft_status === "editing";
  const f = "flex flex-col gap-1.5";

  return (
    <form onSubmit={(e) => void handleSave(e)} className="flex flex-col gap-3">
      <div className={f}>
        <Label>模块</Label>
        <Select value={moduleId || "__none__"} onValueChange={(v) => setModuleId(v === "__none__" ? "" : v)} disabled={busy}>
          <SelectTrigger><SelectValue placeholder="未归属" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="__none__">未归属</SelectItem>
            {modules.map((m) => <SelectItem key={m.id} value={m.id}>{m.path_label}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
      <div className={f}><Label>标题</Label><Input value={title} onChange={(e) => setTitle(e.target.value)} disabled={busy} required /></div>
      <StepsEditor steps={steps} onChange={setSteps} disabled={busy} />
      <div className="grid grid-cols-2 gap-3">
        <div className={f}><Label>优先级</Label><Input value={priority} onChange={(e) => setPriority(e.target.value)} disabled={busy} /></div>
        <div className={f}><Label>风险</Label><Input value={risk} onChange={(e) => setRisk(e.target.value)} disabled={busy} /></div>
      </div>
      <div className={f}><Label>标签</Label><Input value={tags} onChange={(e) => setTags(e.target.value)} disabled={busy} /></div>
      <div className="flex gap-2">
        <Button variant="outline" type="submit" disabled={busy}>保存草稿</Button>
        {onSubmitReview && <Button type="button" disabled={busy || !canSubmit} onClick={() => void onSubmitReview()}>提交评审</Button>}
      </div>
      {onAddressChanges && (
        <div className="flex gap-2 items-end">
          <div className={`${f} flex-1`}><Label>复审说明</Label><Input value={changeComment} onChange={(e) => setChangeComment(e.target.value)} disabled={busy} /></div>
          <Button type="button" disabled={busy || !changeComment.trim()} onClick={() => void onAddressChanges(changeComment)}>标记已修改</Button>
        </div>
      )}
      {!moduleId && <p className="text-xs text-[var(--muted-foreground)]">未选择模块的草稿不能提交评审。</p>}
    </form>
  );
}
