import { Badge } from "@/components/ui/badge";

const reviewStatusConfig: Record<string, { label: string; variant: "success" | "warning" | "destructive" | "secondary" | "info" | "outline" }> = {
  pending: { label: "待评审", variant: "warning" },
  approved: { label: "已通过", variant: "success" },
  rejected: { label: "已拒绝", variant: "destructive" },
  changes_requested: { label: "需修改", variant: "info" }
};

export function ReviewStatusBadge({ status }: { status: string }) {
  const cfg = reviewStatusConfig[status] ?? { label: status, variant: "outline" as const };
  return <Badge variant={cfg.variant}>{cfg.label}</Badge>;
}
