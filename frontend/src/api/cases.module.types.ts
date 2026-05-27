import type { AgentRunExecuteResponse, AgentStagedOutputRecord } from "./agents";
import type { ModuleMappingRuleRecord } from "./cases.mapping.types";

export type ProjectModuleRecord = {
  id: string;
  workspace_id: string;
  project_id: string;
  parent_id: string | null;
  key: string;
  name: string;
  slug: string;
  code: string;
  path: string;
  path_label: string;
  depth: number;
  sort_order: number;
  status: "active" | "archived";
  description: string;
  owner: string;
  keywords: string[];
  reference_count: number;
  mapping_rules: ModuleMappingRuleRecord[];
  created_at: string;
  updated_at: string;
};

export type ModuleTreeNode = ProjectModuleRecord & { children: ModuleTreeNode[] };

export type ModuleTreeDraftGenerateResponse = AgentStagedOutputRecord | AgentRunExecuteResponse;
