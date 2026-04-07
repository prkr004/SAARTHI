import { createContext, useEffect, useMemo, useState } from "react";

import { api } from "../lib/api/endpoints";
import type { UserProfile } from "../lib/api/types";
import { storage } from "../lib/storage";

interface AuthContextValue {
  user: UserProfile | null;
  token: string | null;
  loading: boolean;
  isAuthenticated: boolean;
  login: (employeeId: string, password: string) => Promise<void>;
  register: (employeeId: string, fullName: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | undefined>(undefined);

interface AuthProviderProps {
  children: React.ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [token, setToken] = useState<string | null>(() => storage.getToken());
  const [user, setUser] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;

    async function bootstrapAuth() {
      if (!token) {
        if (active) {
          setLoading(false);
        }
        return;
      }

      try {
        const profile = await api.me();
        if (active) {
          setUser(profile);
        }
      } catch {
        storage.clearToken();
        if (active) {
          setToken(null);
          setUser(null);
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
  }, [token]);

  async function login(employeeId: string, password: string): Promise<void> {
    const response = await api.login({ employee_id: employeeId, password });
    storage.setToken(response.access_token);
    setToken(response.access_token);
    setUser(response.user);
  }

  async function register(employeeId: string, fullName: string, password: string): Promise<void> {
    await api.register({ employee_id: employeeId, full_name: fullName, password });
  }

  async function logout(): Promise<void> {
    try {
      await api.logout();
    } finally {
      storage.clearToken();
      setToken(null);
      setUser(null);
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
