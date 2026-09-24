# Feature: Manager Dashboard (`manager-dashboard`)

Status: **slice 1 closed; slice 2 in progress** (Today screen closed; Rescue detail in progress)
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

Slice 1 (Today screen) complete; AC1-AC5 verified. Branch `feature/manager-dashboard` on top of `dev`.

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

- [ ] AC6: Rescue detail renders summary, ordered timeline, candidates with
      human-readable exclusion reasons (stable codes) and offers with status.
- [ ] AC7: Candidate ordering is deterministic (score desc, tie-break by id).
- [ ] AC8: Timeline events render chronologically with actor and English
      labels; no health details anywhere (spec §10).
- [ ] AC9: Back navigation works via state callback.
- [ ] AC10: All tests green, build and lint clean; commits recorded.
