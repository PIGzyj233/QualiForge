import type { CaseRevisionRecord, CaseStep } from "../api/cases";

function normalizeSteps(value: unknown): CaseStep[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => {
    if (item && typeof item === "object" && !Array.isArray(item)) {
      const o = item as Record<string, unknown>;
      return {
        action: String(o.action ?? ""),
        expected: String(o.expected ?? "")
      };
    }
    return { action: String(item ?? ""), expected: "" };
  });
}

export function CaseRevisionViewer({ revision }: { revision: CaseRevisionRecord | null }) {
  if (!revision) {
    return <p className="empty-state">暂无正式版本</p>;
  }

  const steps = normalizeSteps(revision.content_snapshot.steps);

  return (
    <div className="case-content">
      <div className="case-meta-grid">
        <span>Revision {revision.revision_number}</span>
        <span>{revision.module_path_label || "未归属"}</span>
        <span>{String(revision.content_snapshot.priority ?? "P2")}</span>
        <span>{String(revision.content_snapshot.risk ?? "medium")}</span>
      </div>
      <h3>{String(revision.content_snapshot.title ?? "Untitled case")}</h3>
      <ol className="step-list paired">
        {steps.map((step, i) => (
          <li key={i}>
            <span className="step-action">{step.action || "(空步骤)"}</span>
            {step.expected ? <span className="step-expected">→ {step.expected}</span> : null}
          </li>
        ))}
      </ol>
    </div>
  );
}
