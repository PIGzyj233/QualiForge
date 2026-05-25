import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { getCurrentMember, listProjects, listWorkspaces, MemberRecord, ProjectRecord, Session, WorkspaceRecord } from "../api";

export type WorkspaceContextValue = {
  session: Session;
  actorEmail: string;
  workspaces: WorkspaceRecord[];
  currentWorkspace: WorkspaceRecord | null;
  projects: ProjectRecord[];
  currentProject: ProjectRecord | null;
  currentMember: MemberRecord | null;
  isOwner: boolean;
  busy: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  selectWorkspace: (id: string) => void;
  selectProject: (id: string) => void;
  registerWorkspace: (workspace: WorkspaceRecord) => void;
  refreshProjects: () => Promise<void>;
};

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

function pickId<T extends { id: string }>(items: T[], preferred: string, current: string) {
  if (preferred && items.some((item) => item.id === preferred)) return preferred;
  if (current && items.some((item) => item.id === current)) return current;
  return items[0]?.id ?? "";
}

export function WorkspaceProvider({ session, children }: { session: Session; children: ReactNode }) {
  const location = useLocation();
  const routeMatch = location.pathname.match(/^\/w\/([^/]+)(?:\/p\/([^/]+))?/);
  const routeWorkspaceId = routeMatch?.[1] ?? "";
  const routeProjectId = routeMatch?.[2] ?? "";
  const actorEmail = session.user.email;
  const [workspaces, setWorkspaces] = useState<WorkspaceRecord[]>([]);
  const [currentWorkspaceId, setCurrentWorkspaceId] = useState<string>("");
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [currentProjectId, setCurrentProjectId] = useState<string>("");
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentMember, setCurrentMember] = useState<MemberRecord | null>(null);

  const refresh = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const list = await listWorkspaces(actorEmail);
      setWorkspaces(list);
      const nextWid = pickId(list, routeWorkspaceId, currentWorkspaceId);
      setCurrentWorkspaceId(nextWid);
      if (nextWid) {
        const ps = await listProjects(nextWid);
        setProjects(ps);
        const nextPid = pickId(ps, routeProjectId, currentProjectId);
        setCurrentProjectId(nextPid);
      } else {
        setProjects([]);
        setCurrentProjectId("");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Workspace 加载失败");
    } finally {
      setBusy(false);
    }
  }, [actorEmail, routeWorkspaceId, routeProjectId, currentWorkspaceId, currentProjectId]);

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [actorEmail, routeWorkspaceId, routeProjectId]);

  useEffect(() => {
    if (!currentWorkspaceId) {
      setCurrentMember(null);
      return;
    }
    let cancelled = false;
    getCurrentMember(currentWorkspaceId, actorEmail)
      .then((m) => {
        if (!cancelled) setCurrentMember(m);
      })
      .catch(() => {
        if (!cancelled) setCurrentMember(null);
      });
    return () => {
      cancelled = true;
    };
  }, [currentWorkspaceId, actorEmail]);

  const refreshProjects = useCallback(async () => {
    if (!currentWorkspaceId) return;
    const ps = await listProjects(currentWorkspaceId);
    setProjects(ps);
    if (!ps.some((p) => p.id === currentProjectId)) {
      setCurrentProjectId(ps[0]?.id ?? "");
    }
  }, [currentWorkspaceId, currentProjectId]);

  const selectWorkspace = useCallback(
    (id: string) => {
      if (id === currentWorkspaceId) return;
      setCurrentWorkspaceId(id);
      setBusy(true);
      void listProjects(id)
        .then((ps) => {
          setProjects(ps);
          setCurrentProjectId(pickId(ps, routeProjectId, ""));
        })
        .catch((err) => setError(err instanceof Error ? err.message : "项目加载失败"))
        .finally(() => setBusy(false));
    },
    [currentWorkspaceId, routeProjectId]
  );

  const selectProject = useCallback((id: string) => {
    setCurrentProjectId(id);
  }, []);

  const registerWorkspace = useCallback((workspace: WorkspaceRecord) => {
    setWorkspaces((prev) => (prev.some((w) => w.id === workspace.id) ? prev : [...prev, workspace]));
    setCurrentWorkspaceId(workspace.id);
    setProjects([]);
    setCurrentProjectId("");
  }, []);

  const value: WorkspaceContextValue = useMemo(
    () => ({
      session,
      actorEmail,
      workspaces,
      currentWorkspace: workspaces.find((w) => w.id === currentWorkspaceId) ?? null,
      projects,
      currentProject: projects.find((p) => p.id === currentProjectId) ?? null,
      currentMember,
      isOwner: currentMember?.role === "WorkspaceOwner",
      busy,
      error,
      refresh,
      selectWorkspace,
      selectProject,
      registerWorkspace,
      refreshProjects
    }),
    [
      session,
      actorEmail,
      workspaces,
      currentWorkspaceId,
      projects,
      currentProjectId,
      currentMember,
      busy,
      error,
      refresh,
      selectWorkspace,
      selectProject,
      registerWorkspace,
      refreshProjects
    ]
  );

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspaceContext(): WorkspaceContextValue {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error("useWorkspaceContext must be used inside WorkspaceProvider");
  return ctx;
}
