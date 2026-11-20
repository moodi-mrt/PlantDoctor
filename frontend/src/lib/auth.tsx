import { createContext, useContext, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import type { User } from "./types";

interface AuthCtx { user: User | null; loading: boolean; refresh: () => Promise<void>; logout: () => Promise<void> }
const Ctx = createContext<AuthCtx>({ user: null, loading: true, refresh: async () => {}, logout: async () => {} });

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["session"],
    queryFn: () => api<{ authenticated: boolean; user: User | null }>("/auth/session"),
    staleTime: 60_000,
    retry: 1,
  });
  const refresh = async () => { await qc.invalidateQueries({ queryKey: ["session"] }); };
  const logout = async () => {
    try { await api("/auth/logout", { method: "POST" }); } finally { qc.clear(); await refresh(); }
  };
  return <Ctx.Provider value={{ user: q.data?.user ?? null, loading: q.isLoading, refresh, logout }}>{children}</Ctx.Provider>;
}

export const useAuth = () => useContext(Ctx);
