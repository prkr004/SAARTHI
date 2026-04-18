import { createContext, useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";

import { api } from "../lib/api/endpoints";
import type { UserProfile } from "../lib/api/types";
import type { AuthScope } from "../lib/storage";
import { storage } from "../lib/storage";

type ScopedAuthState<T> = {
  employee: T;
  admin: T;
};

interface AuthContextValue {
  user: UserProfile | null;
  token: string | null;
  loading: boolean;
  isAuthenticated: boolean;
  login: (employeeId: string, password: string) => Promise<UserProfile>;
  register: (employeeId: string, fullName: string, password: string, email: string) => Promise<string>;
  logout: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | undefined>(undefined);

interface AuthProviderProps {
  children: React.ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const location = useLocation();
  const scope: AuthScope = storage.resolveScope(location.pathname);

  const [tokens, setTokens] = useState<ScopedAuthState<string | null>>(() => ({
    employee: storage.getToken("employee"),
    admin: storage.getToken("admin"),
  }));
  const [users, setUsers] = useState<ScopedAuthState<UserProfile | null>>({
    employee: null,
    admin: null,
  });
  const [loading, setLoading] = useState(true);

  const token = scope === "admin" ? tokens.admin : tokens.employee;
  const user = scope === "admin" ? users.admin : users.employee;

  useEffect(() => {
    let active = true;

    async function bootstrapAuth() {
      setLoading(true);

      if (!token) {
        if (active) {
          setUsers((current) => ({
            ...current,
            [scope]: null,
          }));
          setLoading(false);
        }
        return;
      }

      try {
        const profile = await api.me();
        if (active) {
          setUsers((current) => ({
            ...current,
            [scope]: profile,
          }));
        }
      } catch {
        storage.clearToken(scope);
        if (active) {
          setTokens((current) => ({
            ...current,
            [scope]: null,
          }));
          setUsers((current) => ({
            ...current,
            [scope]: null,
          }));
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    bootstrapAuth();

    return () => {
      active = false;
    };
  }, [scope, token]);

  async function login(employeeId: string, password: string): Promise<UserProfile> {
    const response = await api.login({ employee_id: employeeId, password });
    storage.setToken(response.access_token, scope);
    setTokens((current) => ({
      ...current,
      [scope]: response.access_token,
    }));
    setUsers((current) => ({
      ...current,
      [scope]: response.user,
    }));
    return response.user;
  }

  async function register(employeeId: string, fullName: string, password: string, email: string): Promise<string> {
    const response = await api.register({ employee_id: employeeId, full_name: fullName, password, email });
    return response.message;
  }

  async function logout(): Promise<void> {
    try {
      await api.logout();
    } finally {
      storage.clearToken(scope);
      setTokens((current) => ({
        ...current,
        [scope]: null,
      }));
      setUsers((current) => ({
        ...current,
        [scope]: null,
      }));
    }
  }

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      token,
      loading,
      isAuthenticated: Boolean(user && token),
      login,
      register,
      logout,
    }),
    [loading, token, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
