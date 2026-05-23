import { FolderTree } from "lucide-react";
import type { ModuleTreeNode } from "../api";

function TreeNode({
  node,
  selectedModuleId,
  onSelect
}: {
  node: ModuleTreeNode;
  selectedModuleId: string;
  onSelect: (moduleId: string) => void;
}) {
  const active = selectedModuleId === node.id;
  return (
    <li>
      <button className={active ? "tree-node active" : "tree-node"} type="button" onClick={() => onSelect(node.id)}>
        <span style={{ paddingLeft: node.depth * 12 }}>{node.path_label}</span>
        <small>{node.reference_count}</small>
      </button>
      {node.children.length ? (
        <ul>
          {node.children.map((child) => (
            <TreeNode node={child} selectedModuleId={selectedModuleId} onSelect={onSelect} key={child.id} />
          ))}
        </ul>
      ) : null}
    </li>
  );
}

export function ModuleTree({
  modules,
  selectedModuleId,
  onSelect
}: {
  modules: ModuleTreeNode[];
  selectedModuleId: string;
  onSelect: (moduleId: string) => void;
}) {
  return (
    <div className="module-tree">
      <div className="pane-heading">
        <div>
          <span className="eyebrow">Modules</span>
          <h3>模块目录</h3>
        </div>
        <FolderTree size={18} aria-hidden="true" />
      </div>
      <button className={selectedModuleId === "" ? "tree-node active" : "tree-node"} type="button" onClick={() => onSelect("")}>
        <span>全部</span>
      </button>
      <ul>
        {modules.map((module) => (
          <TreeNode node={module} selectedModuleId={selectedModuleId} onSelect={onSelect} key={module.id} />
        ))}
      </ul>
    </div>
  );
}
