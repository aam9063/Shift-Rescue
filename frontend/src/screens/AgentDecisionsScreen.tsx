import { useState } from 'react'
import { useAgentDecisions } from '../services/dashboard'

const FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'low-confidence', label: 'Low confidence' },
  { id: 'validation-failed', label: 'Validation failed' },
  { id: 'unclear', label: 'UNCLEAR' },
] as const

type FilterId = (typeof FILTERS)[number]['id']

function ConfidenceBar({ confidence }: { confidence: number }) {
  const color =
    confidence >= 0.75 ? 'bg-green-accent' : confidence >= 0.6 ? 'bg-gold' : 'bg-error'
  return (
    <span className="flex items-center gap-2">
      <span className="h-1.5 w-16 overflow-hidden rounded-full bg-black/10">
        <span
          className={`block h-full rounded-full ${color}`}
          style={{ width: `${Math.round(confidence * 100)}%` }}
        />
      </span>
      <span className="text-sm font-medium tracking-tight">
        {confidence.toFixed(2)}
      </span>
    </span>
  )
}

function ValidationLabel({ validation }: { validation: string }) {
  return (
    <span
      className={`text-sm font-semibold tracking-tight ${
        validation === 'OK' ? 'text-green-accent' : 'text-gold'
      }`}
    >
      {validation}
    </span>
  )
}

/**
 * Phone variant (below `md`) of a decision row: the same eight fields as the
 * table, stacked. CSS-controlled sibling of the table (DESIGN.md §8: wide
 * data becomes a list on small screens).
 */
function DecisionCard({
  decision: d,
}: {
  decision: {
    time: string
    employeeName: string
    intent: string
    confidence: number
    model: string
    costUsd: number
    latencyMs: number
    validation: string
  }
}) {
  return (
    <li className="rounded-card bg-surface px-4 py-3 shadow-card">
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-sm font-semibold tracking-tight">{d.employeeName}</p>
        <p className="text-sm text-text-secondary">{d.time}</p>
      </div>
      <p className="mt-1 text-sm font-medium tracking-tight">{d.intent}</p>
      <div className="mt-2">
        <ConfidenceBar confidence={d.confidence} />
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
        <div className="flex justify-between gap-2">
          <dt className="text-text-secondary">Model</dt>
          <dd className="text-right">{d.model}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="text-text-secondary">Cost</dt>
          <dd className="text-right">${d.costUsd.toFixed(3)}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="text-text-secondary">Latency</dt>
          <dd className="text-right">{d.latencyMs}ms</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="text-text-secondary">Validation</dt>
          <dd className="text-right">
            <ValidationLabel validation={d.validation} />
          </dd>
        </div>
      </dl>
    </li>
  )
}

/**
 * Agent decisions inspector (spec §7.6 screen 8, mockup "Decisiones del
 * agente"): every LLM interpretation with confidence, model, cost, latency
 * and validation result.
 */
export function AgentDecisionsScreen() {
  const { decisions, error, isLoading } = useAgentDecisions()
  const [filter, setFilter] = useState<FilterId>('all')

  const filtered = decisions.filter((d) => {
    if (filter === 'low-confidence') return d.confidence < 0.75
    if (filter === 'validation-failed') return d.validation !== 'OK'
    if (filter === 'unclear') return d.intent === 'UNCLEAR'
    return true
  })

  if (error !== null && error !== undefined) {
    const forbidden = (error as { status?: number }).status === 403
    return (
      <div className="space-y-6">
        <h1 className="font-serif text-4xl font-semibold tracking-tight text-green-starbucks">
          Agent decisions
        </h1>
        <p role="alert" className="rounded-card bg-surface px-5 py-4 text-sm tracking-tight text-text-secondary shadow-card">
          {forbidden
            ? 'This view is for the operator account: it shows what the model decided and costs money to run. Sign in as operator@laterraza.demo to see it.'
            : 'The agent decisions could not be loaded. Check that the API is reachable and try again.'}
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="font-serif text-4xl font-semibold tracking-tight text-green-starbucks">
          Agent decisions
        </h1>
        <div className="flex flex-wrap gap-2">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              type="button"
              onClick={() => setFilter(f.id)}
              className={`pointer-coarse:min-h-11 cursor-pointer rounded-pill px-4 py-2 text-sm font-semibold tracking-tight transition-all duration-200 active:scale-95 ${
                filter === f.id
                  ? 'bg-green-house text-white'
                  : 'border border-black/10 bg-surface text-text-primary'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <p className="text-sm tracking-tight text-text-secondary">Loading...</p>
      ) : null}
      <ul aria-label="Agent decisions" className="space-y-3 md:hidden">
        {filtered.map((d) => (
          <DecisionCard key={`${d.time}-${d.employeeName}`} decision={d} />
        ))}
      </ul>

      <div
        data-testid="agent-decisions-table"
        className="hidden overflow-x-auto rounded-card bg-surface px-4 py-2 shadow-card md:block"
      >
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-black/5 text-xs uppercase tracking-wider text-text-secondary">
              <th className="py-3 pr-4 font-medium">Time</th>
              <th className="py-3 pr-4 font-medium">Employee</th>
              <th className="py-3 pr-4 font-medium">Intent</th>
              <th className="py-3 pr-4 font-medium">Confidence</th>
              <th className="py-3 pr-4 font-medium">Model</th>
              <th className="py-3 pr-4 font-medium">Cost</th>
              <th className="py-3 pr-4 font-medium">Latency</th>
              <th className="py-3 font-medium">Validation</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((d) => (
              <tr key={`${d.time}-${d.employeeName}`} className="border-b border-black/5 last:border-0">
                <td className="py-3 pr-4 text-sm text-text-secondary">{d.time}</td>
                <td className="py-3 pr-4 text-sm font-semibold tracking-tight">{d.employeeName}</td>
                <td className="py-3 pr-4 text-sm font-medium tracking-tight">{d.intent}</td>
                <td className="py-3 pr-4">
                  <ConfidenceBar confidence={d.confidence} />
                </td>
                <td className="py-3 pr-4 text-sm text-text-secondary">{d.model}</td>
                <td className="py-3 pr-4 text-sm text-text-secondary">${d.costUsd.toFixed(3)}</td>
                <td className="py-3 pr-4 text-sm text-text-secondary">{d.latencyMs}ms</td>
                <td className="py-3">
                  <ValidationLabel validation={d.validation} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
