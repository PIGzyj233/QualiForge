import { statusLabel } from "@/lib/labels";
import { cn } from "@/lib/utils";

export function StatusTile({ label, status, detail }: { label: string; status: string; detail: string }) {
  return (
    <div className="flex flex-col justify-between gap-3 rounded-[var(--radius-md)] border bg-[var(--card)] p-4 shadow-sm min-h-[96px]">
      <div>
        <span className="text-[11px] font-bold uppercase tracking-wider text-[var(--muted-foreground)]">{label}</span>
        <strong className="block mt-1 text-xl font-bold text-[var(--foreground)]">{statusLabel[status] ?? status}</strong>
      </div>
      <small className="text-xs text-[var(--muted-foreground)] leading-snug">{detail}</small>
    </div>
  );
}
