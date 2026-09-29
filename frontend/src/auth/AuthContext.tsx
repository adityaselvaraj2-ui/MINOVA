import { createContext, useContext, useState, useCallback, type ReactNode } from "react";
import { apiFetch } from "../api/client";

interface User {
  user_id: number;
  username: string;
  full_name: string;
  role_code: string;
  mine_id: number | null;
  can_enter?: boolean;
  can_approve?: boolean;
}

interface AuthState {
  token: string | null;
  user: User | null;
}

interface AuthContextValue extends AuthState {
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function loadStored(): AuthState {
  try {
    const raw = localStorage.getItem("minetrace_auth");
    if (raw) return JSON.parse(raw);
  } catch { /* ignore */ }
  return { token: null, user: null };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(loadStored);

  const login = useCallback(async (username: string, password: string) => {
    const resp = await apiFetch<{
      access_token: string;
      user_id: number;
      username: string;
      full_name: string;
      role_code: string;
      mine_id: number | null;
    }>("/auth/login", { method: "POST", body: { username, password } });

    const me = await apiFetch<{
      can_enter: boolean;
      can_approve: boolean;
    }>("/auth/me", { token: resp.access_token });

    const user: User = {
      user_id: resp.user_id,
      username: resp.username,
      full_name: resp.full_name,
      role_code: resp.role_code,
      mine_id: resp.mine_id,
      can_enter: me.can_enter,
      can_approve: me.can_approve,
    };
    const next = { token: resp.access_token, user };
    localStorage.setItem("minetrace_auth", JSON.stringify(next));
    setState(next);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem("minetrace_auth");
    setState({ token: null, user: null });
  }, []);

  return (
    <AuthContext.Provider value={{ ...state, login, logout, isAuthenticated: !!state.token }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be inside AuthProvider");
  return ctx;
}
