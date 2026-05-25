import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { ChangeEvent, useRef } from "react";
import type { CaseStep } from "../api";

function autoResize(el: HTMLTextAreaElement | null) {
  if (!el) return;
  el.style.height = "auto";
  el.style.height = `${Math.min(el.scrollHeight, 320)}px`;
}

export function StepsEditor({
  steps,
  onChange,
  disabled
}: {
  steps: CaseStep[];
  onChange: (next: CaseStep[]) => void;
  disabled?: boolean;
}) {
  const rowRefs = useRef<Array<HTMLTextAreaElement | null>>([]);

  function update(index: number, patch: Partial<CaseStep>) {
    const next = steps.map((step, i) => (i === index ? { ...step, ...patch } : step));
    onChange(next);
  }

  function move(index: number, delta: number) {
    const target = index + delta;
    if (target < 0 || target >= steps.length) return;
    const next = [...steps];
    [next[index], next[target]] = [next[target], next[index]];
    onChange(next);
  }

  function add() {
    onChange([...steps, { action: "", expected: "" }]);
  }

  function remove(index: number) {
    onChange(steps.filter((_, i) => i !== index));
  }

  return (
    <div className="steps-editor">
      <div className="steps-editor-head">
        <h4>步骤与预期结果</h4>
        <button type="button" className="ghost-button small" onClick={add} disabled={disabled}>
          <Plus size={14} aria-hidden="true" />
          新增步骤
        </button>
      </div>

      <div className="steps-editor-table">
        <div className="steps-editor-row steps-editor-head-row">
          <span>#</span>
          <span>操作步骤</span>
          <span>预期结果</span>
          <span aria-label="操作"></span>
        </div>
        {steps.length === 0 ? (
          <p className="empty-state">尚无步骤，点击「新增步骤」开始编写。</p>
        ) : null}
        {steps.map((step, index) => (
          <div className="steps-editor-row" key={index}>
            <span className="steps-editor-index">{index + 1}</span>
            <textarea
              value={step.action}
              onChange={(e: ChangeEvent<HTMLTextAreaElement>) => {
                update(index, { action: e.target.value });
                autoResize(e.target);
              }}
              placeholder="例：打开收银台，选择微信支付"
              rows={2}
              disabled={disabled}
              ref={(el) => {
                rowRefs.current[index] = el;
                autoResize(el);
              }}
            />
            <textarea
              value={step.expected}
              onChange={(e: ChangeEvent<HTMLTextAreaElement>) => {
                update(index, { expected: e.target.value });
                autoResize(e.target);
              }}
              placeholder="例：跳转到微信支付二维码页面，金额一致"
              rows={2}
              disabled={disabled}
            />
            <div className="steps-editor-actions">
              <button type="button" className="icon-button subtle" onClick={() => move(index, -1)} disabled={disabled || index === 0} title="上移">
                <ArrowUp size={14} aria-hidden="true" />
              </button>
              <button type="button" className="icon-button subtle" onClick={() => move(index, 1)} disabled={disabled || index === steps.length - 1} title="下移">
                <ArrowDown size={14} aria-hidden="true" />
              </button>
              <button type="button" className="icon-button subtle" onClick={() => remove(index)} disabled={disabled} title="删除">
                <Trash2 size={14} aria-hidden="true" />
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
