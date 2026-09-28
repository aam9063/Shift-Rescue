# Demo walkthrough — from an absence to a manager decision

A newcomer-friendly walkthrough of the demo: what each screen is for, how to
produce a rescue from the Simulator, how a case moves through its states, and
what the manager does when a case escalates. Deploy and access instructions,
credentials and troubleshooting live in `docs/runbook.md` — this page is the
tour, not the ops manual.

**Cast (seeded, all fictional):** Iker Mendoza (a floor employee), Marta López
(a candidate), Demo Manager (`manager@laterraza.demo`, the account you log in
with). All data is demo data at "La Terraza del Puerto".

---

## 1. What each screen is for

| Screen | Purpose |
|---|---|
| **Today** | The manager's home. One row per shift of the day with its live state: Uncovered, Searching, Needs approval, Escalated, or Covered, plus the active-rescue counter and a countdown while something is pending. |
| **Simulator** | Employee phones. You write as any employee; the message travels the same pipeline as a real WhatsApp message. This is where every demo rescue starts. |
| **Approvals** | The inbox of conditional acceptances (overtime, partial coverage) that need a manager decision. |
| **Rescue detail** | Everything about one case: the agent's timeline ("What the agent did"), the candidates and what each answered, and the manager actions (approve/reject, Close case). |
| **Agent decisions** (operator) | Every LLM interpretation with intent, confidence, model, cost and latency. |
| **Operations** (operator) | LLM cost, p95 latency, low-confidence rate, stuck rescues and alerts. |
| **Evals** (operator) | Intent accuracy and the invariant checks. |
| **Settings** | Pause the agent, quiet hours, wave configuration. |

## 2. Before you start

1. Deploy and smoke-test per `docs/runbook.md` §3–4: `api`, `worker`, `beat`,
   `redis` and `postgres` must all be up. The worker is what makes the agent
   reply — without it nothing below happens.
2. Log in to the dashboard with the demo manager account.
3. **Reset the demo clock** (Simulator → *Reset clock*) until it reads
   *on real time*. A leftover offset silently moves "now" for the whole worker.
4. Open **Simulator**. Each frame is labelled with the employee's situation
   against the current time — *On shift now*, *Starts at HH:MM*, *Ended at
   HH:MM*, *No shift today*. Only an *On shift now* employee can report an
   absence; the agent correctly answers "out of scope" to anyone else.

## 3. Produce a rescue from the Simulator (about a minute)

1. Pick an *On shift now* frame and type the absence, e.g.
   `me encuentro fatal, hoy no puedo ir`. Send it. The message enters the real
   pipeline (the API enqueues the same task a Twilio webhook would).
2. **The agent takes ~10 seconds to reply** (worker + LLM). The frame shows
   *"the agent is replying…"* and blocks duplicate sends; when the answer
   lands it appears in the thread by itself — no reload — and the Today board
   refreshes.
3. The agent asks for an explicit confirmation: reply `SÍ` in the same frame,
   **and do it promptly**. ⏱️ The confirmation has a deadline: for a shift that
   has *already started* you have **10 minutes** (spec §5.3: `start − 30 min`, or
   `opened + 10 min` when that has already passed). If the answer arrives later
   the rescue has already escalated to the manager — the agent will then explain
   that instead of confirming, which is correct but makes a confusing demo. For a
   calmer walkthrough pick an employee whose shift *starts later* (the frame says
   *Starts at HH:MM*): the window runs until half an hour before that shift.
4. On confirmation the rescue opens: the shift is marked absent in the HR
   system, the manager gets a notice, and the first wave of offers goes out.

## 4. How the case moves through its states

Watch the shift's row on **Today** (cards on a phone, table from tablet up):

| State | What it means | What the row shows |
|---|---|---|
| **Searching** | Offers are out, waiting for answers. | Live countdown, wave number. |
| **Needs approval** | A candidate accepted conditionally (overtime or partial coverage). | Countdown on the approval window plus a *Review approval* button. |
| **Covered** | Someone took the shift. | The covered employee; no countdown — nothing is pending. |
| **Escalated** | The deadline passed (or candidates ran out) and the manager was notified. | *Escalated at HH:MM* and a summary of who was contacted and what each answered — never "Uncovered". |

Each state change is one click away from the full story: *View detail* opens
the rescue detail with the agent timeline and the candidates.

**Skip the waiting:** the demo clock (Simulator, *+10 min* / *+1h*) moves the
shared virtual time, so deadlines and escalations happen in seconds. Broker
timers keep their real-time ETA — the Simulator says so in one line.

**A late acceptance is not lost.** When a case escalates, the offers that are
still open **stay open on purpose** (spec §5: *aceptación después del escalado*).
If a candidate finally answers `SÍ`, the case comes back as an approval request
for the manager instead of being silently dropped — a good beat to show after
the escalation: the system gives up on the deadline, never on the shift.

## 5. What the manager does when a case escalates

The escalation is where the manager takes over — the system did its best and
is honest about it:

1. **Find it on Today.** The row reads **Escalated** with *Escalated at HH:MM*
   and the §6.4-style summary of what the agent already tried, e.g.
   `Contacted: Marta L. (no reply yet), Ivan R. (declined).` No health
   details, ever — who was contacted and what each answered is all it says.
2. **Open the detail** (*View detail*). Read the timeline and the candidate
   list to see exactly what happened and what options remain.
3. **Resolve it outside the system** — a quick call, or a fix in the rota.
   The detail screen says exactly that: the manager resolves, the system
   records it.
4. **Close the case from the detail screen**: press **Close case**, confirm,
   and the write is queued (202) — the board updates a moment later when the
   worker applies it. The row stops reading Escalated and the active-rescue
   counter drops.

Optional, and the best proof that nothing is lost: before closing, go back to the
Simulator and have a candidate whose offer is still open answer `SÍ`. The case
returns to the manager as an **approval request** (spec §5), so a shift can still
be covered after the deadline — the agent stops waiting, the manager decides.

Answering late is not a dead end: if the employee writes after the case closed,
the agent tells them the outcome (it escalated, it was covered, or the manager
closed it) and — since every reply is stored in the thread — it shows up in
**Conversations** as well as on their phone.

If instead a case is **awaiting approval** (a conditional acceptance), the
manager acts right on the detail screen: **Approve** or **Reject** inline, and
the case moves on without leaving the page.

## 6. Recording checklist (for the 2–3 minute video)

1. Both windows side by side: Simulator (left) and Today (right), 1080p,
   browser zoom 100 %.
2. Reset the demo clock and reseed if yesterday's data is stale (runbook §5).
3. Walk §3 → §4 → §5 of this page in order; the countdown while Searching and
   the Escalated summary are the two shots worth holding on.
4. Finish with the manager close — it is the proof the loop ends with a human
   decision, not a timeout.
