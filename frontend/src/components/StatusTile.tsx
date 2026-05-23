import { statusLabel } from "../lib/labels";

export function StatusTile({ label, status, detail }: { label: string; status: string; detail: string }) {
  return (
    <div className="status-tile">
      <div>
        <span>{label}</span>
        <strong>{statusLabel[status] ?? status}</strong>
      </div>
      <small>{detail}</small>
    </div>
  );
}
