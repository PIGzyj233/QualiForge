import type { TestCasePayload } from "./cases.common.types";

export type DiffStructureChange = {
  type: string;
  name: string;
  state: string;
  evidence?: string;
};

export type DiffFileChange = {
  path: string;
  old_path: string | null;
  directory: string;
  language: string;
  change_type: "added" | "modified" | "deleted" | "renamed";
  additions: number;
  deletions: number;
  module_id: string | null;
  module_key: string | null;
  module_name: string | null;
  is_test_file: boolean;
  is_migration: boolean;
  structure_changes: DiffStructureChange[];
  risk_level: "low" | "medium" | "high";
  confidence: number;
  evidence: string[];
  diff_hunks?: Array<{
    header: string;
    old_start: number;
    old_lines: number;
    new_start: number;
    new_lines: number;
    context?: string;
    lines: string[];
  }>;
  patch_truncated?: boolean;
};

export type DiffModuleImpact = {
  module_id: string | null;
  module_key: string;
  module_name: string;
  risk_level: "low" | "medium" | "high";
  changed_file_count: number;
  recommended_tests: string[];
  evidence: string[];
  confidence: number;
};

export type DiffAnalysisRecord = {
  id: string;
  workspace_id: string;
  project_id: string;
  repository_id: string;
  job_id: string;
  base_ref: string;
  target_ref: string;
  status: "running" | "succeeded" | "failed";
  risk_level: "low" | "medium" | "high";
  summary: string;
  recommended_scope: string[];
  file_changes: DiffFileChange[];
  module_impacts: DiffModuleImpact[];
  key_logs: string[];
  error_summary: string;
  created_by: string;
  created_at: string;
  completed_at: string | null;
};

export type AISuggestionStatus = "suggested" | "accepted" | "ignored" | "modified";

export type AISuggestionType = "regression" | "case_candidate";

export type AISuggestionRecord = {
  id: string;
  workspace_id: string;
  project_id: string;
  diff_analysis_id: string;
  suggestion_type: AISuggestionType;
  status: AISuggestionStatus;
  title: string;
  rationale: string;
  confidence: number;
  module_id: string | null;
  module_key: string;
  source_diff: Record<string, unknown>;
  mapping_evidence: string[];
  code_paths: string[];
  interfaces: string[];
  config_keys: string[];
  related_case_ids: string[];
  selected_case_ids: string[];
  candidate_payload: TestCasePayload & { custom_fields: Record<string, string> };
  candidate_case_id: string | null;
  plan_item_ids: string[];
  feedback_history: Array<{ actor_email: string; comment: string; created_at: string }>;
  created_by: string;
  created_at: string;
  updated_at: string;
};
