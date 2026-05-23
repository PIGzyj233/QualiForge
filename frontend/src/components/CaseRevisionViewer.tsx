import type { CaseRevisionRecord } from "../api";

export function CaseRevisionViewer({ revision }: { revision: CaseRevisionRecord | null }) {
  if (!revision) {
    return <p className="empty-state">暂无正式版本</p>;
  }

  const steps = Array.isArray(revision.content_snapshot.steps)
    ? revision.content_snapshot.steps.map((step) => String(step))
    : [];

  return (
    <div className="case-content">
      <div className="case-meta-grid">
        <span>Revision {revision.revision_number}</span>
        <span>{revision.module_path_label || "未归属"}</span>
        <span>{String(revision.content_snapshot.priority ?? "P2")}</span>
        <span>{String(revision.content_snapshot.risk ?? "medium")}</span>
      </div>
      <h3>{String(revision.content_snapshot.title ?? "Untitled case")}</h3>
      <ol className="step-list">
        {steps.map((step) => (
          <li key={step}>{step}</li>
        ))}
      </ol>
      <p>{String(revision.content_snapshot.expected_result ?? "")}</p>
    </div>
  );
}
