import { statusLabel } from "../lib/labels";

export function CaseStatusBadge({ status }: { status: string }) {
  return <span className={`status-pill ${status}`}>{statusLabel[status] ?? status}</span>;
}
