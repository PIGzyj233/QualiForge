import { create } from "zustand";
import { useLocation } from "react-router-dom";
import { useEffect } from "react";
import {
  getCurrentMember,
  listProjects,
  listWorkspaces,
  type MemberRecord,
  type ProjectRecord,
  type WorkspaceRecord
} from "@/api/workspace";

type WorkspaceStore = {
  workspaces: WorkspaceRecord[];
  currentWorkspaceId: string;
  projects: ProjectRecord[];
  currentProjectId: string;
  currentMember: MemberRecord | null;
  busy: boolean;
  error: string | null;
  setWorkspaces: (ws: WorkspaceRecord[]) => void;
  setCurrentWorkspaceId: (id: string) => void;
  setProjects: (ps: ProjectRecord[]) => void;
  setCurrentProjectId: (id: string) => void;
  setCurrentMember: (m: MemberRecord | null) => void;
  setBusy: (b: boolean) => void;
  setError: (e: string | null) => void;
  registerWorkspace: (ws: WorkspaceRecord) => void;
};

export const useWorkspaceStore = create<WorkspaceStore>((set, get) => ({
  workspaces: [],
  currentWorkspaceId: "",
  projects: [],
  currentProjectId: "",
  currentMember: null,
  busy: true,
  error: null,
  setWorkspaces: (workspaces) => set({ workspaces }),
  setCurrentWorkspaceId: (currentWorkspaceId) => set({ currentWorkspaceId }),
  setProjects: (projects) => set({ projects }),
  setCurrentProjectId: (currentProjectId) => set({ currentProjectId }),
  setCurrentMember: (currentMember) => set({ currentMember }),
  setBusy: (busy) => set({ busy }),
  setError: (error) => set({ error }),
  registerWorkspace: (ws) => {
    const { workspaces } = get();
    if (!workspaces.some((w) => w.id === ws.id)) {
      set({ workspaces: [...workspaces, ws] });
    }
    set({ currentWorkspaceId: ws.id, projects: [], currentProjectId: "" });
  }
}));

function pickId<T extends { id: string }>(items: T[], preferred: string, current: string) {
  if (preferred && items.some((i) => i.id === preferred)) return preferred;
  if (current && items.some((i) => i.id === current)) return current;
  return items[0]?.id ?? "";
}

export function useWorkspaceSync(actorEmail: string) {
  const location = useLocation();
  const store = useWorkspaceStore();
  const routeMatch = location.pathname.match(/^\/w\/([^/]+)(?:\/p\/([^/]+))?/);
  const routeWid = routeMatch?.[1] ?? "";
  const routePid = routeMatch?.[2] ?? "";

  useEffect(() => {
    let cancelled = false;
    store.setBusy(true);
    store.setError(null);
    listWorkspaces(actorEmail)
      .then(async (list) => {
        if (cancelled) return;
        store.setWorkspaces(list);
        const wid = pickId(list, routeWid, store.currentWorkspaceId);
        store.setCurrentWorkspaceId(wid);
        if (wid) {
          const ps = await listProjects(wid);
          if (cancelled) return;
          store.setProjects(ps);
          store.setCurrentProjectId(pickId(ps, routePid, store.currentProjectId));
        }
      })
      .catch((err) => {
        if (!cancelled) store.setError(err instanceof Error ? err.message : "加载失败");
      })
      .finally(() => {
        if (!cancelled) store.setBusy(false);
      });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [actorEmail, routeWid, routePid]);

  useEffect(() => {
    const { currentWorkspaceId } = store;
    if (!currentWorkspaceId) { store.setCurrentMember(null); return; }
    let cancelled = false;
    getCurrentMember(currentWorkspaceId, actorEmail)
      .then((m) => { if (!cancelled) store.setCurrentMember(m); })
      .catch(() => { if (!cancelled) store.setCurrentMember(null); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [store.currentWorkspaceId, actorEmail]);
}

export function useCurrentWorkspace() {
  const { workspaces, currentWorkspaceId } = useWorkspaceStore();
  return workspaces.find((w) => w.id === currentWorkspaceId) ?? null;
}

export function useCurrentProject() {
  const { projects, currentProjectId } = useWorkspaceStore();
  return projects.find((p) => p.id === currentProjectId) ?? null;
}

export function useIsOwner() {
  const { currentMember } = useWorkspaceStore();
  return currentMember?.role === "WorkspaceOwner";
}

export async function switchWorkspace(id: string, actorEmail: string) {
  const store = useWorkspaceStore.getState();
  if (id === store.currentWorkspaceId) return;
  store.setCurrentWorkspaceId(id);
  store.setBusy(true);
  try {
    const ps = await listProjects(id);
    store.setProjects(ps);
    store.setCurrentProjectId(ps[0]?.id ?? "");
  } catch (err) {
    store.setError(err instanceof Error ? err.message : "项目加载失败");
  } finally {
    store.setBusy(false);
  }
}

export async function refreshProjects(wid: string) {
  const store = useWorkspaceStore.getState();
  const ps = await listProjects(wid);
  store.setProjects(ps);
  if (!ps.some((p) => p.id === store.currentProjectId)) {
    store.setCurrentProjectId(ps[0]?.id ?? "");
  }
}
