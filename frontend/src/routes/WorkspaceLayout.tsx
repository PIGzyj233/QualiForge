import { Outlet } from "react-router-dom";
import { useEffect } from "react";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Sidebar } from "@/components/layout/Sidebar";
import { CommandPalette } from "@/components/layout/CommandPalette";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { AlertCircle } from "lucide-react";
import { useUIStore } from "@/stores/ui-store";
import { useWorkspaceStore, useWorkspaceSync } from "@/stores/workspace-store";
import { useSessionStore } from "@/stores/session-store";

function ThemeEffect() {
  const theme = useUIStore((s) => s.theme);
  useEffect(() => {
    const root = document.documentElement;
    if (theme === "dark") {
      root.classList.add("dark");
    } else if (theme === "light") {
      root.classList.remove("dark");
    } else {
      const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
      root.classList.toggle("dark", prefersDark);
    }
  }, [theme]);
  return null;
}

function WorkspaceSyncEffect() {
  const session = useSessionStore((s) => s.session);
  useWorkspaceSync(session?.user.email ?? "");
  return null;
}

export function WorkspaceLayout() {
  const error = useWorkspaceStore((s) => s.error);

  return (
    <TooltipProvider delayDuration={300}>
      <ThemeEffect />
      <WorkspaceSyncEffect />
      <div className="flex h-screen overflow-hidden bg-[var(--background)]">
        <Sidebar />
        <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
          <main className="flex-1 overflow-y-auto">
            <div className="max-w-screen-2xl mx-auto px-6 py-6 flex flex-col gap-5">
              {error && (
                <Alert variant="destructive">
                  <AlertCircle size={16} className="shrink-0" />
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}
              <Outlet />
            </div>
          </main>
        </div>
        <CommandPalette />
      </div>
    </TooltipProvider>
  );
}
