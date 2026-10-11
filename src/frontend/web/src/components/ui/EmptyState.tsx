import type { ReactNode } from "react";
import styles from "./EmptyState.module.css";

export type EmptyStateIcon = "chat" | "journal" | "applications" | "search";

const ICONS: Record<EmptyStateIcon, ReactNode> = {
  chat: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
    </svg>
  ),
  journal: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
    </svg>
  ),
  applications: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <line x1="3" y1="9" x2="21" y2="9" />
      <line x1="7" y1="14" x2="13" y2="14" />
      <line x1="7" y1="17" x2="11" y2="17" />
    </svg>
  ),
  search: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="7" />
      <path d="m21 21-4.3-4.3" />
    </svg>
  ),
};

interface EmptyStateProps {
  icon: EmptyStateIcon;
  title: string;
  description?: ReactNode;
  compact?: boolean;
}

/** A centered icon + message for a container with nothing to show yet.
 * Pulled out once several pages (journal, candidatures, assistant) had
 * independently reinvented "one line of muted text" inside a container
 * that flexes to fill the page, which read as broken/unloaded rather
 * than deliberately empty. The icon is what turns that into a designed
 * state instead of an accident. */
export function EmptyState({ icon, title, description, compact }: EmptyStateProps) {
  return (
    <div className={[styles.wrap, compact ? styles.compact : ""].join(" ")}>
      <div className={styles.icon}>{ICONS[icon]}</div>
      <p className={styles.title}>{title}</p>
      {description ? <p className={styles.description}>{description}</p> : null}
    </div>
  );
}
