export type AuthScope = "employee" | "admin";

const STORAGE_KEYS = {
  employeeToken: "saarthi_employee_token",
  adminToken: "saarthi_admin_token",
  legacyToken: "saarthi_token",
  selectedModel: "saarthi_selected_model",
  employeeDisplayName: "saarthi_employee_display_name",
  adminDisplayName: "saarthi_admin_display_name",
} as const;

function resolveScope(pathname: string): AuthScope {
  return pathname.startsWith("/admin") ? "admin" : "employee";
}

function keyForScope(scope: AuthScope): string {
  return scope === "admin" ? STORAGE_KEYS.adminToken : STORAGE_KEYS.employeeToken;
}

function displayNameKeyForScope(scope: AuthScope): string {
  return scope === "admin" ? STORAGE_KEYS.adminDisplayName : STORAGE_KEYS.employeeDisplayName;
}

function getSafeStorage(): Storage | null {
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage;
}

function migrateLegacyToken(store: Storage): void {
  const legacyToken = store.getItem(STORAGE_KEYS.legacyToken);
  if (!legacyToken) {
    return;
  }

  const employeeToken = store.getItem(STORAGE_KEYS.employeeToken);
  if (!employeeToken) {
    store.setItem(STORAGE_KEYS.employeeToken, legacyToken);
  }
  store.removeItem(STORAGE_KEYS.legacyToken);
}

export const storage = {
  resolveScope,
  getToken(scope: AuthScope = "employee"): string | null {
    const store = getSafeStorage();
    if (!store) {
      return null;
    }
    migrateLegacyToken(store);
    return store.getItem(keyForScope(scope));
  },
  getTokenForPath(pathname: string): string | null {
    return this.getToken(resolveScope(pathname));
  },
  getTokenForCurrentPath(): string | null {
    const pathname = typeof window === "undefined" ? "/" : window.location.pathname;
    return this.getTokenForPath(pathname);
  },
  setToken(token: string, scope: AuthScope = "employee"): void {
    const store = getSafeStorage();
    if (!store) {
      return;
    }
    migrateLegacyToken(store);
    store.setItem(keyForScope(scope), token);
  },
  clearToken(scope: AuthScope = "employee"): void {
    getSafeStorage()?.removeItem(keyForScope(scope));
  },
  clearAllTokens(): void {
    const store = getSafeStorage();
    if (!store) {
      return;
    }
    store.removeItem(STORAGE_KEYS.employeeToken);
    store.removeItem(STORAGE_KEYS.adminToken);
    store.removeItem(STORAGE_KEYS.legacyToken);
  },
  getSelectedModel(): string | null {
    return getSafeStorage()?.getItem(STORAGE_KEYS.selectedModel) ?? null;
  },
  setSelectedModel(modelId: string): void {
    getSafeStorage()?.setItem(STORAGE_KEYS.selectedModel, modelId);
  },
  getDisplayName(scope: AuthScope = "employee"): string | null {
    return getSafeStorage()?.getItem(displayNameKeyForScope(scope)) ?? null;
  },
  setDisplayName(displayName: string, scope: AuthScope = "employee"): void {
    const store = getSafeStorage();
    if (!store) {
      return;
    }
    store.setItem(displayNameKeyForScope(scope), displayName);
  },
  clearDisplayName(scope: AuthScope = "employee"): void {
    getSafeStorage()?.removeItem(displayNameKeyForScope(scope));
  },
};
