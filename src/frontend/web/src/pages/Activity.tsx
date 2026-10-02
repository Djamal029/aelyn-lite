import { useMemo, useState } from "react";
import { LogPanel } from "../components/ui/LogPanel";
import { activityLog } from "../mocks";
import type { ActivityEntry } from "../types";
import styles from "./Activity.module.css";

const SOURCE_OPTIONS: { value: ActivityEntry["source"] | "all"; label: string }[] = [
  { value: "all", label: "Toutes sources" },
  { value: "voice", label: "Voix" },
  { value: "text", label: "Texte" },
  { value: "vision", label: "Vision" },
  { value: "email", label: "Mail" },
  { value: "career", label: "Carrière" },
  { value: "media", label: "Média" },
  { value: "system", label: "Système" },
];

export function Activity() {
  const [source, setSource] = useState<(typeof SOURCE_OPTIONS)[number]["value"]>("all");
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    return activityLog
      .filter((e) => source === "all" || e.source === source)
      .filter((e) => !query.trim() || e.message.toLowerCase().includes(query.toLowerCase()))
      .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
  }, [source, query]);

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.title}>Activity</div>
        <div className={styles.subtitle}>Journal réel de ce qu'AELYN a fait : une ligne par action, pas une vue décorative.</div>
      </div>

      <div className={styles.filters}>
        <select className={styles.select} value={source} onChange={(e) => setSource(e.target.value as typeof source)}>
          {SOURCE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <input
          className={styles.search}
          type="text"
          placeholder="Filtrer le journal…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>

      <div className={styles.logWrap}>
        <LogPanel entries={filtered} />
      </div>
    </div>
  );
}
