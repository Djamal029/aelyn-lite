import { useEffect, useState } from "react";
import { getActivity, type ApiActivityEntry } from "./api";
import { isBackendLive } from "./backendStatus";
import { getLocalActivity } from "./localActivity";
import { LITE_MODE } from "./liteMode";
import type { ActivityEntry, ActivitySource } from "../types";

const LITE_SECURITY_RE = /camera|caméra|security|sécurité|vision|visage|intrusion|mouvement|anti.?spoof|yolo|arcface/i;

function fromApiEntry(entry: ApiActivityEntry): ActivityEntry {
  const knownSources: ActivitySource[] = ["voice", "text", "vision", "system", "email", "career", "media"];
  return {
    id: entry.id,
    timestamp: entry.timestamp,
    message: entry.message,
    source: knownSources.includes(entry.source as ActivitySource) ? entry.source as ActivitySource : "system",
  };
}

function safeForBuild(entries: ActivityEntry[]): ActivityEntry[] {
  return LITE_MODE ? entries.filter((entry) => !LITE_SECURITY_RE.test(entry.message) && entry.source !== "vision") : entries;
}

export function useActivityEntries(): { entries: ActivityEntry[]; live: boolean } {
  const [entries, setEntries] = useState<ActivityEntry[]>([]);
  const [live, setLive] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let refreshing = false;

    const refresh = async () => {
      if (refreshing) return;
      refreshing = true;
      try {
        if (await isBackendLive()) {
          const apiEntries = (await getActivity()).map(fromApiEntry);
          if (cancelled) return;
          setEntries(safeForBuild([...apiEntries, ...getLocalActivity()]));
          setLive(true);
        } else {
          if (cancelled) return;
          setEntries(safeForBuild(getLocalActivity()));
          setLive(false);
        }
      } catch {
        if (!cancelled) {
          setEntries(safeForBuild(getLocalActivity()));
          setLive(false);
        }
      } finally {
        refreshing = false;
      }
    };

    void refresh();
    const timer = window.setInterval(() => void refresh(), 15_000);
    const onLocalActivity = () => void refresh();
    window.addEventListener("aelyn-activity-changed", onLocalActivity);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
      window.removeEventListener("aelyn-activity-changed", onLocalActivity);
    };
  }, []);

  return { entries, live };
}