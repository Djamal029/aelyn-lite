import type { ActivityEntry } from "../../types";
import { formatTimestamp } from "../../lib/time";
import styles from "./LogPanel.module.css";

const SOURCE_LABEL: Record<ActivityEntry["source"], string> = {
  voice: "voix",
  text: "texte",
  vision: "vision",
  system: "system",
  email: "mail",
  career: "carriere",
  media: "media",
};

export function LogPanel({ entries }: { entries: ActivityEntry[] }) {
  return (
    <div className={styles.log}>
      {entries.map((entry) => (
        <div className={styles.line} key={entry.id}>
          <span className={styles.time}>{formatTimestamp(entry.timestamp)}</span>
          <span className={styles.source}>{SOURCE_LABEL[entry.source]}</span>
          <span className={styles.message}>{entry.message}</span>
        </div>
      ))}
    </div>
  );
}
