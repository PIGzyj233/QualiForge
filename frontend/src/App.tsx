import { useState } from "react";
import { BrowserRouter } from "react-router-dom";
import type { Session } from "./api";
import { AppRouter } from "./routes/AppRouter";
import { LoginView } from "./views/LoginView";

const SESSION_KEY = "qualiforge.session";

export function App() {
  const [session, setSession] = useState<Session | null>(() => {
    const stored = localStorage.getItem(SESSION_KEY);
    return stored ? (JSON.parse(stored) as Session) : null;
  });

  const handleSession = (next: Session) => {
    localStorage.setItem(SESSION_KEY, JSON.stringify(next));
    setSession(next);
  };

  const handleSignOut = () => {
    localStorage.removeItem(SESSION_KEY);
    setSession(null);
  };

  if (!session) {
    return <LoginView onSession={handleSession} />;
  }

  return (
    <BrowserRouter>
      <AppRouter session={session} onSignOut={handleSignOut} />
    </BrowserRouter>
  );
}
