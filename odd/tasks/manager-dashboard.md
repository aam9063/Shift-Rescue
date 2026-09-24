# Feature: Manager Dashboard (`manager-dashboard`)

Status: **in progress**
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

- [ ] AC1: Shift domain types + mock data exist behind a service interface;
      components never import the mock directly (they go through hooks).
- [ ] AC2: Today screen renders the day's shifts grouped by role in order
      (kitchen, floor, bar, cleaning, supervisor) with role labels and times.
- [ ] AC3: Each shift shows its status (`scheduled` | `absent` | `open` |
      `covered`) with distinct visual treatment per DESIGN.md semantics.
- [ ] AC4: Active rescues are highlighted with a countdown to the deadline
      (minutes remaining, computed from injected clock — no `Date.now()` in
      domain/helpers).
- [ ] AC5: All tests green (`pnpm vitest run`), `pnpm build` and `pnpm lint`
      clean; work-unit commits recorded below.

## Tasks

- [ ] T1 — Domain types + mock data service + pure helpers (TDD: helpers RED
      first), then GREEN.
- [ ] T2 — `useTodayShifts` query hook + `TodayScreen` with grouped shift
      cards and status badges (TDD), then GREEN.
- [ ] T3 — Active rescue banner with countdown (TDD), then GREEN.
- [ ] T4 — Verify all, update feature doc, work-unit commits.

## Verification evidence

(appended per task)

## Commits

(appended per commit)

## Progress / Next step

Next: T1.
