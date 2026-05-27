import type { CaseStep } from "./cases.common.types";

export type ImportBatchRecord = {
  id: string;
  workspace_id: string;
  project_id: string;
  job_id: string | null;
  file_name: string;
  file_type: "csv" | "xlsx";
  original_file_path: string;
  status: "uploaded" | "preview_ready" | "review_submitted" | "imported" | "failed";
  created_by: string;
  row_count: number;
  raw_rows: Record<string, unknown>[];
  ai_conversion_result: Record<string, unknown>[];
  manual_changes: Record<string, unknown>[];
  error_summary: string;
  created_at: string;
  updated_at: string;
  submitted_at: string | null;
  imported_at: string | null;
};

export type ImportDraftRecord = {
  id: string;
  workspace_id: string;
  project_id: string;
  batch_id: string;
  module_id: string | null;
  test_case_id: string | null;
  case_draft_id: string | null;
  review_cycle_id: string | null;
  title: string;
  steps: CaseStep[];
  priority: string;
  risk: string;
  tags: string[];
  custom_fields: Record<string, string>;
  source_row_index: number;
  raw_row: Record<string, unknown>;
  ai_confidence: number;
  status: "draft" | "review_submitted" | "imported";
  created_at: string;
  updated_at: string;
};

export type ImportResultRecord = {
  batch: ImportBatchRecord;
  imported_count: number;
};
