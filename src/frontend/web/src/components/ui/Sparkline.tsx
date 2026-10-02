import type { TimeSeriesPoint } from "../../types";

interface SparklineProps {
  data: TimeSeriesPoint[];
  width?: number;
  height?: number;
  color?: string;
  unit?: string;
  max?: number;
}

/** A real trend line for a real metric: flat stroke, faint flat-color
 * fill under the line (not a gradient), no smoothing tricks that would
 * misrepresent the data. */
export function Sparkline({ data, width = 240, height = 48, color = "var(--state-blue)", unit = "", max }: SparklineProps) {
  if (data.length === 0) return null;
  const values = data.map((d) => d.v);
  const maxV = max ?? Math.max(...values, 1);
  const minV = Math.min(...values, 0);
  const range = maxV - minV || 1;
  const stepX = width / (data.length - 1 || 1);

  const points = data.map((d, i) => {
    const x = i * stepX;
    const y = height - ((d.v - minV) / range) * height;
    return [x, y] as const;
  });

  const linePath = points.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const areaPath = `${linePath} L${width},${height} L0,${height} Z`;

  const last = data[data.length - 1];
  const first = data[0];

  return (
    <div>
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`Tendance de ${first.t} à ${last.t}`}>
        <path d={areaPath} fill={color} opacity={0.08} stroke="none" />
        <path d={linePath} fill="none" stroke={color} strokeWidth={1.5} />
      </svg>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          fontSize: "var(--fs-xs)",
          color: "var(--text-muted)",
          fontFamily: "var(--font-mono)",
          marginTop: 2,
        }}
      >
        <span>{first.t}</span>
        <span style={{ color: "var(--text-secondary)" }}>
          {last.v}
          {unit}
        </span>
        <span>{last.t}</span>
      </div>
    </div>
  );
}
