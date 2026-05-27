export type CaseStep = {
  action: string;
  expected: string;
};

export type TestCasePayload = {
  module_id?: string | null;
  title: string;
  steps: CaseStep[];
  priority: string;
  risk: string;
  tags: string[];
  custom_fields: Record<string, unknown>;
  source_type?: "manual" | "import" | "ai_suggestion" | "active_edit";
  source_ref?: Record<string, unknown>;
};
