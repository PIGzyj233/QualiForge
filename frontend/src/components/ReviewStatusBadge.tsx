import { statusLabel } from "../lib/labels";

export function ReviewStatusBadge({ status }: { status: string | null }) {
  const value = status ?? "no_review";
  return <span className={`status-pill ${value}`}>{status ? statusLabel[status] ?? status : "无评审"}</span>;
}
