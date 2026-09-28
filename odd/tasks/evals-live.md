# Feature: evals-live

**Status**: in progress
**Branch**: `feature/dashboard-live`
**Spec references**: §7.5 (`GET /api/evals/runs`, `/api/evals/runs/{id}`, operator only), §7.6 (screen 9), §8 (evaluation)
**Design system**: `DESIGN.md`

## Problem

The Evals screen is the last one rendering invented data, and it says so in the
interface ("eval data is not live yet — the runs endpoint is not implemented, so
this screen shows mock results"). Verified:

- `eval_run` table: **0 rows** — the model exists with rich columns (git sha,
  trigger, timings, `model_config`, `prompt_versions`, `metrics`,
  `invariant_violations`, `passed`, `baseline_run_id`, `report_path`) and has
  never had a writer.
- `GET /api/evals/runs*`: **does not exist**.
- The evaluation itself is real and runs from the terminal: a 150-sample golden
  set with thresholds, and the scenario suite with invariant checks — the last
  measured numbers with the real provider were **0.9935 intent accuracy, 1.0
  health detection, 0.95 conditional times**.

So the engine is built and nothing shows it. An evaluator opening "Evals" sees
numbers that came from nowhere.

## Decisions (fixed, do not re-litigate)

1. **The runners record their own runs.** The golden-set runner
   (`evals/runner.py`) persists one `eval_run` row per execution: metrics,
   model and provider, prompt version, git sha, trigger (`manual`, or `ci` when
   the environment says so), the timing, the threshold verdict in `passed`, the
   report path, and the per-scenario results in `metrics` when the suite is the
   scenario one.
2. **The scenario suite becomes recordable too.** It already runs through the
   harness in the test suite; expose a way to execute it and record per-scenario
   pass/fail plus invariant violations, so the screen's "Per-scenario results"
   is real and not renamed golden failures.
3. **The API serves what the screen needs.** `GET /api/evals/runs` (list, newest
   first, bounded), `GET /api/evals/runs/{id}` (detail) and
   `GET /api/evals/runs/summary` returning exactly the shape the screen already
   consumes (verdict, commit, when it ran, accuracy history, threshold, latest
   accuracy, per-scenario results, model comparison, invariant violations).
   All three require the **operator** role (spec §7.5).
4. **No runs is an honest empty state**, not mock data: the screen says there are
   no recorded runs and how to produce one. The mock stays behind
   `VITE_USE_MOCK` for offline work, and the "not live yet" note disappears.
5. **Nothing is invented in the UI.** A section whose data does not exist yet
   (for example, no scenario run recorded) says so instead of showing zeros that
   look like failures.

## Tasks

### T1 — Recording (backend + runner)
A small module that writes an `eval_run` row from a report dict (id from the
shared uuid convention, `started_at`/`finished_at`, `metrics`, `passed` from the
threshold check, `model_config`, `prompt_versions`, `git_sha`, `trigger`,
`report_path`). `evals/runner.py` calls it after each run (both `--provider
parser` and `--provider interpreter`), and the scenario entry point calls it with
the per-scenario results and the invariant violations.

### T2 — Endpoints (`app/api/evals.py`, operator-only)
`GET /api/evals/runs?limit=`, `GET /api/evals/runs/{id}` and
`GET /api/evals/runs/summary` composed from the rows: accuracy history across
golden runs, the threshold from the thresholds file, the latest accuracy, the
scenario results from the newest scenario run, and the model comparison grouped
by `model_config`.

### T3 — Screen (`frontend`)
`useEvalRun` reads the summary; the "not live yet" note goes away; an empty state
appears when there are no runs (with the exact command to produce one); the mock
keeps working behind `VITE_USE_MOCK`.

### T4 — Tests and docs
- Backend: recording writes the expected fields and marks `passed` from the
  thresholds; the summary composes history/scenarios/models from several runs;
  the endpoints require `operator` (403 for a manager); the empty case returns an
  empty summary that the UI can render.
- Frontend: the screen renders the live summary, shows the empty state without
  runs, and keeps the mock path.
- `docs/runbook.md`: how to record an eval run and see it in the dashboard.
- `docs/eval-report.md`: point at the dashboard as the live view of the same data.

## Acceptance criteria

1. Running the golden-set or scenario evaluation records a row in `eval_run`.
2. Open `/api/evals/runs/summary` with an operator token returns the real
   numbers, the verdict and the scenario results.
3. The Evals screen shows the recorded data with no "not live yet" note, or an
   honest empty state when there is nothing recorded.
4. Recording never breaks a run that fails its thresholds — a failing run is
   recorded with `passed: false`.
5. Suites green: backend, frontend, ruff, mypy, oxlint, build, tsc.

## Verification evidence

_Pending._
