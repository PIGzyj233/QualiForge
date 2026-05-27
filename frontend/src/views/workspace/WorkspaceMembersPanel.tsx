import { FormEvent, useEffect, useState } from "react";
import { Trash2, UserPlus } from "lucide-react";
import { addMember, listMembers, removeMember, type MemberRecord } from "@/api/workspace";
import { useWorkspaceStore, useCurrentWorkspace } from "@/stores/workspace-store";
import { useSessionStore } from "@/stores/session-store";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export function WorkspaceMembersPanel() {
  const session = useSessionStore((s) => s.session);
  const ws = useCurrentWorkspace();
  const [members, setMembers] = useState<MemberRecord[]>([]);
  const [email, setEmail] = useState("tester@qualiforge.local");
  const [displayName, setDisplayName] = useState("Tester");
  const [role, setRole] = useState<"WorkspaceOwner" | "WorkspaceMember">("WorkspaceMember");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function refresh() {
    if (!ws) return;
    setBusy(true);
    try { setMembers(await listMembers(ws.id)); }
    catch (e) { setMessage(e instanceof Error ? e.message : "成员加载失败"); }
    finally { setBusy(false); }
  }

  useEffect(() => { void refresh(); }, [ws?.id]);

  async function handleAdd(e: FormEvent) {
    e.preventDefault();
    if (!ws || !session) return;
    setBusy(true); setMessage(null);
    try {
      const m = await addMember(ws.id, session.user.email, { email, display_name: displayName, role });
      setMessage(`已添加成员 ${m.email}`);
      await refresh();
    } catch (err) { setMessage(err instanceof Error ? err.message : "添加成员失败"); }
    finally { setBusy(false); }
  }

  async function handleRemove(id: string) {
    if (!ws || !session) return;
    setBusy(true); setMessage(null);
    try { await removeMember(ws.id, id, session.user.email); setMessage("已移除成员"); await refresh(); }
    catch (err) { setMessage(err instanceof Error ? err.message : "移除成员失败"); }
    finally { setBusy(false); }
  }

  return (
    <div className="flex flex-col gap-5">
      {message && <Alert><AlertDescription>{message}</AlertDescription></Alert>}
      <Card>
        <CardHeader><CardTitle className="flex items-center gap-2"><UserPlus size={16} />添加成员</CardTitle></CardHeader>
        <CardContent>
          <form onSubmit={handleAdd} className="flex flex-col gap-4">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="flex flex-col gap-1.5">
                <Label>邮箱</Label>
                <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>显示名称</Label>
                <Input value={displayName} onChange={(e) => setDisplayName(e.target.value)} required />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>角色</Label>
                <Select value={role} onValueChange={(v) => setRole(v as typeof role)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="WorkspaceMember">成员</SelectItem>
                    <SelectItem value="WorkspaceOwner">Owner</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <Button type="submit" disabled={busy || !ws} className="self-start">添加成员</Button>
          </form>
        </CardContent>
      </Card>
      <div className="flex flex-col gap-2">
        {members.map((m) => (
          <div key={m.id} className="flex items-center justify-between gap-3 rounded-[var(--radius-md)] border bg-[var(--card)] px-4 py-3">
            <div className="min-w-0">
              <p className="font-semibold text-sm">{m.display_name}</p>
              <p className="text-xs text-[var(--muted-foreground)]">{m.email}</p>
              <p className="text-xs text-[var(--muted-foreground)]">{m.role === "WorkspaceOwner" ? "Owner" : "成员"} · 加入于 {new Date(m.created_at).toLocaleDateString()}</p>
            </div>
            <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0" onClick={() => void handleRemove(m.id)} disabled={busy || m.role === "WorkspaceOwner"} title={m.role === "WorkspaceOwner" ? "Owner 不可移除" : "移除成员"}>
              <Trash2 size={15} />
            </Button>
          </div>
        ))}
        {members.length === 0 && <p className="text-sm text-[var(--muted-foreground)]">尚无成员</p>}
      </div>
    </div>
  );
}
