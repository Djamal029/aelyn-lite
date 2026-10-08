import { useEffect, useMemo, useRef, useState } from "react";
import type { ChatMessage as ChatMessageT } from "../../types";
import { ChatMessage } from "./ChatMessage";
import styles from "./ChatHistory.module.css";

function dayLabel(iso: string): string {
  const date = new Date(iso);
  const now = new Date();
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (date.toDateString() === now.toDateString()) return "Aujourd'hui";
  if (date.toDateString() === yesterday.toDateString()) return "Hier";
  return date.toLocaleDateString("fr-FR", { day: "2-digit", month: "long", year: "numeric" });
}

interface ChatHistoryProps {
  messages: ChatMessageT[];
  /** Whether to auto-scroll to the newest message (on for a live
   * session view; disabled while the user is actively searching). */
  followLatest?: boolean;
  /** Passé jusqu'à ChatResultTable (cf. son docstring) : candidature
   * facile sur plusieurs offres sélectionnées dans un tableau affiché. */
  onPrepareCvs?: (offers: { id: string; title: string }[]) => void;
}

/** Full, searchable conversation history: spans more than the current
 * session (see mocks/chat.ts), grouped by day like a real persisted
 * transcript rather than a single ephemeral scroll of bubbles. */
export function ChatHistory({ messages, followLatest = true, onPrepareCvs }: ChatHistoryProps) {
  const [query, setQuery] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  const filtered = useMemo(() => {
    if (!query.trim()) return messages;
    const q = query.toLowerCase();
    return messages.filter(
      (m) =>
        m.text.toLowerCase().includes(q) ||
        m.understood?.toLowerCase().includes(q) ||
        m.command?.toLowerCase().includes(q)
    );
  }, [messages, query]);

  const groups = useMemo(() => {
    const map = new Map<string, ChatMessageT[]>();
    for (const m of filtered) {
      const label = dayLabel(m.timestamp);
      if (!map.has(label)) map.set(label, []);
      map.get(label)!.push(m);
    }
    return Array.from(map.entries());
  }, [filtered]);

  useEffect(() => {
    if (!followLatest) return;
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages.length, followLatest]);

  return (
    <div className={styles.wrap}>
      <div className={styles.toolbar}>
        <input
          className={styles.search}
          type="text"
          placeholder="Rechercher dans l'historique (message, commande, intention comprise)…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <span className={styles.count}>
          {filtered.length} / {messages.length}
        </span>
      </div>
      <div className={styles.scroll} ref={scrollRef}>
        {groups.length === 0 ? (
          query.trim() ? <div className={styles.empty}>Aucun résultat pour « {query} ».</div> : null
        ) : (
          groups.map(([label, msgs]) => (
            <div key={label}>
              <div className={styles.daySeparator}>{label}</div>
              {msgs.map((m) => (
                <ChatMessage key={m.id} message={m} onPrepareCvs={onPrepareCvs} />
              ))}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
