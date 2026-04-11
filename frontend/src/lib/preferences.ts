export type ComparisonMethod = "difflib" | "llm" | "both";

export interface WorkspacePreferences {
  topK: number;
  comparisonMethod: ComparisonMethod;
  compactChat: boolean;
  showTemporalDetails: boolean;
  showSourceSnippets: boolean;
}

const STORAGE_KEY = "saarthi_workspace_preferences";

const DEFAULT_PREFERENCES: WorkspacePreferences = {
  topK: 5,
  comparisonMethod: "both",
  compactChat: false,
  showTemporalDetails: true,
  showSourceSnippets: true,
};

function getSafeStorage(): Storage | null {
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage;
}

function clampTopK(value: number): number {
  if (!Number.isFinite(value)) {
    return DEFAULT_PREFERENCES.topK;
  }
  return Math.max(2, Math.min(10, Math.round(value)));
}

function parsePreferences(raw: string | null): WorkspacePreferences {
  if (!raw) {
    return { ...DEFAULT_PREFERENCES };
  }

  try {
    const parsed = JSON.parse(raw) as Partial<WorkspacePreferences>;
    return {
      topK: clampTopK(parsed.topK ?? DEFAULT_PREFERENCES.topK),
      comparisonMethod:
        parsed.comparisonMethod === "difflib" || parsed.comparisonMethod === "llm" || parsed.comparisonMethod === "both"
          ? parsed.comparisonMethod
          : DEFAULT_PREFERENCES.comparisonMethod,
      compactChat: Boolean(parsed.compactChat),
      showTemporalDetails:
        typeof parsed.showTemporalDetails === "boolean"
          ? parsed.showTemporalDetails
          : DEFAULT_PREFERENCES.showTemporalDetails,
      showSourceSnippets:
        typeof parsed.showSourceSnippets === "boolean"
          ? parsed.showSourceSnippets
          : DEFAULT_PREFERENCES.showSourceSnippets,
    };
  } catch {
    return { ...DEFAULT_PREFERENCES };
  }
}

export function getWorkspacePreferences(): WorkspacePreferences {
  return parsePreferences(getSafeStorage()?.getItem(STORAGE_KEY) ?? null);
}

export function saveWorkspacePreferences(preferences: WorkspacePreferences): void {
  const normalized: WorkspacePreferences = {
    ...preferences,
    topK: clampTopK(preferences.topK),
  };
  getSafeStorage()?.setItem(STORAGE_KEY, JSON.stringify(normalized));
}

export function updateWorkspacePreferences(next: Partial<WorkspacePreferences>): WorkspacePreferences {
  const merged = {
    ...getWorkspacePreferences(),
    ...next,
  };
  saveWorkspacePreferences(merged);
  return merged;
}

export function resetWorkspacePreferences(): WorkspacePreferences {
  saveWorkspacePreferences(DEFAULT_PREFERENCES);
  return { ...DEFAULT_PREFERENCES };
}

export function getDefaultWorkspacePreferences(): WorkspacePreferences {
  return { ...DEFAULT_PREFERENCES };
}