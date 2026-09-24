# Feature: Frontend Foundation (`frontend-foundation`)

Status: **in progress**
Branch: `feature/frontend-foundation`
Created: 2026-09-24

## Objective

Scaffold the manager dashboard frontend as a Vite + React 19 + TypeScript project, with the
design system from `DESIGN.md` encoded as reusable design tokens (colors, typography, spacing,
radii, shadows) and a themed app shell. This is the frontend slice of spec Feature 0
(`foundation`), performed first because the user directed it.

## Problem / Why

Shift Rescue needs a manager dashboard (spec §7.6). Before screens exist, the project needs a
working frontend skeleton whose visual language matches `DESIGN.md` (Starbucks-inspired: warm
cream canvas, four-tier green system, pill buttons, 12px cards, tight tracking). Building
screens later without tokens would produce inconsistent styling.

## Scope

In scope:
- Vite + React 19 + TypeScript scaffold in `frontend/` (per spec §7.2 stack).
- Tailwind CSS v4 wired with `DESIGN.md` tokens (colors, fonts, spacing, radii, shadows).
- Font substitute: **Inter** for the proprietary SoDoSans (per DESIGN.md §9 note), documented
  in `docs/assumptions.md`.
- Minimal base UI primitives used by tests and future screens: pill `Button`, `Card`.
- Themed app shell page (header band placeholder + cream canvas).
- Vitest + React Testing Library wired as the TDD runner (`pnpm vitest run`).

Out of scope (later features):
- All nine dashboard screens (spec Feature 5 `manager-dashboard`).
- Backend, API client, WebSocket, auth, simulator.
- Deployment/CI for the frontend beyond making tests runnable.

## Constraints

- Technical artifacts (code, names, commits, docs) in English.
- TDD: RED observed before implementation for each behavior.
- Runner: `pnpm vitest run`.
- DESIGN.md is the single source of truth for visual style; it defines the *style*, not a
  Starbucks-like site. No gradients, no gold as general accent, cream canvas not white.
- ~400 changed lines per task is a heuristic, not a hard limit.

## Acceptance criteria

- [ ] AC1: `frontend/` builds with Vite; `pnpm build` succeeds with zero TS errors.
- [ ] AC2: `pnpm vitest run` runs as the test runner and all tests pass.
- [ ] AC3: Design tokens from DESIGN.md exist as Tailwind theme tokens / CSS variables
      (four greens, gold reserved, cream/ceramic surfaces, text alphas, red/yellow semantics,
      12px card radius, 50px pill radius, space scale, shadow stacks).
- [ ] AC4: App shell renders on the warm cream canvas (`#f2f0eb`) with Inter and tight
      tracking; a smoke test asserts the themed shell renders.
- [ ] AC5: `Button` renders full-pill with `scale(0.95)` active state (unit tested).
- [ ] AC6: Work-unit commits (Conventional Commits) recorded in this document as evidence.

## Tasks

- [ ] T1 — Repo setup: initial docs commit on `main`, feature branch
      `feature/frontend-foundation`, tooling check (node 24, pnpm 11).
- [ ] T2 — Scaffold Vite React-TS app in `frontend/`, install Tailwind, TanStack Query,
      vitest + RTL; first commit.
- [ ] T3 — Design tokens (TDD): write failing tests asserting token presence (CSS variables
      on the shell + Button pill/press behavior), then implement tokens in Tailwind theme and
      base components. Commit.
- [ ] T4 — App shell: header band + cream canvas, smoke test green, `pnpm build` clean.
      Commit. Document Inter substitution in `docs/assumptions.md`.

## Verification evidence

(appended per task)

## Progress / Next step

Next: T1.
