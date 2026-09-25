# Demo video script (2–3 minutes)

**Format:** split screen — left: the employee's phone (WhatsApp); right: the
manager dashboard. Recorded against the deployed demo.

**Cast (seeded, all fictional):** Iker Mendoza (`emp_09_floor`, the absent
employee), Marta López (`emp_13_floor`, the covering employee), Javier Prado
(the manager account).

---

## 0:00–0:20 · The problem (voiceover over the dashboard)

> "When someone calls in sick in a restaurant, it is almost always less than two
> hours before their shift, by WhatsApp, to the manager — who is in the middle
> of service. Covering that gap costs them 30 to 60 minutes of messages and
> calls, and they don't know who is available, who has already closed the night
> before, or who is close to their hour limit."

## 0:20–0:45 · The absence arrives

- **Left (phone, Iker):** send `me encuentro fatal, hoy no puedo ir`.
- **Voiceover:** "The agent asks for an explicit confirmation — it never opens a
  rescue by guessing — and it never asks why."
- **Left:** the agent replies asking to confirm.

## 0:45–1:05 · The rescue opens (dashboard)

- **Right:** refresh **Today**. The shift moves into the **Searching** column
  with a live countdown; the manager already has a notice.
- **Voiceover:** "The absent shift is marked in the HR system, the manager is
  notified, and the eligibility engine filters candidates: role, overlap,
  minimum rest, weekly hour caps, recent coverages."

## 1:05–1:30 · The offer reaches a real phone

- **Left (phone, Iker):** reply `SÍ`.
- **Left (phone, Marta):** the offer arrives: *"Hola Marta López, soy el
  asistente de turnos… ¿Puedes cubrirlo?"*
- **Voiceover:** "Offers go out in waves of three, ranking by fairness,
  proximity and preference — never by how often someone has said yes before."

## 1:30–2:00 · Acceptance and coverage

- **Left (phone, Marta):** reply `SÍ` → she receives the confirmation.
- **Right:** the card moves to **Covered today**, showing who covered it; open
  **Rescue detail** to show the live timeline.
- *(Optional, if recording a conditional acceptance: show the gold
  "Review approval" card → **Approvals** → Approve → the case becomes
  partially covered.)*

## 2:00–2:25 · The agent is observable and measurable

- **Right:** **Agent decisions** — every interpretation with intent,
  confidence bar, model, cost, latency and validation result.
- **Right:** **Operations** — LLM cost, p95 latency, low-confidence rate, stuck
  rescues and active alerts.
- **Voiceover:** "The LLM only interprets language and drafts replies: every
  output is validated, has no ability to assign anything, and one trace per
  rescue lands in Langfuse."

## 2:25–3:00 · Evals and closing

- **Right:** **Evals** — intent accuracy against the threshold, per-scenario
  results and the invariants counter: **0 violations**.
- **Voiceover over the architecture slide:** "FastAPI, Celery and PostgreSQL
  run the deterministic core; React shows the manager the truth; the WhatsApp
  channel is Twilio. The seven invariants — one person per shift, no offers to
  ineligible staff, no assignment without approval, no messages during quiet
  hours, one offer per person, full audit trail, and no health details leaving
  the conversation — are enforced by code and checked by an evaluation suite
  that runs on CI."

---

### Recording checklist

1. Deploy the demo and confirm `https://<domain>/health` is OK.
2. Have both phones joined to the Twilio sandbox (`join <code>`).
3. Reset the day: `make seed` on the instance so today has shifts.
4. Close any pending approvals from previous takes.
5. Record at 1080p, browser zoom 100 %, both windows side by side.
6. Keep the countdown visible — it is the strongest visual proof of urgency.
