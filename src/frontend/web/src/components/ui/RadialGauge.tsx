import styles from "./RadialGauge.module.css";

interface RadialGaugeProps {
  label: string;
  /** 0-100: how full the ring is. Callers compute this themselves
   * (value/max * 100) so the gauge has no opinion about what "full"
   * means for a given metric (a percentage, a temperature against a
   * sane ceiling, etc). */
  percent: number;
  /** The exact text shown at the ring's center, e.g. "23%" or "48°C":
   * kept as a caller-supplied string rather than reconstructed here,
   * since formatting (decimals, unit placement) already varies by
   * metric across the app. */
  displayValue: string;
  color?: string;
  size?: number;
}

/** A clean radial progress ring, the primary "gauge cluster" read for a
 * single bounded system metric (CPU/RAM/temperature/disk) instead of a
 * bare number, the single most recognizable HUD signifier. Deliberately
 * a simple instrument: no tick marks or printed units around the dial,
 * that level of instrument detail is reserved for the voice orb
 * (VoiceOrb.module.css), the one element meant to read as a full HUD
 * face. The ring's accent is always a caller-supplied color drawn from
 * the existing state palette (var(--state-blue/amber/red)), never a new
 * color, with a small glow (not a thick neon outline) marking it as the
 * HUD's "live instrument" surface. */
export function RadialGauge({ label, percent, displayValue, color = "var(--state-blue)", size = 72 }: RadialGaugeProps) {
  const stroke = 4;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.max(0, Math.min(100, percent));
  const offset = circumference * (1 - clamped / 100);
  const center = size / 2;

  return (
    <div className={styles.wrap}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`${label} : ${displayValue}`}>
        <circle cx={center} cy={center} r={radius} fill="none" stroke="var(--border-subtle)" strokeWidth={stroke} />
        <circle
          className={styles.progress}
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          transform={`rotate(-90 ${center} ${center})`}
          style={{ filter: `drop-shadow(0 0 3px ${color})` }}
        />
        <text x={center} y={center} textAnchor="middle" dominantBaseline="central" className={styles.value}>
          {displayValue}
        </text>
      </svg>
      <span className={styles.label}>{label}</span>
    </div>
  );
}
