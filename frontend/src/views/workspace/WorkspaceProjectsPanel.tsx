import { FormEvent, useState } from "react";
import { Archive, FolderKanban, PencilLine } from "lucide-react";
import { createProject, updateProject, type ProjectRecord } from "@/api/workspace";
import { useCurrentWorkspace, useWorkspaceStore, refreshProjects } from "@/stores/workspace-store";
import { useSessionStore } from "@/stores/session-store";
import { statusLabel } from "@/lib/labels";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export function WorkspaceProjectsPanel() {
  const session = useSessionStore((s) => s.session);
  const ws = useCurrentWorkspace();
  const projects = useWorkspaceStore((s) => s.projects);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [name, setName] = useState("Checkout");
  const [key, setKey] = useState("CHECKOUT");
  const [description, setDescription] = useState("Checkout regression surface");
  const [projStatus, setProjStatus] = useState<"active" | "archived">("active");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  function reset() { setEditingId(null); setName(""); setKey(""); setDescription(""); setProjStatus("active"); }
  function edit(p: ProjectRecord) { setEditingId(p.id); setName(p.name); setKey(p.key); setDescription(p.description); setProjStatus(p.status); }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!ws || !session) return;
    setBusy(true); setMessage(null);
    try {
      if (editingId) {
        await updateProject(ws.id, editingId, session.user.email, { name, description, status: projStatus });
        setMessage(`已更新项目 ${key}`);
      } else {
        await createProject(ws.id, session.user.email, { name, key, description });
        setMessage(`已创建项目 ${key}`);
      }
      reset();
      await refreshProjects(ws.id);
    } catch (err) { setMessage(err instanceof Error ? err.message : "项目保存失败"); }
    finally { setBusy(false); }
  }

  return (
    <div className="flex flex-col gap-5">
      {message && <Alert><AlertDescription>{message}</AlertDescription></Alert>}
      <Card>
        <CardHeader><CardTitle className="flex items-center gap-2"><FolderKanban size={16} />{editingId ? "编辑项目" : "新建项目"}</CardTitle></CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="flex flex-col gap-1.5">
                <Label>名称</Label>
                <Input value={name} onChange={(e) => setName(e.target.value)} required />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Key</Label>
                <Input value={key} onChange={(e) => setKey(e.target.value.toUpperCase())} disabled={Boolean(editingId)} required />
              </div>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>描述</Label>
              <Input value={description} onChange={(e) => setDescription(e.target.value)} />
            </div>
            {editingId && (
              <div className="flex flex-col gap-1.5">
                <Label>状态</Label>
                <Select value={projStatus} onValueChange={(v) => setProjStatus(v as "active" | "archived")}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="active">Active</SelectItem>
                    <SelectItem value="archived">Archived</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            )}
            <div className="flex gap-2">
              <Button type="submit" disabled={busy || !ws}>{editingId ? "保存" : "创建项目"}</Button>
              {editingId && <Button type="button" variant="outline" onClick={reset}>取消</Button>}
            </div>
          </form>
        </CardContent>
      </Card>
      <div className="flex flex-col gap-2">
        {projects.map((p) => (
          <div key={p.id} className="flex items-center justify-between gap-3 rounded-[var(--radius-md)] border bg-[var(--card)] px-4 py-3">
            <div className="min-w-0">
              <p className="font-semibold text-sm">{p.key} · {p.name}</p>
              <p className="text-xs text-[var(--muted-foreground)]">{p.description || "无描述"}</p>
              <p className="text-xs text-[var(--muted-foreground)]">{statusLabel[p.status]} · 创建于 {new Date(p.created_at).toLocaleDateString()}</p>
            </div>
            <div className="flex items-center gap-1 shrink-0">
              {p.status === "archived" && <Archive size={14} className="text-[var(--muted-foreground)]" />}
              <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => edit(p)} title="编辑项目"><PencilLine size={15} /></Button>
            </div>
          </div>
        ))}
        {projects.length === 0 && <p className="text-sm text-[var(--muted-foreground)]">尚无项目</p>}
      </div>
    </div>
  );
}
