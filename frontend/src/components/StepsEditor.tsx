import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { ChangeEvent, useRef } from "react";
import type { CaseStep } from "@/api/cases";
import { Button } from "@/components/ui/button";

function autoResize(el: HTMLTextAreaElement | null) {
  if (!el) return;
  el.style.height = "auto";
  el.style.height = `${Math.min(el.scrollHeight, 320)}px`;
}

export function StepsEditor({ steps, onChange, disabled }: { steps: CaseStep[]; onChange: (next: CaseStep[]) => void; disabled?: boolean }) {
  const rowRefs = useRef<Array<HTMLTextAreaElement | null>>([]);

  function update(i: number, patch: Partial<CaseStep>) {
    onChange(steps.map((s, idx) => (idx === i ? { ...s, ...patch } : s)));
  }
  function move(i: number, delta: number) {
    const t = i + delta;
    if (t < 0 || t >= steps.length) return;
    const next = [...steps];
    [next[i], next[t]] = [next[t], next[i]];
    onChange(next);
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">步骤与预期结果</span>
        <Button type="button" variant="outline" size="sm" className="h-7 text-xs" onClick={() => onChange([...steps, { action: "", expected: "" }])} disabled={disabled}>
          <Plus size={12} />新增步骤
        </Button>
      </div>
      {steps.length === 0 && <p className="text-xs text-[var(--muted-foreground)]">尚无步骤，点击「新增步骤」开始编写。</p>}
      {steps.map((step, i) => (
        <div key={i} className="grid grid-cols-[24px_1fr_1fr_auto] gap-2 items-start">
          <span className="text-xs text-[var(--muted-foreground)] pt-2 text-center">{i + 1}</span>
          <textarea
            value={step.action}
            onChange={(e: ChangeEvent<HTMLTextAreaElement>) => { update(i, { action: e.target.value }); autoResize(e.target); }}
            placeholder="操作步骤"
            rows={2}
            disabled={disabled}
            ref={(el) => { rowRefs.current[i] = el; autoResize(el); }}
            className="rounded-[var(--radius-sm)] border border-[var(--input)] bg-[var(--card)] px-2 py-1.5 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-[var(--ring)]"
          />
          <textarea
            value={step.expected}
            onChange={(e: ChangeEvent<HTMLTextAreaElement>) => { update(i, { expected: e.target.value }); autoResize(e.target); }}
            placeholder="预期结果"
            rows={2}
            disabled={disabled}
            className="rounded-[var(--radius-sm)] border border-[var(--input)] bg-[var(--card)] px-2 py-1.5 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-[var(--ring)]"
          />
          <div className="flex flex-col gap-0.5 pt-1">
            <Button type="button" variant="ghost" size="icon" className="h-6 w-6" onClick={() => move(i, -1)} disabled={disabled || i === 0}><ArrowUp size={12} /></Button>
            <Button type="button" variant="ghost" size="icon" className="h-6 w-6" onClick={() => move(i, 1)} disabled={disabled || i === steps.length - 1}><ArrowDown size={12} /></Button>
            <Button type="button" variant="ghost" size="icon" className="h-6 w-6 text-[var(--destructive)]" onClick={() => onChange(steps.filter((_, idx) => idx !== i))} disabled={disabled}><Trash2 size={12} /></Button>
          </div>
        </div>
      ))}
    </div>
  );
}
