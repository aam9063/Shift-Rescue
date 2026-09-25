# Evaluation report

Results of the evaluation harness (spec §8) as of the latest run, plus the
failures found while building the project and how they were fixed.

## 1. Automated suites

| Suite | Command | Result |
|---|---|---|
| Backend unit | `cd backend && uv run pytest` | **308 passed** |
| Backend integration (real PostgreSQL) | `DATABASE_URL=... uv run pytest tests/integration -m integration` | **2 passed** |
| Domain coverage gate (≥95%) | `uv run pytest --cov` | **100%** on `app/domain/` |
| Frontend | `cd frontend && pnpm vitest run` | **83 passed** |
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

| Provider / prompt | Intent accuracy | Health detection | Conditional times | Avg latency | Avg cost | Verdict |
|---|---|---|---|---|---|---|
| Deterministic parser (degraded mode, offline) | 0.3733 | 0.0 | 0.0 | — | — | informational floor; it only knows an explicit vocabulary |
| Deterministic parser + context (offline) | 0.3733 | 0.0 | 0.0 | — | — | same run, kept for reference |
| `gpt-4o-mini`, `interpreter_v1` | 0.86 | 0.9167 | 0.95 | 1051 ms | $0.000211 | **2 violations** (intent < 0.92, health < 0.95) |
| `gpt-4o-mini`, `interpreter_v2` | **0.9333** | **1.0** | **0.85** | 1047 ms | $0.000298 | **thresholds met** (intent ≥ 0.92, health ≥ 0.95, times ≥ 0.80) |

The v2 prompt added an explicit decision procedure keyed on the context the
harness already supplies (`[pending_offers]` before `[pending_confirmation]`
before "nothing pending"), numeric replies (`1` = yes, `2` = no) only when
something is pending, a broader health rule (any symptom, malaise or medical
reference), and worked examples for the confusions the v1 run exposed
(`OFFER_ACCEPT` vs `ABSENCE_CONFIRM`, `OFFER_WITHDRAW` vs `OFFER_DECLINE`,
`"xq no puedo ir hoy"` as a statement rather than a question).

Run-to-run spread at temperature 0 is real but small (v1 measured 0.86 and 0.84
in two consecutive runs); the prompt change is larger than that spread.

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

### 5.1 The threshold gate silently passed for months

`check_thresholds()` iterated hardcoded keys ending in `_min`/`_max`
(`intent_accuracy_min`) while the report stored the values without the suffix
(`intent_accuracy`), so `report.get(key)` returned `None` for every entry, every
comparison was skipped and the runner printed **"Thresholds met."** while two
thresholds were violated. `evals/thresholds.yaml` was never read at all.

Fixed: thresholds now live in `backend/app/evals/thresholds.py`, read the YAML
(single source of truth, max *and* min directions), and **fail closed** — an
unmapped key, an unknown metric or a non-numeric value is a violation rather
than a silent pass. Verified against the real v1 report, which now reports
exactly the two violations it always had.

### 5.2 `OFFER_WITHDRAW` is not inferable from the context the harness supplies

Six of the ten remaining failures (`no puedo al final`, `imposible al final`,
`tengo que cancelar`, `no podré ir`, `i need to cancel`) carry **the same
context** as cases labelled `OFFER_DECLINE` and `OFFER_ACCEPT`:
`{"pending_offers": ["offer_1"], ...}`. The golden set distinguishes them by
wording alone, so the only way to match it is a lexical rule for the word
"al final" — which would be prompt overfitting, not a real capability.

The product fix is to put the missing fact in the context: when an employee has
already accepted and now cancels, the orchestrator knows it, and the interpreter
should receive that marker (e.g. `[accepted_offer=offer_1]`) so the distinction
is state, not guesswork. Tracked as its own work unit; the remaining four
failures are one accentless `"si"`, one colloquial `"allí estaré"`, one
`QUESTION`/`SMALLTALK` boundary and one adversarial case (`"cancele el caso de
todos"` → expected `UNCLEAR`).

### 5.3 Scheduled work

Celery beat owns the scheduled work (every 5 s `run-due-jobs`, daily retention
purge). The in-memory `SimScheduler` still loses in-flight timers if the worker
restarts, so wave deadlines survive a restart only once the schedule lives in
the database.
- The two-phone acceptance run needs a second WhatsApp number joined to the
  sandbox; everything else is verified live.
- `make eval-models` (Anthropic vs Bedrock vs NaN comparison) is prepared but
  pending keys.
