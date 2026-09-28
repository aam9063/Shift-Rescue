import { LineChart } from '../components/LineChart'
import { useEvalRun } from '../services/dashboard'
import type { EvalRunSummaryLive } from '../services/api'

/** The exact commands that record a run (they write to `eval_run` themselves). */
const GOLDEN_RUN_COMMAND = 'cd backend && uv run python ../evals/runner.py --provider interpreter'
const SCENARIOS_RUN_COMMAND = 'cd backend && uv run python ../evals/runner.py --scenarios'

/**
 * Evals screen (spec §7.6 screen 9, mockup "Evals"): latest run status,
 * intent accuracy evolution vs threshold, per-scenario results, model
 * comparison and the invariants card — all composed from the recorded
 * `eval_run` rows; nothing is invented. Sections whose data does not exist
 * yet say so instead of showing zeros that look like failures.
 */
export function EvalsScreen() {
  const { evalRun, error, isLoading } = useEvalRun()
  if (isLoading) {
    return <p className="text-base text-text-secondary">Loading…</p>
  }
  if (error !== null || !evalRun) {
    return (
      <p className="text-base text-text-secondary">
        Eval runs could not be loaded. The runs endpoint needs an operator
        account — sign in with the operator user and reload.
      </p>
    )
  }
  if (!evalRun.hasRuns) {
    return <EmptyState />
  }
  return <Summary summary={evalRun} />
}

/** Honest empty state: no recorded runs, and the exact command to produce one. */
function EmptyState() {
  return (
    <div className="space-y-6">
      <h1 className="font-serif text-4xl font-semibold tracking-tight text-green-starbucks">
        Evals
      </h1>
      <div className="max-w-2xl space-y-4 rounded-card bg-surface p-6 shadow-card">
        <h2 className="text-lg font-semibold tracking-tight">No eval runs recorded yet</h2>
        <p className="text-sm tracking-tight text-text-secondary">
          This screen shows only recorded evaluation runs — nothing is invented.
          Run an evaluation to record the first one:
        </p>
        <code className="block rounded-card bg-black/5 px-4 py-3 text-sm tracking-tight">
          {GOLDEN_RUN_COMMAND}
        </code>
        <p className="text-sm tracking-tight text-text-secondary">
          The scenario suite records its own run too:
        </p>
        <code className="block rounded-card bg-black/5 px-4 py-3 text-sm tracking-tight">
          {SCENARIOS_RUN_COMMAND}
        </code>
      </div>
    </div>
  )
}

function Summary({ summary }: { summary: EvalRunSummaryLive }) {
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-4">
        <h1 className="font-serif text-4xl font-semibold tracking-tight text-green-starbucks">
          Evals
        </h1>
        <span
          className={`flex items-center gap-2 rounded-pill px-4 py-2 text-sm font-semibold tracking-tight ${
            summary.passed ? 'bg-green-light text-green-house' : 'bg-error/10 text-error'
          }`}
        >
          <span className={`size-2 rounded-full ${summary.passed ? 'bg-green-accent' : 'bg-error'}`} />
          {summary.passed ? 'Latest run: passes thresholds' : 'Latest run: FAILING'}
        </span>
        {summary.commit && (
          <span className="text-sm text-text-secondary">
            commit {summary.commit} · {summary.ranAgo}
          </span>
        )}
      </div>

      <div
        data-testid="evals-grid"
        className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-5"
      >
        <div className="space-y-4 rounded-card bg-surface p-6 shadow-card lg:col-span-3">
          <h2 className="text-lg font-semibold tracking-tight">
            Intent accuracy, last 10 runs
          </h2>
          {summary.accuracyHistory.length > 0 ? (
            <LineChart
              values={summary.accuracyHistory}
              reference={summary.threshold}
              ariaLabel="Intent accuracy evolution"
              leftCaption={`threshold ${summary.threshold}`}
              rightCaption={`current ${summary.latestAccuracy}`}
            />
          ) : (
            <p className="text-sm text-text-secondary">
              No golden-set runs recorded yet — the accuracy chart fills in as
              runs are recorded.
            </p>
          )}
          <h3 className="pt-2 text-base font-semibold tracking-tight">Per-scenario results</h3>
          {summary.scenarios.length > 0 ? (
            <ul className="divide-y divide-black/5">
              {summary.scenarios.map((scenario) => (
                <li key={scenario.id} className="flex items-center justify-between py-2 text-sm">
                  <span className="tracking-tight">{scenario.id}</span>
                  <span
                    className={`font-semibold ${scenario.passed ? 'text-green-accent' : 'text-error'}`}
                  >
                    {scenario.passed ? 'passes' : 'fails'}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-text-secondary">
              No scenario run recorded yet — run the scenario suite to record
              one.
            </p>
          )}
        </div>

        <div className="space-y-6 lg:col-span-2">
          <div className="rounded-card bg-surface p-6 shadow-card">
            <h2 className="mb-3 text-lg font-semibold tracking-tight">Model comparison</h2>
            {summary.models.length > 0 ? (
              <ul className="space-y-2">
                {summary.models.map((model) => (
                  <li key={model.name} className="flex items-center justify-between text-sm">
                    <span className="font-medium tracking-tight">{model.name}</span>
                    <span className="text-text-secondary">
                      acc {model.accuracy.toFixed(2)} · {model.costPerMessage}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-text-secondary">
                No model comparison yet — it fills in as different models record
                golden runs.
              </p>
            )}
          </div>
          <div className="rounded-card bg-green-house p-6 text-white">
            <p className="text-sm font-medium tracking-tight text-white/80">Invariantes</p>
            <p className="mt-1 font-serif text-5xl font-bold">{summary.invariantViolations}</p>
            <p className="mt-1 text-sm tracking-tight text-white/70">violations in this run</p>
          </div>
        </div>
      </div>
    </div>
  )
}
