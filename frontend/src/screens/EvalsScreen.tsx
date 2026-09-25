import { LineChart } from '../components/LineChart'
import { useEvalRun } from '../services/dashboard'

/**
 * Evals screen (spec §7.6 screen 9, mockup "Evals"): latest run status,
 * intent accuracy evolution vs threshold, per-scenario results, model
 * comparison and the invariants card.
 */
export function EvalsScreen() {
  const { evalRun } = useEvalRun()
  if (!evalRun) {
    return <p className="text-base text-text-secondary">Loading…</p>
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-4">
        <h1 className="font-serif text-4xl font-semibold tracking-tight text-green-starbucks">
          Evals
        </h1>
        <span
          className={`flex items-center gap-2 rounded-pill px-4 py-2 text-sm font-semibold tracking-tight ${
            evalRun.passed ? 'bg-green-light text-green-house' : 'bg-error/10 text-error'
          }`}
        >
          <span className={`size-2 rounded-full ${evalRun.passed ? 'bg-green-accent' : 'bg-error'}`} />
          {evalRun.passed ? 'Latest run: passes thresholds' : 'Latest run: FAILING'}
        </span>
        <span className="text-sm text-text-secondary">
          commit {evalRun.commit} · {evalRun.ranAgo}
        </span>
      </div>

      <p className="text-sm tracking-tight text-text-secondary">
        Note: eval data is not live yet — the runs endpoint is not implemented, so this
        screen shows mock results.
      </p>

      <div data-testid="evals-grid" className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-5">
        <div className="space-y-4 rounded-card bg-surface p-6 shadow-card lg:col-span-3">
          <h2 className="text-lg font-semibold tracking-tight">
            Intent accuracy, last 10 runs
          </h2>
          <LineChart
            values={evalRun.accuracyHistory}
            reference={evalRun.threshold}
            ariaLabel="Intent accuracy evolution"
            leftCaption={`threshold ${evalRun.threshold}`}
            rightCaption={`current ${evalRun.latestAccuracy}`}
          />
          <h3 className="pt-2 text-base font-semibold tracking-tight">Per-scenario results</h3>
          <ul className="divide-y divide-black/5">
            {evalRun.scenarios.map((scenario) => (
              <li key={scenario.id} className="flex items-center justify-between py-2 text-sm">
                <span className="tracking-tight">{scenario.id}</span>
                <span className={`font-semibold ${scenario.passed ? 'text-green-accent' : 'text-error'}`}>
                  {scenario.passed ? 'passes' : 'fails'}
                </span>
              </li>
            ))}
          </ul>
        </div>

        <div className="space-y-6 lg:col-span-2">
          <div className="rounded-card bg-surface p-6 shadow-card">
            <h2 className="mb-3 text-lg font-semibold tracking-tight">Model comparison</h2>
            <ul className="space-y-2">
              {evalRun.models.map((model) => (
                <li key={model.name} className="flex items-center justify-between text-sm">
                  <span className="font-medium tracking-tight">{model.name}</span>
                  <span className="text-text-secondary">
                    acc {model.accuracy.toFixed(2)} · {model.costPerMessage}
                  </span>
                </li>
              ))}
            </ul>
          </div>
          <div className="rounded-card bg-green-house p-6 text-white">
            <p className="text-sm font-medium tracking-tight text-white/80">Invariantes</p>
            <p className="mt-1 font-serif text-5xl font-bold">
              {evalRun.invariantViolations}
            </p>
            <p className="mt-1 text-sm tracking-tight text-white/70">
              violations in this run
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
