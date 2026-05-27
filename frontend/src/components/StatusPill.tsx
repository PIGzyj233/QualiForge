import { Badge } from "@/components/ui/badge";

const statusConfig: Record<string, { label: string; variant: "success" | "warning" | "destructive" | "secondary" | "info" | "outline" }> = {
  ok: { label: "正常", variant: "success" },
  reachable: { label: "可达", variant: "success" },
  succeeded: { label: "成功", variant: "success" },
  done: { label: "完成", variant: "success" },
  approved: { label: "已通过", variant: "success" },
  active: { label: "活跃", variant: "success" },
  passed: { label: "通过", variant: "success" },
  degraded: { label: "降级", variant: "warning" },
  checking: { label: "检查中", variant: "warning" },
  pending: { label: "待处理", variant: "warning" },
  in_progress: { label: "进行中", variant: "info" },
  running: { label: "运行中", variant: "info" },
  failed: { label: "失败", variant: "destructive" },
  rejected: { label: "已拒绝", variant: "destructive" },
  blocked: { label: "阻塞", variant: "destructive" },
  archived: { label: "已归档", variant: "secondary" },
  draft: { label: "草稿", variant: "secondary" },
  skipped: { label: "跳过", variant: "secondary" }
};

export function StatusPill({ status }: { status: string }) {
  const cfg = statusConfig[status] ?? { label: status, variant: "outline" as const };
  return <Badge variant={cfg.variant}>{cfg.label}</Badge>;
}
