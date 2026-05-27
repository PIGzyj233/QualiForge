export type MappingRuleType =
  | "directory"
  | "file"
  | "api"
  | "service"
  | "command"
  | "library_api"
  | "symbol"
  | "package"
  | "build_target"
  | "config_key"
  | "database_migration"
  | "protocol"
  | "transport"
  | "format"
  | "codec"
  | "media_pipeline"
  | "asset_fixture"
  | "keyword";

export type MappingRelationship = "primary" | "related" | "dependency" | "evidence";

export type MappingStatus = "active" | "stale" | "archived";

export type MappingStatusFilter = MappingStatus | "all";

export type MappingSource = "manual" | "ai_repository" | "ai_history" | "diff_confirmation";

export type ModuleMappingRuleRecord = {
  id: string;
  workspace_id: string;
  project_id: string;
  module_id: string;
  repository_id: string | null;
  rule_type: MappingRuleType;
  pattern: string;
  relationship: MappingRelationship;
  status: MappingStatus;
  source: MappingSource;
  description: string;
  ai_confidence: number;
  confidence: number;
  evidence_refs: Record<string, unknown>[];
  accepted_from_output_id: string | null;
  verified_by: string;
  verified_at: string | null;
  stale_reason: string;
  conditions: Record<string, unknown>;
  case_sensitive: boolean | null;
  created_at: string;
  updated_at: string;
};

export type MappingRulePreflightIssue = {
  severity: "blocker" | "warning";
  code: string;
  reason: string;
  rule_id?: string | null;
  module_id?: string | null;
  path?: string | null;
};

export type MappingRulePreflightRecord = {
  passed: boolean;
  blocker_count: number;
  warning_count: number;
  issues: MappingRulePreflightIssue[];
  matched_sample_count: number;
  sample_paths: string[];
};
