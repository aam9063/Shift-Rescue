import { LineChart } from '../components/LineChart'
import { useOpsMetrics } from '../services/dashboard'

function KpiCard({
  label,
  value,
  caption,
  urgent = false,
}: {
  label: string
  value: string
  caption: string
  urgent?: boolean
}) {
  return (
    <div className="rounded-card bg-surface p-4 shadow-card">
      <p className="text-sm tracking-tight text-text-secondary">{label}</p>
      <p
        className={`mt-1 text-3xl font-bold tracking-tight ${
          urgent ? 'text-error' : 'text-green-starbucks'
        }`}
      >
        {value}
      </p>
      <p className="mt-1 text-xs tracking-tight text-text-secondary">{caption}</p>
    </div>
  )
}

/**
 * Ops screen (spec §7.6 screen 4, mockup "Operaciones"): LLM cost, p95
 * latency, low-confidence rate, stuck rescues, daily cost chart and active
 * alerts.
 */
export function OpsScreen() {
  const { metrics } = useOpsMetrics()
  if (!metrics) {
    return <p className="text-base text-text-secondary">Loading…</p>
  }

  return (
    <div className="space-y-6">
      <h1 className="font-serif text-4xl font-semibold tracking-tight text-green-starbucks">
        Operations
      </h1>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          label="Cost today"
          value={`$${metrics.costToday.toFixed(2)}`}
          caption={`${metrics.rescuesCount} rescues`}
        />
        <KpiCard
          label="Interpreter p95 latency"
          value={`${metrics.p95LatencyMs}ms`}
          caption={`target < ${metrics.latencyTargetMs / 1000}s`}
        />
        <KpiCard
          label="Low confidence"
          value={`${metrics.lowConfidencePct}%`}
          caption={`de ${metrics.lowConfidenceTotal} mensajes`}
        />
        <KpiCard
          label="Stuck rescues"
          value={String(metrics.stuckCount)}
          caption="more than 15 min without events"
          urgent={metrics.stuckCount > 0}
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="rounded-card bg-surface p-6 shadow-card lg:col-span-2">
          <h2 className="mb-4 text-lg font-semibold tracking-tight">
            Daily LLM cost (last 14 days)
          </h2>
          <LineChart
            values={metrics.costHistory}
            ariaLabel="Daily LLM cost"
            leftCaption="14 days ago"
            rightCaption="today"
          />
        </div>
        <div className="rounded-card bg-surface p-6 shadow-card">
          <h2 className="mb-3 border-b border-black/5 pb-2 text-lg font-semibold tracking-tight">
            Active alerts
          </h2>
          <ul className="space-y-3">
            {metrics.alerts.map((alert) => (
              <li key={alert.title} className="border-b border-black/5 pb-3 last:border-0 last:pb-0">
                <p className="flex items-center gap-2 text-sm font-semibold tracking-tight">
                  <span
                    className={`size-2 rounded-full ${
                      alert.severity === 'error' ? 'bg-error' : 'bg-gold'
                    }`}
                  />
                  {alert.title}
                </p>
                <p className="mt-1 text-sm tracking-tight text-text-secondary">{alert.detail}</p>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}
