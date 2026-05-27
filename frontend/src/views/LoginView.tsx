import { FormEvent, useState } from "react";
import { LogIn } from "lucide-react";
import { login, type Session } from "@/api/workspace";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function LoginView({ onSession }: { onSession: (session: Session) => void }) {
  const [email, setEmail] = useState("owner@qualiforge.local");
  const [displayName, setDisplayName] = useState("Workspace Owner");
  const [workspaceName, setWorkspaceName] = useState("QualiForge Lab");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      onSession(await login({ email, display_name: displayName, workspace_name: workspaceName }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="min-h-screen grid place-items-center p-8 bg-[var(--background)]"
      style={{ background: "radial-gradient(ellipse 80% 50% at 50% -20%, rgb(13 148 136 / 0.1), transparent), var(--background)" }}>
      <section className="w-full max-w-sm flex flex-col gap-6 rounded-[var(--radius-lg)] border bg-[var(--card)] p-8 shadow-lg" aria-label="QualiForge 登录">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-[var(--radius-sm)] bg-[var(--primary)] text-[var(--primary-foreground)] text-sm font-bold">QF</div>
          <div>
            <p className="font-heading font-bold text-base">QualiForge</p>
            <p className="text-xs text-[var(--muted-foreground)]">测试资产工作台</p>
          </div>
        </div>
        <div>
          <h1 className="font-heading text-2xl font-bold tracking-tight">私有化测试资产工作台</h1>
          <p className="mt-1.5 text-sm text-[var(--muted-foreground)]">团队测试资产与发布决策的私有工作台。</p>
        </div>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="email">邮箱</Label>
            <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="name">显示名称</Label>
            <Input id="name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} required />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="ws">Workspace</Label>
            <Input id="ws" value={workspaceName} onChange={(e) => setWorkspaceName(e.target.value)} required />
          </div>
          {error && <p className="text-sm font-semibold text-[var(--destructive)]">{error}</p>}
          <Button type="submit" disabled={submitting} className="mt-1">
            <LogIn size={16} />
            {submitting ? "进入中..." : "进入工作台"}
          </Button>
        </form>
      </section>
    </main>
  );
}
