# Feature: interpreter-quality

**Status**: closed — thresholds met; two follow-ups recorded
**Branch**: `feature/webhook-offload` (work done after the offload was verified)
**Spec references**: §8.1 (golden set), §8.3 (thresholds), §6.2 (interpreter prompt)
**ADRs**: ADR-002 (prompts are versioned files), ADR-004 (provider selection)

## Problem

Wiring the LLM (feature `llm-runtime-wiring`) made it possible, for the first
time, to run the golden set against a real model. That run exposed three
separate defects, in decreasing order of severity:

1. **The eval gate never gated anything.** `check_thresholds()` iterated
   hardcoded threshold keys (`intent_accuracy_min`) while the report stored the
   metrics without the suffix (`intent_accuracy`), so every lookup returned
   `None`, every comparison was skipped, and the runner printed
   **"Thresholds met."** with accuracy 0.86 against a 0.92 minimum.
   `evals/thresholds.yaml` was never read at all.
2. **A context key never reached the model.** `_build_prompt` forwarded
   `rescue_id`, `pending_offers` and `shifts_48h` but dropped
   `pending_confirmation`, so a bare `"1"` (expected `ABSENCE_CONFIRM`) was
   classifiable only by luck.
3. **The prompt had no decision procedure.** The golden set's expectations
   `OFFER_ACCEPT` / `OFFER_DECLINE` / `OFFER_WITHDRAW` / `ABSENCE_CONFIRM` all
   depend on *what is pending right now*, but the prompt stated the rules in an
   order that let the model read an affirmation as an absence confirmation while
   an offer was open.

## Goal

Make the eval verdict trustworthy, then make it pass: accuracy ≥ 0.92, health
detection ≥ 0.95, conditional times ≥ 0.80, with the failing cases understood
rather than fitted.

## Work done

1. **Threshold gate extracted and made fail-closed** —
   `backend/app/evals/thresholds.py` reads `evals/thresholds.yaml` (single
   source of truth, both directions: `*_min` and `*_max`), and treats an
   unmapped key, an unknown metric or a non-numeric value as a **violation**
   instead of a silent pass. `evals/runner.py` uses it and the duplicate
   hardcoded table is gone.
2. **Context forwarded** — `_build_prompt` renders `pending_confirmation` and any
   remaining non-empty context key, with a credential-name filter so a secret can
   never be rendered into a prompt.
3. **Prompt v2** (`backend/app/agent/prompts/interpreter_v2.md`) — an explicit
   procedure: read the context first, then classify by what is pending
   (`[pending_offers]` → offer intents, `[pending_confirmation]` → absence
   confirmation, nothing pending → a fresh message), with numeric replies
   (`1`/`2`) meaning yes/no **only** when something is pending, a broader health
   rule (any symptom, malaise or medical reference), and worked examples for the
   confusions v1 produced. The active version is named once
   (`interpreter.PROMPT_VERSION`) and recorded on every interpretation, so a
   quality change is always attributable to a prompt version.

## Evidence (real model, `gpt-4o-mini`, 150 golden samples)

| Prompt | Intent accuracy | Health | Conditional times | Avg latency | Avg cost | Verdict |
|---|---|---|---|---|---|---|
| `interpreter_v1` (run 1) | 0.86 | 0.9167 | 0.95 | 1051 ms | $0.000211 | 2 violations, printed "Thresholds met." (gate broken) |
| `interpreter_v1` (run 2) | 0.84 | 0.9167 | 0.90 | — | — | same, plus run-to-run spread |
| **`interpreter_v2`** | **0.9333** | **1.0** | **0.85** | 1047 ms | $0.000298 | **thresholds met, honestly** |
| Parser baseline (offline) | 0.3733 | 0.0 | 0.0 | — | — | informational floor |

- The gate fix is proven by feeding it the real v1 report: it returns exactly the
  two violations that were previously invisible.
- 10 failures remain, analysed rather than hidden (see below).
- `308 passed, 2 skipped`, ruff clean, mypy clean (54 files).

## Open follow-ups

1. **`OFFER_WITHDRAW` needs state, not wording.** Six of the ten remaining
   failures (`no puedo al final`, `imposible al final`, `tengo que cancelar`,
   `no podré ir`, `i need to cancel`) carry **the same context** as cases labelled
   `OFFER_DECLINE`: `{"pending_offers": ["offer_1"], ...}`. Only the phrase "al
   final" separates them, so matching the golden set there would be prompt
   overfitting. The real fix is in the product: when the employee cancels
   something already accepted, the orchestrator knows it — pass that marker
   (e.g. `[accepted_offer=offer_1]`) so the distinction is state.
2. **The `interpretation` table is never written.** `grep` over `app/` finds the
   model at `app/db/models.py:165` and no writer, so the "Agent decisions" screen
   has no real data source (it renders mock data). Persisting intent, confidence,
   model, prompt version, cost, latency and validation result — with the Langfuse
   trace link — is its own work unit.
