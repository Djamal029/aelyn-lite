export const THEME_OPTIONS = [
  { id: "porcelaine", label: "Porcelaine", note: "Ivoire et lavande douce" },
  { id: "lavande", label: "Lavande", note: "Lilas et encre prune" },
  { id: "sauge", label: "Sauge", note: "Vert tendre et crème" },
  { id: "sable", label: "Sable", note: "Lin et terre cuite" },
  { id: "nuit", label: "Nuit", note: "Un Jarvis discret" },
] as const;

export type AelynTheme = (typeof THEME_OPTIONS)[number]["id"];

const STORAGE_KEY = "aelyn.theme";
const DEFAULT_THEME: AelynTheme = "porcelaine";

function isTheme(value: string | null): value is AelynTheme {
  return THEME_OPTIONS.some((theme) => theme.id === value);
}

export function getAelynTheme(): AelynTheme {
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    return isTheme(saved) ? saved : DEFAULT_THEME;
  } catch {
    return DEFAULT_THEME;
  }
}

function applyAelynTheme(theme: AelynTheme): void {
  document.documentElement.dataset.theme = theme;
}

export function setAelynTheme(theme: AelynTheme): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // The selected theme still applies for this visit if storage is blocked.
  }
  applyAelynTheme(theme);
}

export function initializeAelynTheme(): void {
  applyAelynTheme(getAelynTheme());
}