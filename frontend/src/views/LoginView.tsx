import { FormEvent, useState } from "react";
import { LogIn, Sparkles } from "lucide-react";
import {
  login,
  Session
} from "../api";

export function LoginView({ onSession }: { onSession: (session: Session) => void }) {
  const [email, setEmail] = useState("owner@qualiforge.local");
  const [displayName, setDisplayName] = useState("Workspace Owner");
  const [workspaceName, setWorkspaceName] = useState("QualiForge Lab");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);

    try {
      const nextSession = await login({ email, display_name: displayName, workspace_name: workspaceName });
      onSession(nextSession);
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login-shell">
      <section className="login-panel" aria-label="QualiForge 登录">
        <div className="brand-mark">
          <Sparkles size={22} aria-hidden="true" />
          <span>QualiForge</span>
        </div>
        <div>
          <h1>私有化测试资产工作台</h1>
          <p>团队测试资产与发布决策的私有工作台。</p>
        </div>
        <form onSubmit={handleSubmit} className="login-form">
          <label>
            邮箱
            <input value={email} type="email" onChange={(event) => setEmail(event.target.value)} required />
          </label>
          <label>
            显示名称
            <input value={displayName} onChange={(event) => setDisplayName(event.target.value)} required />
          </label>
          <label>
            Workspace
            <input value={workspaceName} onChange={(event) => setWorkspaceName(event.target.value)} required />
          </label>
          {error ? <p className="form-error">{error}</p> : null}
          <button className="primary-button" type="submit" disabled={submitting}>
            <LogIn size={18} aria-hidden="true" />
            <span>{submitting ? "进入中" : "进入工作台"}</span>
          </button>
        </form>
      </section>
    </main>
  );
}

