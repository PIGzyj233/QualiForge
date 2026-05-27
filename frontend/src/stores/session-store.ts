import { create } from "zustand";
import type { Session } from "@/api/workspace";

const SESSION_KEY = "qualiforge.session";

type SessionStore = {
  session: Session | null;
  setSession: (s: Session) => void;
  signOut: () => void;
};

export const useSessionStore = create<SessionStore>((set) => ({
  session: (() => {
    const stored = localStorage.getItem(SESSION_KEY);
    return stored ? (JSON.parse(stored) as Session) : null;
  })(),
  setSession: (s) => {
    localStorage.setItem(SESSION_KEY, JSON.stringify(s));
    set({ session: s });
  },
  signOut: () => {
    localStorage.removeItem(SESSION_KEY);
    set({ session: null });
  }
}));
