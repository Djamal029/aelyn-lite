import styles from "./StatusDot.module.css";

export type DotKind =
  | "operational"
  | "degraded"
  | "offline"
  | "connected"
  | "connecting"
  | "disconnected"
  | "info"
  | "warning"
  | "critical"
  | "neutral"
  | "active"
  | "done"
  | "executing"
  | "error";

interface StatusDotProps {
  kind: DotKind;
  pulse?: boolean;
  title?: string;
}

export function StatusDot({ kind, pulse, title }: StatusDotProps) {
  const cls = [styles.dot, styles[kind], pulse ? styles.pulse : ""].join(" ").trim();
  return <span className={cls} title={title} aria-hidden={title ? undefined : true} />;
}
