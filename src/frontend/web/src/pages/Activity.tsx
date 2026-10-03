import { useMemo, useState } from "react";
import { LogPanel } from "../components/ui/LogPanel";
import { LITE_MODE } from "../lib/liteMode";
import { useActivityEntries } from "../lib/useActivityEntries";
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
  const { entries, live } = useActivityEntries();
  const [source, setSource] = useState<(typeof SOURCE_OPTIONS)[number]["value"]>("all");
  const [query, setQuery] = useState("");
  const sourceOptions = LITE_MODE
    ? SOURCE_OPTIONS.filter((option) => option.value !== "vision")
    : SOURCE_OPTIONS;

  const filtered = useMemo(
    () => entries
      .filter((entry) => source === "all" || entry.source === source)
      .filter((entry) => !query.trim() || entry.message.toLowerCase().includes(query.toLowerCase()))
      .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()),
    [entries, source, query]
  );

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.title}>Activité</div>
        <div className={styles.subtitle}>
          {live ? "Historique réel, actualisé automatiquement." : "Historique local des actions effectuées sur cet appareil."}
        </div>
      </div>

      <div className={styles.filters}>
        <select className={styles.select} value={source} onChange={(event) => setSource(event.target.value as typeof source)}>
          {sourceOptions.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
        <input
          className={styles.search}
          type="text"
          placeholder="Filtrer le journal…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
      </div>

      <div className={styles.logWrap}>
        {filtered.length > 0 ? (
          <LogPanel entries={filtered} />
        ) : (
          <div className={styles.empty}>
            {entries.length === 0
              ? "Aucune activité pour le moment. Le journal se remplira avec vos premières actions."
              : "Aucune entrée ne correspond à ce filtre."}
          </div>
        )}
      </div>
    </div>
  );
}