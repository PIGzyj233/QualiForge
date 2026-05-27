import { useEffect, useState } from "react";
import { Mail, Shield } from "lucide-react";
import { listMembers, type MemberRecord } from "@/api/workspace";
import { useCurrentWorkspace } from "@/stores/workspace-store";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";

export function ProjectTeamPanel() {
  const ws = useCurrentWorkspace();
  const [members, setMembers] = useState<MemberRecord[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ws) return;
    listMembers(ws.id).then(setMembers).catch((e) => setError(e instanceof Error ? e.message : "成员加载失败"));
  }, [ws?.id]);

  return (
    <div className="flex flex-col gap-5">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)] mb-1">Team</p>
        <h1 className="font-heading text-2xl font-bold">项目团队</h1>
        <p className="mt-1 text-sm text-[var(--muted-foreground)]">该项目所在 Workspace 的成员（添加成员请前往 Workspace 管理 → 成员）。</p>
      </div>
      {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {members.map((m) => (
          <Card key={m.id}>
            <CardContent className="p-4 flex flex-col gap-1.5">
              <p className="font-semibold">{m.display_name}</p>
              <p className="text-xs text-[var(--muted-foreground)] flex items-center gap-1.5"><Mail size={11} />{m.email}</p>
              <p className="text-xs text-[var(--muted-foreground)] flex items-center gap-1.5"><Shield size={11} />{m.role === "WorkspaceOwner" ? "Workspace Owner" : "Workspace 成员"}</p>
            </CardContent>
          </Card>
        ))}
        {members.length === 0 && <p className="text-sm text-[var(--muted-foreground)]">尚无成员</p>}
      </div>
    </div>
  );
}
