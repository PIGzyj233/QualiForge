import { useEffect, useState } from "react";
import { History } from "lucide-react";
import { listAuditLogs, type AuditLogRecord } from "@/api/workspace";
import { useCurrentWorkspace } from "@/stores/workspace-store";
import { useSessionStore } from "@/stores/session-store";
import { Pagination } from "@/components/Pagination";
import { usePagination } from "@/hooks/usePagination";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Card, CardContent } from "@/components/ui/card";

export function WorkspaceAuditPanel() {
  const session = useSessionStore((s) => s.session);
  const ws = useCurrentWorkspace();
  const [logs, setLogs] = useState<AuditLogRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const pagination = usePagination(logs, 12);

  useEffect(() => {
    if (!ws || !session) return;
    listAuditLogs(ws.id, session.user.email)
      .then(setLogs)
      .catch((e) => setError(e instanceof Error ? e.message : "审计日志加载失败"));
  }, [ws?.id, session?.user.email]);

  return (
    <div className="flex flex-col gap-5">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)] mb-1">Audit</p>
        <h1 className="font-heading text-2xl font-bold">审计日志</h1>
        <p className="mt-1 text-sm text-[var(--muted-foreground)]">记录 Workspace 内的成员、项目和资源变更。</p>
      </div>
      {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
      <Card>
        <CardContent className="p-0">
          {pagination.currentItems.map((entry) => (
            <div key={entry.id} className="flex flex-col gap-0.5 px-5 py-3 border-b last:border-0">
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono bg-[var(--muted)] px-1.5 py-0.5 rounded text-[var(--muted-foreground)]">{entry.action}</span>
                <p className="text-sm font-semibold">{entry.summary}</p>
              </div>
              <p className="text-xs text-[var(--muted-foreground)]">{entry.actor_email} · {new Date(entry.created_at).toLocaleString()}</p>
            </div>
          ))}
          {logs.length === 0 && <p className="px-5 py-4 text-sm text-[var(--muted-foreground)]">暂无审计记录</p>}
          <div className="px-5">
            <Pagination currentPage={pagination.currentPage} totalPages={pagination.totalPages} totalItems={pagination.totalItems} onPageChange={pagination.goToPage} itemsPerPage={12} />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
