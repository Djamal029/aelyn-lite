import styles from "./Badge.module.css";

export type BadgeKind = "info" | "warning" | "critical" | "operational" | "active";

interface BadgeProps {
  kind: BadgeKind;
  children: React.ReactNode;
}

export function Badge({ kind, children }: BadgeProps) {
  return <span className={[styles.badge, styles[kind]].join(" ")}>{children}</span>;
}
