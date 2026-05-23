import { useState } from "react";
import type { Session } from "./api";
import { LoginView } from "./views/LoginView";
import { Workbench } from "./views/Workbench";

const SESSION_KEY = "qualiforge.session";

export function App() {
  const [session, setSession] = useState<Session | null>(() => {
    const stored = localStorage.getItem(SESSION_KEY);
    return stored ? (JSON.parse(stored) as Session) : null;
  });

  const handleSession = (nextSession: Session) => {
    localStorage.setItem(SESSION_KEY, JSON.stringify(nextSession));
    setSession(nextSession);
  };

  if (!session) {
    return <LoginView onSession={handleSession} />;
  }

  return (
    <Workbench
      session={session}
      onSignOut={() => {
        localStorage.removeItem(SESSION_KEY);
        setSession(null);
      }}
    />
  );
}
