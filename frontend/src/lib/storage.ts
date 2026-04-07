const STORAGE_KEYS = {
  token: "saarthi_token",
  selectedModel: "saarthi_selected_model",
} as const;

function getSafeStorage(): Storage | null {
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage;
}

export const storage = {
  getToken(): string | null {
    return getSafeStorage()?.getItem(STORAGE_KEYS.token) ?? null;
  },
  setToken(token: string): void {
    getSafeStorage()?.setItem(STORAGE_KEYS.token, token);
  },
  clearToken(): void {
    getSafeStorage()?.removeItem(STORAGE_KEYS.token);
  },
  getSelectedModel(): string | null {
    return getSafeStorage()?.getItem(STORAGE_KEYS.selectedModel) ?? null;
  },
  setSelectedModel(modelId: string): void {
    getSafeStorage()?.setItem(STORAGE_KEYS.selectedModel, modelId);
  },
};
