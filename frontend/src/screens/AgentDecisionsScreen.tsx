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

/**
 * Agent decisions inspector (spec §7.6 screen 8, mockup "Decisiones del
 * agente"): every LLM interpretation with confidence, model, cost, latency
 * and validation result.
 */
export function AgentDecisionsScreen() {
  const { decisions } = useAgentDecisions()
  const [filter, setFilter] = useState<FilterId>('all')

  const filtered = decisions.filter((d) => {
    if (filter === 'low-confidence') return d.confidence < 0.75
    if (filter === 'validation-failed') return d.validation !== 'OK'
    if (filter === 'unclear') return d.intent === 'UNCLEAR'
    return true
  })

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
              className={`cursor-pointer rounded-pill px-4 py-2 text-sm font-semibold tracking-tight transition-all duration-200 active:scale-95 ${
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

      <div className="rounded-card bg-surface px-4 py-2 shadow-card">
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-black/5 text-xs uppercase tracking-wider text-text-secondary">
              <th className="py-3 pr-4 font-medium">Time</th>
              <th className="py-3 pr-4 font-medium">Empleado</th>
              <th className="py-3 pr-4 font-medium">Intent</th>
              <th className="py-3 pr-4 font-medium">Confianza</th>
              <th className="py-3 pr-4 font-medium">Modelo</th>
              <th className="py-3 pr-4 font-medium">Coste</th>
              <th className="py-3 pr-4 font-medium">Latencia</th>
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
                  <span
                    className={`text-sm font-semibold tracking-tight ${
                      d.validation === 'OK' ? 'text-green-accent' : 'text-gold'
                    }`}
                  >
                    {d.validation}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
