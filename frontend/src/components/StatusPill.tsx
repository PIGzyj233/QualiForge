import { statusLabel } from "../lib/labels";

export function StatusPill({ status }: { status: string }) {
  return <span className={`status-pill ${status}`}>{statusLabel[status] ?? status}</span>;
}
