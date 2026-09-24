# ADR-002: Strands without the autonomous loop; LLM at the edges, domain in charge

Status: accepted
Date: 2026-09-24
Deciders: FDE + product owner
Related: spec §6, §5.4, ADR-001

## Context

The Strands Agents SDK is designed around a model-driven agent loop: the LLM
reasons, picks tools and iterates until a goal is met. Shift Rescue needs the
SDK's model abstraction, structured output, hooks and native OpenTelemetry —
but the rescue flow itself is a deterministic state machine whose transitions
carry legal weight (one shift, one person; no assignment without manager
approval; no offers during quiet hours).

An LLM in the loop with tools that mutate state would put invariant-critical
decisions behind probabilistic behavior, and the preassembled harness brings
capabilities (web search, fetch) that only widen the attack surface.

## Decision

1. **No autonomous loop.** The state machine (`app/domain/state_machine.py`)
   is the only orchestrator of rescue transitions. Strands `Agent` is used
   exclusively as a single-shot structured-output call:
   `Agent(model=..., system_prompt=..., structured_output_model=Interpretation,
   callback_handler=None)` with **no tools attached**.
2. **LLM at three acotated edges** (spec §6): message interpretation,
   in-session reply composition, escalation summaries. Interpretation is the
   only one wired in this feature; the other two arrive later with the same
   pattern.
3. **Every output validated.** `MessageInterpreter` re-validates with Pydantic
   (`app/agent/schemas.py`), retries once including the validation error, and
   falls back to `UNCLEAR` on repeated failure or provider outage. The
   orchestrator treats UNCLEAR as a clarification request, never an action.
4. **Deterministic parser is the degraded fallback.** When the circuit breaker
   opens (provider down) or no interpreter is configured, the Feature 2
   parser keeps the system fully functional (`spec §9.3`).
5. **Version pinning.** `strands-agents==1.56.0` pinned exactly; before using
   any new Strands API, its behavior is verified against that version's
   official docs — never from memory (spec §0 rule 6).
6. **No behavioral profiling.** The interpreter sees the message and minimal
   context (pending offers, next-48h shifts). Response history or acceptance
   rates never feed prompts or ranking (spec §5.2, EU AI Act exposure).

## Consequences

- Provider swaps (Anthropic direct, Bedrock, OpenAI-compatible endpoints such
  as NaN) are configuration: the `Agent` takes a `model`. The per-piece model
  comparison arrives with `evals-observability` (`make eval-models`).
- Cost and latency per interpretation are captured by `StrandsLLMClient`
  (`last_usage`) and exported as trace attributes (`rescue_id`,
  `prompt_version`) via Strands' native OpenTelemetry.
- The golden-set eval gate (`intent accuracy ≥ 0.92`, `health detection ≥
  0.95`) only blocks CI when a real model is evaluated; the deterministic
  parser baseline is informational.
- Prompts are versioned files (`app/agent/prompts/interpreter_v1.md`); the
  version is stored with every `Interpretation` for reproducibility.
