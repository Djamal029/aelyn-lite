import { RadialGauge } from "./RadialGauge";
import styles from "./MetricRow.module.css";

const STATE_COLOR: Record<"normal" | "warning" | "critical", string> = {
  normal: "var(--state-blue)",
  warning: "var(--state-amber)",
  critical: "var(--state-red)",
};

export interface MetricItem {
  label: string;
  value: string;
  /** Threshold state, applied to the value's color (and, for a gauge
   * item, the ring color): never a decorative color, always a real
   * reading past a real threshold. */
  state?: "normal" | "warning" | "critical";
  /** Present only for metrics with a natural 0..max bound (a percentage,
   * or a temperature against a sane ceiling): when set, this item
   * renders as a radial gauge (the HUD-style instrument read) instead of
   * a plain label/value pair. Metrics without a natural bound (e.g. a
   * network rate) stay as plain text. */
  gauge?: { value: number; max: number };
}

export function MetricRow({ items }: { items: MetricItem[] }) {
  return (
    <div className={styles.row}>
      {items.map((item) =>
        item.gauge ? (
          <RadialGauge
            key={item.label}
            label={item.label}
            percent={(item.gauge.value / item.gauge.max) * 100}
            displayValue={item.value}
            color={STATE_COLOR[item.state ?? "normal"]}
          />
        ) : (
          <div className={styles.item} key={item.label}>
            <span className={styles.label}>{item.label}</span>
            <span className={[styles.value, item.state && item.state !== "normal" ? styles[item.state] : ""].join(" ")}>
              {item.value}
            </span>
          </div>
        )
      )}
    </div>
  );
}

export function thresholdState(value: number, warnAt: number, criticalAt: number): "normal" | "warning" | "critical" {
  if (value >= criticalAt) return "critical";
  if (value >= warnAt) return "warning";
  return "normal";
}
