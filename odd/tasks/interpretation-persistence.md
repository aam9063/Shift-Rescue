# Feature: interpretation-persistence

**Status**: in progress
**Branch**: `feature/dashboard-live` (from `feature/webhook-offload`)
**Spec references**: §5.5 (withdrawals), §6.2 (interpreter), §7.5 (`/api/interpretations`), §7.6 (Agent decisions screen), §8.1 (golden set)
**ADRs**: ADR-002 (prompt versioning), ADR-004 (provider selection)

## Problem

Two gaps, one dependency:

1. **`OFFER_WITHDRAW` is not inferable.** Six of the ten remaining golden-set
   failures (`no puedo al final`, `imposible al final`, `tengo que cancelar`,
   `no podré ir`, `i need to cancel`) carry **the same context** as cases
   labelled `OFFER_DECLINE`: `{"pending_offers": ["offer_1"], ...}`. The state
   that makes the label correct — the employee had already accepted that offer —
   is never sent to the model, so the only way to match the golden set is a
   lexical rule for the words "al final". That is prompt overfitting, not a
   capability.
2. **Interpretations are never persisted.** The `interpretation` table
   (`app/db/models.py`) has no writer anywhere in `app/`, so the "Agent
   decisions" screen specified in §7.6 has no real data source: it renders mock
   data even though the LLM answers production traffic.

The second gap is what blocks connecting the dashboard's decisions screen, so
both are fixed here in order.

## Decisions (fixed, do not re-litigate)

1. **The missing state is passed as context, not guessed.** The orchestrator
   sends the offers the employee has already accepted (`accepted_offers`)
   alongside `pending_offers`. A cancellation with an accepted offer is a
   withdrawal; a negative answer with only a pending offer is a decline.
2. **The prompt is versioned, not edited in place** (ADR-002): `interpreter_v3`
   adds the marker rule on top of v2's decision procedure, and
   `PROMPT_VERSION` is bumped so every stored interpretation is attributable.
3. **The golden fixture is corrected, not fitted.** For the rows labelled
   `OFFER_WITHDRAW` the fixture gains `"accepted_offers": ["offer_1"]`, because
   the fixture described an incomplete world state for those labels — without it
   the expected value contradicts the other rows that share the same context.
   Expected *labels* are never changed.
4. **Persistence is best effort but real**: one row per LLM interpretation
   (never one per parser decision — a degraded-mode decision is not an LLM
   decision), written in the same flow, with a duplicate provider message
   producing no second row.
5. **Never persist health details**: `extracted` carries structured fields
   only; message bodies stay redacted as today (spec §10).

## Tasks

### T1 — Accepted-offer context (`app/services/orchestrator.py`)
`accepted_offers` in the LLM context: ids of the employee's accepted offers
whose rescue case is still open (verify the exact status value in
`app/db/models.py`). Absent or empty list when there are none.

### T2 — Prompt v3 (`app/agent/prompts/interpreter_v3.md`)
Extend v2's decision table with the accepted-offer row and an example per
confusion. Bump `PROMPT_VERSION` in `app/agent/interpreter.py`; the version
flows to the interpreter and to every stored interpretation automatically.

### T3 — Golden fixture (`evals/golden/interpreter_golden.jsonl`)
Add `"accepted_offers": ["offer_1"]` to the `OFFER_WITHDRAW` rows, with the
rationale recorded in this document and in `docs/eval-report.md`.

### T4 — Expose measurement (`app/agent/interpreter.py`)
`MessageInterpreter.last_usage` (delegating to the wrapped client when it
exposes one, otherwise `None`) so the orchestrator can persist tokens, latency
and cost without reaching into private attributes.

### T5 — Persist interpretations (`app/services/orchestrator.py`)
- `_persist_inbound` returns the created message id (or `None` for a duplicate)
  instead of a bool; callers and tests adapt.
- After a successful LLM interpretation, insert one `Interpretation` row:
  `message_id`, `intent`, `confidence`, `extracted` (structured fields only),
  `model`, `prompt_version`, `latency_ms`, `input_tokens`, `output_tokens`,
  `cost_usd`, taken from the interpreter and its `last_usage`.
- A failure to persist must not break the rescue: log a warning and continue.
- No row for the deterministic-parser path.

### T6 — Tests and docs
- Context: `accepted_offers` present with an accepted offer and absent without
  one (unit, fake workforce).
- Persistence: one row per LLM interpretation with the measured numbers; no row
  when the parser answers or the provider is degraded; no second row for a
  duplicate provider message; a persistence failure is logged and the flow
  continues.
- `MessageInterpreter.last_usage` for a client that reports usage and for one
  that does not.
- `docs/eval-report.md`: the v3 measurement and the fixture correction.
- This document's evidence section.

## Acceptance criteria

1. The `OFFER_WITHDRAW` golden rows pass with the marker present and their
   expected labels are unchanged.
2. Every LLM interpretation leaves exactly one `interpretation` row carrying
   model, prompt version, tokens, latency and cost.
3. The parser path leaves no row, and a duplicate message leaves no second row.
4. `uv run pytest -q`, `uv run ruff check .`, `uv run mypy app` clean.

## Verification evidence

Status spelling verified in the codebase before filtering: `"ACCEPTED"` — set
by `_try_accept_offer` (`offer.status = "ACCEPTED"`, orchestrator), filtered by
`_coverage_counts` (`Offer.status == "ACCEPTED"`), documented in
`app/db/models.py:127-128`. An accepted offer always implies a non-`OPEN` case
(acceptance moves it to COVERED/PARTIALLY_COVERED), so "case still open" was
implemented as *not finally resolved*: `RescueCase.status NOT IN
("CLOSED_BY_MANAGER", "CANCELLED")` — otherwise the marker could never reach
the model for the withdrawal flow it exists for.

### Changes

- `backend/app/services/orchestrator.py` — `accepted_offers` in the LLM context
  (new `_accepted_offer_ids`); `_persist_inbound` now returns the created
  message id (`str | None`); new `_persist_interpretation` writes exactly one
  `Interpretation` row per LLM interpretation (structured `extracted` fields
  only, zeroed usage defaults, warning + continue on failure); parser and
  degraded paths write nothing.
- `backend/app/agent/interpreter.py` — `PROMPT_VERSION = "interpreter_v3"`;
  `MessageInterpreter.last_usage` read-only property (wrapped client's dict or
  `None`).
- `backend/app/agent/prompts/interpreter_v3.md` — v2 copied intact; adds the
  `[accepted_offers=...]` context line, the marker rule (cancellation with an
  accepted offer → OFFER_WITHDRAW; negative with only pending offers →
  OFFER_DECLINE) and worked examples for both sides of the confusion.
- `evals/golden/interpreter_golden.jsonl` — `"accepted_offers": ["offer_1"]`
  added to the 11 `OFFER_WITHDRAW` rows only; every expected label and every
  other row byte-identical (150 rows, verified programmatically). Rationale:
  the fixture described an incomplete world state for those labels (identical
  context to the decline rows), so the state is now part of the input rather
  than something the model must infer from wording.
- `backend/tests/unit/services/test_interpreter_wiring.py` — context
  (`accepted_offers` populated/empty, existing keys untouched) and persistence
  tests (measured usage row, zero defaults, parser/no-interpreter paths write
  nothing, duplicate provider message → one row, persistence failure logged and
  flow continues).
- `backend/tests/unit/agent/test_interpreter.py` — `last_usage` present/None;
  one pre-existing assertion adapted (schema default vs `PROMPT_VERSION`, see
  deviations).
- `docs/eval-report.md` — v3 table row marked `pending parent measurement` and
  the fixture-correction note; §5.2 marked fixed.

### Deviations

- `test_full_structured_payload_with_prompt_version_is_accepted` constructed a
  payload from the schema default (`interpreter_v2`) and asserted it equals
  `PROMPT_VERSION`; with the bump to v3 it was changed to pass
  `prompt_version=PROMPT_VERSION` explicitly. The schema default itself
  (`app/agent/schemas.py`) is outside this task's edit surfaces and was left
  untouched.
- ruff isort required the aliased model import on its own line
  (`from app.db.models import Interpretation as InterpretationRow`) and the
  wiring tests use the same alias to avoid shadowing the pydantic schema.

### Checks (observed)

```
cd backend && uv run pytest -q
→ 317 passed, 2 skipped in 24.45s   (was 308 passed, 2 skipped)
cd backend && uv run ruff check .
→ All checks passed!
cd backend && uv run mypy app
→ Success: no issues found in 54 source files
cd backend && uv run python -c "from app.agent.interpreter import PROMPT_VERSION; print(PROMPT_VERSION)"
→ interpreter_v3
cd backend && uv run python -c "from app.agent.factory import load_system_prompt; p=load_system_prompt(); print(len(p), 'accepted_offers' in p)"
→ 5663 True
```

Not verified here (owner: parent): the real-model v3 golden run (costs money,
needs the key) — the eval-report v3 row is intentionally `pending parent
measurement`; OFFER_WITHDRAW accuracy against the real model is therefore
unconfirmed.
