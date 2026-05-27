import { Badge } from "@/components/ui/badge";

const caseStatusConfig: Record<string, { label: string; variant: "success" | "warning" | "secondary" | "info" | "outline" }> = {
  draft: { label: "草稿", variant: "secondary" },
  in_review: { label: "评审中", variant: "warning" },
  approved: { label: "已通过", variant: "success" },
  archived: { label: "已归档", variant: "secondary" },
  rejected: { label: "已拒绝", variant: "outline" }
};

export function CaseStatusBadge({ status }: { status: string }) {
  const cfg = caseStatusConfig[status] ?? { label: status, variant: "outline" as const };
  return <Badge variant={cfg.variant}>{cfg.label}</Badge>;
}
