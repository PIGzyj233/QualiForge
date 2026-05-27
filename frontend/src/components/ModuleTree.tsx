import { FolderTree } from "lucide-react";
import type { ModuleTreeNode } from "@/api/cases";
import { cn } from "@/lib/utils";

function TreeNode({ node, selectedModuleId, onSelect }: { node: ModuleTreeNode; selectedModuleId: string; onSelect: (id: string) => void }) {
  const active = selectedModuleId === node.id;
  return (
    <li>
      <button
        type="button"
        onClick={() => onSelect(node.id)}
        className={cn("w-full flex items-center justify-between px-2 py-1.5 rounded-[var(--radius-sm)] text-sm transition-colors hover:bg-[var(--muted)]/60", active && "bg-[var(--accent)] text-[var(--accent-foreground)] font-semibold")}
        style={{ paddingLeft: `${8 + node.depth * 12}px` }}
      >
        <span className="truncate">{node.path_label}</span>
        <small className="text-xs text-[var(--muted-foreground)] shrink-0 ml-1">{node.reference_count}</small>
      </button>
      {node.children.length > 0 && (
        <ul>{node.children.map((c) => <TreeNode key={c.id} node={c} selectedModuleId={selectedModuleId} onSelect={onSelect} />)}</ul>
      )}
    </li>
  );
}

export function ModuleTree({ modules, selectedModuleId, onSelect }: { modules: ModuleTreeNode[]; selectedModuleId: string; onSelect: (id: string) => void }) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between px-2 mb-1">
        <span className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">模块目录</span>
        <FolderTree size={14} className="text-[var(--muted-foreground)]" />
      </div>
      <button
        type="button"
        onClick={() => onSelect("")}
        className={cn("w-full text-left px-2 py-1.5 rounded-[var(--radius-sm)] text-sm transition-colors hover:bg-[var(--muted)]/60", selectedModuleId === "" && "bg-[var(--accent)] text-[var(--accent-foreground)] font-semibold")}
      >
        全部
      </button>
      <ul>{modules.map((m) => <TreeNode key={m.id} node={m} selectedModuleId={selectedModuleId} onSelect={onSelect} />)}</ul>
    </div>
  );
}
