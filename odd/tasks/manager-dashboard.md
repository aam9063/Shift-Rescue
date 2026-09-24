# Feature: Manager Dashboard (`manager-dashboard`)

Status: **slices 1-3 closed; slice 4 in progress (UI redesign per user mockups)**
Branch: `feature/manager-dashboard`
Created: 2026-09-24

## Objective

Build the manager dashboard screens from spec §7.6 on top of the
`frontend-foundation` design tokens. Built screen by screen as slices
(auto-chain / stacked-to-main per the spec delivery strategy); each slice gets
its own PR-sized chain of commits.

## Problem / Why

The product demo (spec §1.2, §7.6) centers on the manager seeing shifts,
active rescues and approvals in real time. The first and central screen is
**Today**: shifts of the day by role with status, active rescues highlighted
with a countdown to their deadline.

## Scope

### Slice 1 — Today screen (current)

- `Shift` / `RescueCase` frontend domain types (mirroring spec §4.1).
- Mock data source behind a service interface (no backend yet; later slices
  swap the implementation for the REST API without touching components).
- `useTodayShifts` TanStack Query hook over the mock source.
- Pure grouping/formatting helpers (testable without React).
- `TodayScreen`: shifts grouped by role, status badges, active rescue banner
  with countdown to deadline.

Out of scope (later slices): rescue detail, approvals, ops, settings,
conversations, agent decisions, evals, WebSocket live updates, auth, router.

## Constraints

- UI text in English (spec §0 rule 1). TDD with `pnpm vitest run`, RED first.
- Visual style strictly from DESIGN.md tokens (cream canvas, white cards with
  12px radius and whisper shadows, greens by surface role, pill buttons).
- No backend assumptions: the mock source must be replaceable via an interface.
- Reuse `frontend-foundation` tokens and `Button`; no new visual language.

## Acceptance criteria (DoD slice 1)

- [x] AC1: Shift domain types + mock data exist behind a service interface;
      components never import the mock directly (they go through hooks).
- [x] AC2: Today screen renders the day's shifts grouped by role in order
      (kitchen, floor, bar, cleaning, supervisor) with role labels and times.
- [x] AC3: Each shift shows its status (`scheduled` | `absent` | `open` |
      `covered`) with distinct visual treatment per DESIGN.md semantics.
- [x] AC4: Active rescues are highlighted with a countdown to the deadline
      (minutes remaining, computed from injected clock — no `Date.now()` in
      domain/helpers).
- [x] AC5: All tests green (`pnpm vitest run`), `pnpm build` and `pnpm lint`
      clean; work-unit commits recorded below.

## Tasks

- [x] T1 — Domain types + mock data service + pure helpers (TDD: helpers RED
      first), then GREEN.
- [x] T2 — `useTodayShifts` query hook + `TodayScreen` with grouped shift
      cards and status badges (TDD), then GREEN.
- [x] T3 — Active rescue banner with countdown (TDD), then GREEN.
- [x] T4 — Verify all, update feature doc, work-unit commits.

## Verification evidence

- T1: RED (`6ab708c` tests failing on missing modules) → GREEN 28/28 → `07a4db4`.
- T2: RED (mock + screen suites failing on missing modules) → GREEN 35/35 → `704263e`. QueryClient test helper added (`renderWithProviders`).
- T3: RED (banner suite failing) → GREEN 40/40 → `86c996b`. Banner wired into TodayScreen; App shell renders TodayScreen; h1 always present.
- Final: `pnpm vitest run` 40/40; `pnpm build` clean; `pnpm lint` clean.

## Commits

- `6ab708c` test(frontend): RED contract tests for today-screen domain helpers and open manager-dashboard feature doc
- `07a4db4` feat(frontend): shift/rescue domain types and pure today-screen helpers (TDD)
- `704263e` feat(frontend): Today screen with role-grouped shift cards, status badges and mock data source (TDD)
- `86c996b` feat(frontend): active rescue banner with deadline countdown wired into Today screen (TDD)

## Progress / Next step

Slice 1 (Today) and slice 2 (Rescue detail) complete; AC1-AC10 verified. Branch
`feature/manager-dashboard` on top of `dev`. Merges are a user decision; the
agent only asks before pushing.

## Commits (slice 2)

- `ff998aa` feat(frontend): rescue detail domain types and pure helpers (TDD)
- `0911167` feat(frontend): mock rescue detail with timeline, scored candidates and offers
- `b3a7dd5` feat(frontend): Rescue detail screen with timeline, candidates and offers; state-based navigation from Today (TDD) (amended to include deadline countdown in summary)

Final verification slice 2: `pnpm vitest run` 55/55; `pnpm build` clean; `pnpm lint` clean.

## Commits (slice 3)

- `61e1e1e` feat(frontend): approval domain types and pure helpers (TDD)
- `c0d15dd` feat(frontend): mock pending approvals with in-memory decide mutation
- `382c7c2` feat(frontend): Approvals screen with approve/reject decisions and shell header navigation (TDD)

Final verification slice 3: `pnpm vitest run` 68/68; `pnpm build` clean; `pnpm lint` clean.

Next: slice 4 (UI redesign per user mockups) in progress.

## Slice 4 — UI redesign per user mockups (in progress)

User provided two mockups (`frontend/public/img/Hoy@1x.png`,
`Detalle del rescate@1x.png`), in Spanish; UI stays English. The current
list-based layout is rejected: Today becomes a kanban board and Rescue
detail becomes a two-column layout under a dark-green hero band.

### Design decisions (from mockups, mapped to DESIGN.md)

- Display headings switch to a serif face (DESIGN.md "Lander Tall" role):
  **Lora** substitute, documented in `docs/assumptions.md`.
- Dark House-Green full-width header band: clock logo, "Shift Rescue"
  wordmark, centered location pill, white pill CTA "+ Report absence".
- Today = 4-column kanban: Uncovered / Searching / Needs your approval /
  Covered today, with count badges and status-accented cards (green/gold
  top bars), big MM:SS countdowns (red when urgent).
- Floating circular "+" FAB bottom-right (DESIGN.md Frap treatment).
- Rescue detail: green hero band with back link, serif title, status pill
  ("Searching · wave 2 of 3"), giant MM:SS countdown; two-column body:
  agent timeline (colored dots, AI badge) + candidate cards with score and
  per-offer status, plus Excluded rows with stable reason codes.
- Deviation from mockup: an "Approvals" nav entry stays in the header
  (mockup has none, but the screen must remain reachable).

### Acceptance criteria (slice 4)

- [ ] AC16: Serif display face (Lora) wired as `--font-serif` and used on
      Today/Detail headings; countdowns render as MM:SS from injected clock.
- [ ] AC17: Shell header is the dark-green band with logo, location pill,
      + Report absence CTA and Approvals nav; FAB renders bottom-right.
- [ ] AC18: Today renders the 4 kanban columns derived by pure helpers
      (uncovered / seeking / needs approval / covered) with accented cards.
- [ ] AC19: Rescue detail renders the green hero band (back, serif title,
      wave pill, giant countdown) and the two-column timeline + candidates
      (+ Excluded) body.
- [ ] AC20: All tests green, build and lint clean; commits recorded.

## Slice 3 — Approvals screen (in progress)

Spec §7.6 screen 3: pending approvals inbox with approve/reject decisions.
Navigation grows to a state-based view switch in the shell header (Today /
Approvals); a router still deferred.

### Scope

- Frontend type `ApprovalRequest` (kind, status, decided_by/at) mirroring
  spec §4.1.
- Mock `getPendingApprovals()` plus `decideApproval(id, decision)` in-memory
  mutation; query invalidation keeps Today and Approvals consistent.
- Pure helpers: English kind/status labels, oldest-first ordering.
- `ApprovalsScreen`: pending inbox with context (employee, kind, rescue),
  Approve/Reject pill buttons, empty state.
- Shell header nav between Today and Approvals.

### Acceptance criteria (slice 3)

- [x] AC11: Approvals screen lists pending approvals oldest-first with kind
      labels, context and approve/reject actions.
- [x] AC12: Deciding an approval updates its status, removes it from the
      inbox and invalidates shared queries (rescue detail reflects it).
- [x] AC13: Empty state renders when no approvals are pending.
- [x] AC14: Shell header navigates Today <-> Approvals without a router.
- [x] AC15: All tests green, build and lint clean; commits recorded.

## Slice 2 — Rescue detail screen (in progress)

Spec §7.6 screen 2: detail view for one rescue with live timeline, candidates
with scores/exclusion reasons, and per-offer status. Navigation stays
state-based (selected rescue id lifted to `App`); a router lands when the
number of screens justifies it.

### Scope

- Frontend types for `AuditEvent`, `Offer`, candidate scoring result (mirrors
  spec §4.1).
- `DashboardDataSource.getRescueDetail(rescueId)` mock implementation with a
  realistic case (wave 1 sent, exclusions with stable reason codes).
- Pure helpers: chronological event sorting, event labels, deterministic
  candidate ordering (score desc, tie-break by employee id).
- `RescueDetailScreen`: summary, timeline, candidates table, offers list,
  back navigation (state-based). Approve/reject actions are rendered but
  wired in a later slice (needs mutations + approvals flow).

### Acceptance criteria (slice 2)

- [x] AC6: Rescue detail renders summary, ordered timeline, candidates with
      human-readable exclusion reasons (stable codes) and offers with status.
- [x] AC7: Candidate ordering is deterministic (score desc, tie-break by id).
- [x] AC8: Timeline events render chronologically with actor and English
      labels; no health details anywhere (spec §10).
- [x] AC9: Back navigation works via state callback.
- [x] AC10: All tests green, build and lint clean; commits recorded.
