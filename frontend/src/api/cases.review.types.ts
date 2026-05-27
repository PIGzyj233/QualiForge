import type { CaseStep } from "./cases.common.types";

export type ReviewSettingsRecord = {
  id: string;
  workspace_id: string;
  allow_self_review: boolean;
  require_review_on_case_update: boolean;
  allow_direct_revision_for_active_case: boolean;
  direct_revision_roles: string[];
  updated_by: string;
  created_at: string;
  updated_at: string;
};

export type CaseReviewAction = "submitted" | "approved" | "rejected" | "changes_requested" | "changes_addressed" | "commented";

export type CaseDraftRecord = {
  id: string;
  test_case_id: string;
  workspace_id: string;
  project_id: string;
  base_revision_id: string | null;
  module_id: string | null;
  title: string;
  steps: CaseStep[];
  priority: string;
  risk: string;
  tags: string[];
  custom_fields: Record<string, unknown>;
  draft_status: "editing" | "in_review" | "consumed" | "cancelled";
  source_type: "manual" | "import" | "ai_suggestion" | "active_edit" | string;
  source_ref: Record<string, unknown>;
  created_by: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
};

export type ReviewCycleRecord = {
  id: string;
  workspace_id: string;
  project_id: string;
  test_case_id: string;
  draft_id: string;
  status: "pending_review" | "changes_requested" | "approved" | "rejected" | "cancelled";
  submitted_by: string;
  closed_by: string;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
};

export type CaseReviewRecord = {
  id: string;
  workspace_id: string;
  project_id: string;
  test_case_id: string;
  cycle_id: string | null;
  draft_id: string | null;
  revision_id: string | null;
  actor_email: string;
  action: CaseReviewAction;
  comment: string;
  diff_summary: Record<string, unknown> | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  created_at: string;
};

export type CaseRevisionRecord = {
  id: string;
  workspace_id: string;
  project_id: string;
  test_case_id: string;
  revision_number: number;
  module_id: string | null;
  module_path_label: string;
  content_snapshot: Record<string, unknown>;
  change_summary: string;
  created_by: string;
  created_at: string;
};

export type TestCaseRecord = {
  id: string;
  workspace_id: string;
  project_id: string;
  lifecycle_status: "draft" | "active" | "archived";
  current_revision_id: string | null;
  current_revision_number: number;
  current_module_id: string | null;
  source_type: "manual" | "import" | "ai_suggestion" | "active_edit" | string;
  source_ref: Record<string, unknown>;
  created_by: string;
  created_at: string;
  updated_at: string;
  title: string;
  module_id: string | null;
  module_path_label: string;
  review_status: "pending_review" | "changes_requested" | "approved" | "rejected" | "cancelled" | null;
  active_draft: CaseDraftRecord | null;
  current_revision: CaseRevisionRecord | null;
  open_cycle: ReviewCycleRecord | null;
  revisions?: CaseRevisionRecord[];
  review_cycles?: ReviewCycleRecord[];
  review_events?: CaseReviewRecord[];
};
