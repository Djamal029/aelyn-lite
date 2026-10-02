interface BarHistogramProps {
  data: { label: string; value: number }[];
  width?: number;
  height?: number;
  color?: string;
}

/** Hourly bars for detection frequency: every bar corresponds to a real
 * count for a real hour, labeled on the axis (every 3rd tick, to avoid
 * crowding 24 labels into a dense console panel). */
export function BarHistogram({ data, width = 480, height = 90, color = "var(--state-blue)" }: BarHistogramProps) {
  const max = Math.max(...data.map((d) => d.value), 1);
  const barWidth = width / data.length;
  const gap = Math.min(3, barWidth * 0.25);

  return (
    <svg width="100%" viewBox={`0 0 ${width} ${height + 14}`} role="img" aria-label="Fréquence de détection par heure">
      {data.map((d, i) => {
        const barHeight = (d.value / max) * height;
        const x = i * barWidth;
        const y = height - barHeight;
        return (
          <g key={d.label}>
            <rect
              x={x + gap / 2}
              y={y}
              width={Math.max(1, barWidth - gap)}
              height={barHeight}
              fill={color}
              opacity={d.value === 0 ? 0.12 : 0.75}
            />
            {i % 3 === 0 ? (
              <text
                x={x + barWidth / 2}
                y={height + 11}
                fontSize="9"
                textAnchor="middle"
                fill="var(--text-muted)"
                fontFamily="var(--font-mono)"
              >
                {d.label}
              </text>
            ) : null}
          </g>
        );
      })}
    </svg>
  );
}
