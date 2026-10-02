import type { ApiEmailListItem, ApiOfferResult } from "../../lib/api";
import type { ChatResultType } from "../../types";
import { formatTimestamp } from "../../lib/time";
import styles from "./ChatResultTable.module.css";

interface ChatResultTableProps {
  resultType: ChatResultType;
  results: ApiOfferResult[] | ApiEmailListItem[];
}

function formatMailDate(value: string | null): string {
  if (!value) return "N/A";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : formatTimestamp(date.toISOString());
}

/** Renders a real chat-reply list (offer search / mail check) as an
 * actual table instead of the plain-sentence/bullet-list summary the
 * backend's `text` field alone would produce, same borders/spacing
 * language as EventsTable (components/security/EventsTable.tsx) so it
 * reads as one system rather than a one-off style. Used by ChatMessage
 * whenever `resultType`/`results` are present on an AELYN turn. */
export function ChatResultTable({ resultType, results }: ChatResultTableProps) {
  if (results.length === 0) return null;

  if (resultType === "offers") {
    const offers = results as ApiOfferResult[];
    return (
      <div className={styles.wrap}>
        <div className={styles.scroll}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Poste</th>
                <th>Entreprise</th>
                <th>Lieu</th>
                <th>Contrat</th>
                <th>Score</th>
              </tr>
            </thead>
            <tbody>
              {offers.map((o, i) => (
                <tr key={o.id ?? `${o.intitule ?? "offre"}-${i}`}>
                  <td>{o.intitule ?? "N/A"}</td>
                  <td>{o.entreprise ?? "N/A"}</td>
                  <td>{o.lieu ?? "N/A"}</td>
                  <td>{o.contrat ?? "N/A"}</td>
                  <td className={styles.score}>{typeof o.score === "number" ? `${Math.round(o.score * 100)}%` : "N/A"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  const mails = results as ApiEmailListItem[];
  return (
    <div className={styles.wrap}>
      <div className={styles.scroll}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Expéditeur</th>
              <th>Objet</th>
              <th>Date</th>
            </tr>
          </thead>
          <tbody>
            {mails.map((m) => (
              <tr key={m.uid}>
                <td>{m.sender || m.sender_email}</td>
                <td>{m.subject}</td>
                <td className={styles.date}>{formatMailDate(m.date)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
