import { BrowserRouter } from "react-router-dom";
import { useSessionStore } from "./stores/session-store";
import { AppRouter } from "./routes/AppRouter";
import { LoginView } from "./views/LoginView";

export function App() {
  const session = useSessionStore((s) => s.session);
  const setSession = useSessionStore((s) => s.setSession);

  if (!session) {
    return <LoginView onSession={setSession} />;
  }

  return (
    <BrowserRouter>
      <AppRouter />
    </BrowserRouter>
  );
}
