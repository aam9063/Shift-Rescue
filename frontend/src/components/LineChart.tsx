export interface LineChartProps {
  values: number[]
  /** Optional dashed reference line (e.g. the eval threshold). */
  reference?: number
  ariaLabel: string
  leftCaption?: string
  rightCaption?: string
}

/** Minimal dependency-free SVG line chart (mockup: Operaciones / Evals). */
export function LineChart({
  values,
  reference,
  ariaLabel,
  leftCaption,
  rightCaption,
}: LineChartProps) {
  if (values.length === 0) {
    return <p className="text-sm text-text-secondary">Sin datos</p>
  }
  const width = 560
  const height = 160
  const padding = 8
  const all = reference != null ? [...values, reference] : values
  const min = Math.min(...all)
  const max = Math.max(...all)
  const span = max - min || 1
  const stepX = (width - padding * 2) / (values.length - 1 || 1)
  const points = values.map((v, i) => {
    const x = padding + i * stepX
    const y = height - padding - ((v - min) / span) * (height - padding * 2)
    return `${x},${y}`
  })
  const refY =
    reference != null
      ? height - padding - ((reference - min) / span) * (height - padding * 2)
      : null

  return (
    <figure aria-label={ariaLabel}>
      <svg
        role="img"
        aria-label={ariaLabel}
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="xMidYMid meet"
        className="h-auto w-full"
        data-testid="line-chart"
      >
        {refY != null && (
          <line
            x1={padding}
            x2={width - padding}
            y1={refY}
            y2={refY}
            stroke="#d4e9e2"
            strokeDasharray="4 4"
          />
        )}
        <polyline
          points={points.join(' ')}
          fill="none"
          stroke="#006241"
          strokeWidth={2.5}
          strokeLinejoin="round"
        />
      </svg>
      {(leftCaption || rightCaption) && (
        <figcaption className="flex justify-between text-xs text-text-secondary">
          <span>{leftCaption}</span>
          <span>{rightCaption}</span>
        </figcaption>
      )}
    </figure>
  )
}
