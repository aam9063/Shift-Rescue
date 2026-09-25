# Evaluation report

Results of the evaluation harness (spec §8) as of the latest run, plus the
failures found while building the project and how they were fixed.

## 1. Automated suites

| Suite | Command | Result |
|---|---|---|
| Backend unit | `cd backend && uv run pytest` | **211 passed** |
| Backend integration (real PostgreSQL) | `DATABASE_URL=... uv run pytest tests/integration -m integration` | **2 passed** |
| Domain coverage gate (≥95%) | `uv run pytest --cov` | **100%** on `app/domain/` |
| Frontend | `cd frontend && pnpm vitest run` | **81 passed** |
| Lint / types | `ruff check`, `mypy app` (strict), `oxlint` | clean |
| Scenarios (§8.2) | `make eval` | **14/14 green, 0 invariant violations** |

## 2. Scenario suite (`evals/scenarios/*.yaml`)

Every scenario runs hermetically (FakeClock, in-memory scheduler, simulated
channel, DB-backed mock HRIS) and is checked by **deterministic invariant
code** — never an LLM judge (§8.3). Minimum set per spec §8.2:

| Scenario | Asserts |
|---|---|
| `quick_coverage` | first wave covers the shift |
| `second_wave_coverage` | wave 2 covers after wave 1 silence |
| `no_candidates` | immediate escalation |
| `all_decline` | waves exhausted → escalation |
| `acceptance_race` | one winner, loser gets `offer_already_covered` |
| `conditional_approved` / `conditional_rejected` | partial-coverage approval path |
| `withdraw_after_accept` | reopen + new waves |
| `absent_retracts_cancel` | manager approves cancellation |
| `shift_already_started` | remainder of a running shift can be covered |
| `quiet_hours_deferred` | offers deferred to quiet-hours end |
| `hris_failure_escalates` | retries ×3 → technical escalation |
| `llm_down_degraded` | provider down → deterministic parser keeps working |
| `manipulation_and_health` | manipulation ignored, health details redacted |

## 3. Interpreter golden set (§8.1)

`evals/golden/interpreter_golden.jsonl`: **150 labelled messages** covering
accepts, declines, 20 conditionals with time extraction ("las 7 y cuarto" →
07:15), reports (with and without health details), retractions, withdrawals,
ambiguous input, questions, smalltalk, manipulation attempts and English.

| Provider | Intent accuracy | Notes |
|---|---|---|
| Deterministic parser (degraded mode, offline) | **0.3733** | informational floor; it only knows an explicit vocabulary |
| Real model (`--provider interpreter`) | **pending** | needs `ANTHROPIC_API_KEY`; thresholds in `evals/thresholds.yaml` (intent ≥0.92, health ≥0.95, times ≥0.80) |

The parser baseline is deliberately low: it exists so the product still works
when the LLM is unavailable, not to replace it.

## 4. Failures found during development (and their fixes)

These are real defects the project caught — most of them by running the system
end to end rather than by unit tests alone.

| # | Failure | Root cause | Fix |
|---|---|---|---|
| 1 | Rest periods wrong across the DST change | CPython returns the **naive** difference when subtracting two aware datetimes with the **same tzinfo** object | all engine durations computed on UTC-normalized datetimes; property test covers the DST boundary |
| 2 | Silent data loss in tests | SQLite in-memory + StaticPool with nested sessions: an inner commit invalidates the outer transaction | test harnesses use temp **file** databases |
| 3 | Rescue deadline escalated too early | `max(start-30min, opened+10min)` instead of spec §5.3 ("start-30min, or opened+10 if already passed") | deadline logic corrected (regression test) |
| 4 | Wave 1 offers disappeared when wave 2 started | implementation expired previous offers; spec §5.3 keeps them alive until the rescue closes | wave timeout only sends the next wave; offers stay PENDING (test) |
| 5 | Confirmation transaction rolled back **after** the messages had been sent | composed ids (`msg_out_offer_case_shift_lt_..._w1_emp_13_floor`) exceeded `VARCHAR(64)` | ids are uuid-based; regression test asserts every persisted id ≤ 64 chars |
| 6 | Wave timeouts / deadlines never fired in the deployed API | the in-memory `SimScheduler` was never advanced outside the eval harness | FastAPI lifespan ticker drives `run_due` every 5 s (Celery beat remains the production path); integration test |
| 7 | Twilio webhook returned **403** behind the tunnel | signature was validated against the internal `http://api:8000` URL instead of the public one | validate against the forwarded public URL (`X-Forwarded-Proto/Host`) |
| 8 | Twilio reported **12300** on every inbound | webhook answered without a `Content-Type` | endpoints answer empty TwiML (`application/xml`) |
| 9 | One rejected recipient crashed the whole webhook (500) | provider error propagated out of the wave loop | delivery failures are audited (`DELIVERY_FAILED`), that candidate is cancelled, the wave survives |
| 10 | Employee absence not found on the demo day | seed built a fixed two-week window starting in the future; the lookup window was 4 h | the seed starts on the current day; the lookup window is 24 h and matches shifts that have not ended |
| 11 | Cannot send WhatsApp from the sandbox | Twilio **trial** accounts cannot send via API (`21654`, Content API `401`); after upgrading, the account's **Primary Compliance Profile** must be approved (`20003`) | provider-side; documented in `docs/twilio-sandbox-setup.md` (worked around by upgrading + submitting the Trust Hub profile) |

## 5. Known gaps

- The real-model interpreter run (accuracy thresholds) needs an API key; the
  harness and thresholds are ready.
- Celery beat should own the scheduled work in production (the lifespan ticker
  covers the demo and restarts lose in-flight timers).
- The two-phone acceptance run needs a second WhatsApp number joined to the
  sandbox; everything else is verified live.
- `make eval-models` (Anthropic vs Bedrock vs NaN comparison) is prepared but
  pending keys.
