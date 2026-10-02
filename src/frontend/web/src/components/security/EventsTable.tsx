import type { SecurityEvent } from "../../types";
import { formatTimestamp } from "../../lib/time";
import { Badge } from "../ui/Badge";
import { SECURITY_TYPE_LABEL, SEVERITY_BADGE } from "../../lib/securityLabels";
import styles from "./EventsTable.module.css";

interface EventsTableProps {
  events: SecurityEvent[];
  limit?: number;
  /** The table's `<th>` uses `position: sticky`, which sticks relative
   * to its nearest scrolling ancestor. When this component provides
   * that ancestor itself (the default, safe to drop into a plain
   * panel, e.g. Overview's summary card), it wraps the table in its own
   * bounded, capped-height scroll box. When the caller already owns a
   * properly sized scroll container (e.g. Security.module.css's
   * `.tableWrap`, which is flex-sized to the remaining page height),
   * pass `selfContained={false}` so the table isn't capped at a fixed
   * height inside a taller box: that combination produced a second,
   * smaller, redundant scrollbar. */
  selfContained?: boolean;
}

export function EventsTable({ events, limit, selfContained = true }: EventsTableProps) {
  const rows = limit ? events.slice(0, limit) : events;

  const table = (
    <table className={styles.table}>
      <thead>
        <tr>
          <th>Heure</th>
          <th>Type</th>
          <th>Caméra</th>
          <th>Confiance</th>
          <th>Sévérité</th>
          <th>Détail</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((e) => (
          <tr key={e.id}>
            <td className={styles.time}>{formatTimestamp(e.timestamp)}</td>
            <td>{SECURITY_TYPE_LABEL[e.type]}</td>
            <td>{e.camera}</td>
            <td className={styles.confidence}>{e.confidencePercent !== null ? `${e.confidencePercent}%` : "N/A"}</td>
            <td>
              <Badge kind={SEVERITY_BADGE[e.severity]}>{e.severity}</Badge>
            </td>
            <td className={styles.detail}>{e.detail}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );

  return selfContained ? <div className={styles.scroll}>{table}</div> : table;
}
