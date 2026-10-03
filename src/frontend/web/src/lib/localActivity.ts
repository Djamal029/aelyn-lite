import type { InterpretedCommand } from "./commandInterpreter";
import { LITE_MODE } from "./liteMode";
import type { ActivityEntry } from "../types";

const STORAGE_KEY = "aelyn.activity.local";
const LITE_RESTRICTED_RE = /camera|caméra|security|sécurité|vision|visage|intrusion|mouvement|anti.?spoof|yolo|arcface/i;

function readStored(): ActivityEntry[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    const entries: unknown = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(entries)) return [];
    return entries.filter(
      (entry): entry is ActivityEntry =>
        typeof entry?.id === "string" &&
        typeof entry?.timestamp === "string" &&
        typeof entry?.message === "string" &&
        typeof entry?.source === "string"
    );
  } catch {
    return [];
  }
}

export function getLocalActivity(): ActivityEntry[] {
  const entries = readStored();
  return LITE_MODE ? entries.filter((entry) => !LITE_RESTRICTED_RE.test(entry.message)) : entries;
}

export function recordLocalActivity(
  prompt: string,
  result: InterpretedCommand,
  via: "text" | "voice" = "text"
): void {
  if (typeof window === "undefined") return;
  const message = `${prompt.trim()} : ${result.resultText.trim()}`.replace(/\s+/g, " ").slice(0, 500);
  if (LITE_MODE && LITE_RESTRICTED_RE.test(message)) return;

  const source: ActivityEntry["source"] = LITE_MODE && result.command === "camera"
    ? via
    : result.command === "chercher_offres"
      ? "career"
      : result.command === "verifier" || result.command === "triage"
        ? "email"
        : result.command === "media"
          ? "media"
          : via;
  const entry: ActivityEntry = {
    id: `local-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    timestamp: new Date().toISOString(),
    message,
    source,
  };

  try {
    const entries = [...readStored(), entry].slice(-300);
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
    window.dispatchEvent(new Event("aelyn-activity-changed"));
  } catch {
    // Activity history is best-effort if browser storage is disabled.
  }
}