import type { CaseRevisionRecord, CaseStep } from "@/api/cases";

function normalizeSteps(value: unknown): CaseStep[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => {
    if (item && typeof item === "object" && !Array.isArray(item)) {
      const o = item as Record<string, unknown>;
      return { action: String(o.action ?? ""), expected: String(o.expected ?? "") };
    }
    return { action: String(item ?? ""), expected: "" };
  });
}

export function CaseRevisionViewer({ revision }: { revision: CaseRevisionRecord | null }) {
  if (!revision) return <p className="text-sm text-[var(--muted-foreground)]">暂无正式版本</p>;
  const steps = normalizeSteps(revision.content_snapshot.steps);
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-2 text-xs text-[var(--muted-foreground)]">
        <span>Rev {revision.revision_number}</span>
        <span>{revision.module_path_label || "未归属"}</span>
        <span>{String(revision.content_snapshot.priority ?? "P2")}</span>
        <span>{String(revision.content_snapshot.risk ?? "medium")}</span>
      </div>
      <p className="text-sm font-semibold">{String(revision.content_snapshot.title ?? "Untitled case")}</p>
      <ol className="flex flex-col gap-1.5">
        {steps.map((step, i) => (
          <li key={i} className="text-sm">
            <span className="font-medium">{step.action || "(空步骤)"}</span>
            {step.expected && <span className="text-[var(--muted-foreground)]"> → {step.expected}</span>}
          </li>
        ))}
      </ol>
    </div>
  );
}
