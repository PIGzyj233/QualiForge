import { useEffect, useState } from "react";
import { History } from "lucide-react";
import { AuditLogRecord, listAuditLogs } from "../../api/workspace";
import { Pagination } from "../../components/Pagination";
import { usePagination } from "../../hooks/usePagination";
import { useWorkspaceContext } from "../../hooks/useWorkspaceContext";

export function WorkspaceAuditPanel() {
  const { actorEmail, currentWorkspace } = useWorkspaceContext();
  const [logs, setLogs] = useState<AuditLogRecord[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pagination = usePagination(logs, 12);

  useEffect(() => {
    if (!currentWorkspace) return;
    setBusy(true);
    setError(null);
    listAuditLogs(currentWorkspace.id, actorEmail)
      .then(setLogs)
      .catch((err) => setError(err instanceof Error ? err.message : "审计日志加载失败"))
      .finally(() => setBusy(false));
  }, [actorEmail, currentWorkspace?.id]);

  return (
    <section className="panel">
      <header className="panel-head">
        <div>
          <span className="eyebrow">Audit</span>
          <h2>审计日志</h2>
          <p className="panel-sub">记录 Workspace 内的成员、项目和资源变更。</p>
        </div>
        <History size={20} aria-hidden="true" />
      </header>
      {error ? <div className="inline-notice">{error}</div> : null}
      <div className="audit-list">
        {pagination.currentItems.map((entry) => (
          <article className="audit-row" key={entry.id}>
            <span>{entry.action}</span>
            <strong>{entry.summary}</strong>
            <small>
              {entry.actor_email} · {new Date(entry.created_at).toLocaleString()}
            </small>
          </article>
        ))}
        {!busy && logs.length === 0 ? <p className="empty-state">暂无审计记录</p> : null}
      </div>
      <Pagination
        currentPage={pagination.currentPage}
        totalPages={pagination.totalPages}
        totalItems={pagination.totalItems}
        onPageChange={pagination.goToPage}
        itemsPerPage={12}
      />
    </section>
  );
}
