# Feature: responsive-dashboard

**Status**: in progress
**Branch**: `feature/dashboard-live`
**Spec references**: §7.6 (screens)
**Design system**: `DESIGN.md` §8 (Responsive Behavior, already written — this is a contract, not a suggestion)

## Problem

`DESIGN.md` §8 defines the responsive contract (breakpoints, collapsing
strategy, touch targets, gutters) and the dashboard violates it in ways that make
it unusable away from a desktop. The user reported the requirement as one they
had not specified; the design system already specifies it, so this is compliance
work, not new design.

Confirmed defects:

| # | Defect | Evidence |
| --- | --- | --- |
| 1 | **No navigation on a phone.** The main nav is `hidden md:flex` and the operator nav `hidden lg:flex`, with no alternative: below 768px the header shows only the wordmark, the avatar and logout. | `components/AppHeader.tsx` (lines ~86, ~98); `DESIGN.md` line 417 requires a **hamburger drawer below the tablet breakpoint** |
| 2 | **The Agent decisions table has eight columns** in a real `<table>` with no scroll container: it overflows horizontally on phones. | `screens/AgentDecisionsScreen.tsx` (line ~72) |
| 3 | **The conversations table** is a real `<table>` too, with no small-screen variant. | `screens/ConversationsScreen.tsx` (line ~35) |
| 4 | **Settings uses `grid-cols-2` with no breakpoint**, so two form columns are squeezed into a 375px viewport. | `screens/SettingsScreen.tsx` (lines ~103, ~135) |
| 5 | Touch targets: pill buttons are ~32px tall, below the 44px minimum `DESIGN.md` §8 requires on touch surfaces. | `DESIGN.md` §8 "Touch Targets" |
| 6 | Evals jumps from one column straight to five at `lg`, wasting tablet width. | `screens/EvalsScreen.tsx` (line ~39, `grid-cols-1 lg:grid-cols-5`) |
| 7 | The chart must be checked for scaling and for axis labels at 360px. | `components/LineChart.tsx` (`viewBox` set; the `<svg>` element's sizing was not verified) |

Already compliant (do not regress): the Today board (`grid-cols-1 md:grid-cols-2
xl:grid-cols-4`), the rescue detail (`max-w-[1200px]` + `grid-cols-1 md:grid-cols-2`),
conversations (`grid-cols-1 lg:grid-cols-3`), Ops (`grid-cols-1 md:grid-cols-2
xl:grid-cols-4`), the simulator (`grid-cols-1 md:grid-cols-2 xl:grid-cols-3`) and
the header's 1440px content cap.

## Goal

Every screen is usable on a phone (360–430px), comfortable on a tablet
(768–1023px) and unchanged on a desktop, following `DESIGN.md` §8 as the written
contract, with the CSS-class contract covered by tests and the visual result
verifiable at three widths.

## Decisions (fixed, do not re-litigate)

1. **`DESIGN.md` §8 is the contract.** Breakpoints as documented: xs < 480,
   mobile 480–767, tablet 768–1023, desktop 1024–1439, xlarge ≥ 1440. Tailwind's
   `sm/md/lg/xl` map onto them; do not invent new breakpoints or a second scale.
2. **The header gets a hamburger drawer below the tablet breakpoint**, exactly as
   the design system states: one button, an accessible panel with the same
   destinations (both the main and operator groups), visible focus, and the
   current view highlighted. Mobile-first, no JavaScript media queries: the
   button is `md:hidden` and the desktop navs keep their `hidden md:flex` /
   `hidden lg:flex` classes.
3. **Wide data becomes a list on small screens.** Tables keep their desktop
   rendering and gain a card variant shown below `md`, with the two variants
   rendered as CSS-controlled siblings (`md:hidden` / `hidden md:block`) so the
   tests can assert both exist. Every table container also gets `overflow-x-auto`
   as a safety net.
4. **Touch targets meet 44px on touch surfaces** — drawer items, primary and
   secondary actions, and the pill buttons in the screens' footers.
5. **Gutters follow the scale** 16 → 24 → 40px (`px-4` → `md:px-6` → `lg:px-10`),
   matching what the screens already do where they do it.
6. **No new visual language.** Same tokens, same typography, same components; only
   the arrangement changes with width.

## Tasks

### T1 — Mobile navigation (`components/AppHeader.tsx`)
A `md:hidden` menu button with `aria-expanded`/`aria-controls`, a panel listing
every destination (main nav plus the operator group, since both are hidden below
their breakpoints), the same active-view highlight as the desktop nav, closing on
selection and on `Escape`, with a focus state that is visible on the dark band.
Touch targets ≥ 44px. The signed-in manager and logout stay reachable on a phone.

### T2 — Screens at 360px
- `AgentDecisionsScreen`: card list below `md` (time, employee, intent,
  confidence, model, cost, latency, validation — the same data, stacked), table
  from `md` up, container `overflow-x-auto`.
- `ConversationsScreen`: the message table becomes cards below `md`.
- `SettingsScreen`: `grid-cols-1 md:grid-cols-2` (both places).
- `EvalsScreen`: `grid-cols-1 md:grid-cols-2 lg:grid-cols-5`.
- `LineChart`: the `<svg>` must scale to its container (fluid width, `h-auto`,
  `preserveAspectRatio` intact) and stay readable at 360px — fewer axis labels or
  a shorter height below `md` if needed.
- Audit every screen for horizontal overflow at 360px and for touch targets.

### T3 — Tests
jsdom cannot evaluate media queries, so test the **class and interaction
contract** instead, and say so in the test docstrings:
- The drawer: closed by default, opens on click, lists every destination, an
  active item is marked, `Escape` closes it, a navigation choice closes it. This
  is real interaction and must be tested for the phone path.
- The header keeps the desktop navs (assert the `hidden md:flex` /
  `hidden lg:flex` classes survive so the change cannot break desktop).
- The two wide tables render **both** variants, with the same row data, and the
  container carries `overflow-x-auto`.
- The settings grid and the Evals grid carry the expected responsive classes.
- A regression test for the shared Button/pill meeting the touch-target class.

### T4 — Documentation
- `DESIGN.md`: a short appendix noting which §8 rules the dashboard adopts and
  how (breakpoints, hamburger drawer below tablet, 44px touch targets, gutter
  scale), so the next slice has one place to look.
- `docs/runbook.md`: how to check responsiveness locally (DevTools at 360px,
  768px, 1024px, 1440px) with what to look for.
- Spec §7.6: one line recording that every screen must be usable from 360px up.
- This document's evidence.

### Parent visual verification (real browser, three widths)

Installed Playwright + Chromium **outside the project** (temp directory, no new
project dependency) and logged into the running stack as the demo manager,
capturing Today, Agent decisions and Operations at 360x820, 768x1024 and
1440x900, plus the navigation panel open, with `hasTouch` on so that
`pointer: coarse` matches (a desktop headless browser reports `fine`, which
would have faked a pass on every touch-target rule).

Automated result after the fixes:

```
OK: no overflow, every destination reachable, touch targets >= 44px
```

Covered by the script: `documentElement.scrollWidth` vs `clientWidth` at every
width, reachability of Approvals / Conversations / Operations / Agent decisions /
Evals, and the height of every visible `button`/`a` on the phone path.

### Two defects the automated pass found, and the third the eye found

| Finding | Fix |
| --- | --- |
| **The tablet range had no navigation at all.** Between 768 and 1023 px the main nav is visible, the operator nav is not (`hidden lg:flex`) and the hamburger was `md:hidden`, so *Ops*, *Agent decisions* and *Evals* were unreachable. The script proved it by timing out on the destination. | The button and the panel are `lg:hidden` (the drawer covers phones **and** tablets), with the test asserting `lg:hidden` and why |
| **Touch targets under 44px on a real touch device**: the wordmark (28 px), the *Demo simulator* pill (36 px) and *Log out* (20 px) — `pointer-coarse:` was already used elsewhere, these three were missed | `pointer-coarse:min-h-11` on all three |
| **Agent decisions rendered a blank page for a manager**: the endpoint is operator-only, so a 403 left an empty table that looked broken | The hook now surfaces the error and the screen explains it in plain English, with the generic message for other failures |

Also corrected while reviewing the screenshots: the drawer's visible group labels
were in Spanish (`PRINCIPAL`, `OPERADOR`) and one `aria-label` was `Menú`.
`scripts/sweep_spanish_ui.py` flagged none of them — its word list missed them —
so it now also flags any literal containing an accented vowel or an enye, which
is a language signal that needs no dictionary. Verified: the sweep reports only
the 11 intentional WhatsApp fixtures and three employee names (accented by rule).

Reviewed and left alone: the Today board, the rescue detail, Approvals and the
Simulator already reflow correctly at 360 px; Operations renders real metrics
(`Cost today`, `p95 2546ms`, `target < 2.5s`) with the chart scaling.

## Acceptance criteria

1. On a 360–430px viewport every screen is reachable and usable, with navigation
   available from the header.
2. No screen scrolls horizontally at 360px.
3. Touch targets on the phone path are ≥ 44px tall.
4. Desktop (≥ 1024px) looks and behaves exactly as before.
5. `pnpm vitest run`, `pnpm build`, `pnpm lint` and `npx tsc --noEmit` clean, with
   the pre-existing 124 tests still green.
6. The visual result is confirmed at 360px, 768px and 1440px (screenshots or a
   human click-through — recorded in the evidence).

## Verification evidence

**T1 — Mobile navigation.** `components/AppHeader.tsx`: `md:hidden` hamburger
(`aria-expanded`, `aria-controls="mobile-nav-panel"`, `aria-label` that flips
between "Open menu"/"Close menu"), `size-11` (44px) button, panel with every
destination from both groups under `Principal` / `Operador` headings, gold
active bar + gold focus ring on the House Green band, closes on `Escape`
(window listener) and on navigate, manager name/role + logout in the panel
footer. Header container `h-16` -> `min-h-16` (wraps when the drawer opens;
desktop still renders a single 64px row). Desktop navs untouched
(`hidden md:flex` / `hidden lg:flex`).

**T2 — Screens at 360px.**

- `AgentDecisionsScreen`: card list (`md:hidden`) with time, employee, intent,
  confidence bar, model, cost, latency and validation; table wrapped in
  `hidden md:block overflow-x-auto`; filter pills `pointer-coarse:min-h-11`.
- `ConversationsScreen`: card list (`md:hidden`) with employee, intent,
  last message and rescue label, tappable to open the chat; table in
  `hidden md:block overflow-x-auto`.
- `SettingsScreen`: both grids `grid-cols-1 md:grid-cols-2`; the pause toggle
  and the ranking-weight buttons got invisible pseudo-element hit areas
  (`after:-inset-2.5` / `after:-inset-[19px]`) so the 28px/6px controls meet
  the 44px floor without changing their look.
- `EvalsScreen`: `grid-cols-1 md:grid-cols-2 lg:grid-cols-5`.
- `LineChart`: `<svg>` now `h-auto w-full` with explicit
  `preserveAspectRatio="xMidYMid meet"`, so it scales fluidly from the 560x160
  viewBox (no more fixed `h-40` letterboxing at 360px). No axis labels exist,
  only the two figcaption captions, which stay readable.
- `ui/Button`: `pointer-coarse:min-h-11` in the base classes — 44px on touch
  surfaces, desktop look unchanged.

**Audit result per screen (360px + touch targets):**

- `TodayScreen`: grid already `grid-cols-1 md:grid-cols-2 xl:grid-cols-4`, no
  overflow; fixed only the "Review approval" pill touch target.
- `RescueDetailScreen`: hero and content gutters already `px-4 md:px-10`,
  `max-w-[1200px]`, `grid-cols-1 md:grid-cols-2`, no overflow; fixed the
  "Back to Today" text button touch target (`pointer-coarse:min-h-11` +
  inline-flex).
- `ApprovalsScreen`: single-column list, no overflow; fixed the
  Reject/Approve pill touch targets.
- `OpsScreen`: already `grid-cols-1 sm:grid-cols-2 xl:grid-cols-4`; no buttons
  below target; nothing to change.
- `SimulatorScreen`: grid already responsive; fixed the 36px send button
  (`pointer-coarse:size-11`) and the clock/scenario pills.
- No screen introduces a fixed-width element wider than 360px; the only
  remaining horizontal-scroll risk (the two wide tables) is covered by the
  card variants plus `overflow-x-auto`.

**T3 — Tests.** All new/updated tests state in their docstrings that jsdom
evaluates no media queries and pin the class/interaction contract:

- `components/MobileNav.test.tsx` (new): drawer closed by default, a11y
  wiring, lists all 7 destinations from both groups, gold active indicator,
  `Escape` closes, navigate closes, manager+logout reachable from the panel,
  touch-target classes on the hamburger and every drawer item.
- `components/AppHeader.test.tsx`: desktop-safety test asserting
  `hidden md:flex` / `hidden lg:flex` survive.
- `screens/AgentDecisionsScreen.test.tsx`, `screens/ConversationsScreen.test.tsx`
  (new): both variants render, identical row data, container
  `overflow-x-auto`; plus card-list selection and filter-pill touch targets.
- `screens/SettingsScreen.test.tsx`: both grids carry
  `grid-cols-1 md:grid-cols-2`.
- `screens/EvalsScreen.test.tsx` (new): grid carries
  `grid-cols-1 md:grid-cols-2 lg:grid-cols-5`.
- `components/ui/Button.test.tsx`: regression for the touch-target class
  (`pointer-coarse:min-h-11`, and no unconditional `min-h-11`).

**T4 — Documentation.** `DESIGN.md` got "Appendix A. Dashboard adoption of
the responsive contract" (breakpoints, drawer, card siblings, touch targets,
gutter scale); `docs/runbook.md` got a "Check responsiveness" subsection under
Smoke test (360/768/1024/1440 and what to look for); spec §7.6 got the one-line
360px usability requirement.

**Checks (observed output):**

1. `cd frontend && pnpm vitest run` — `Test Files  22 passed (22)` /
   `Tests  141 passed (141)` (was 124 tests before this task).
2. `cd frontend && pnpm build` — `dist/assets/index-CS6-ZnlK.css 28.24 kB`,
   `dist/assets/index-DIepw9xL.js 321.71 kB`, `✓ built in 161ms`.
3. `cd frontend && pnpm lint` — oxlint exits 0 with no findings.
4. `cd frontend && npx tsc --noEmit -p tsconfig.app.json` — clean, no output.
5. `cd frontend && grep -rhoE "(sm|md|lg|xl):[a-z-]+" src/screens src/components
   | sort | uniq -c | sort -rn | head -12`:

   ```
     11 md:hidden
      9 md:grid-cols-
      7 md:block
      4 md:px-
      4 md:flex
      4 lg:grid-cols-
      4 lg:flex
      4 lg:col-span-
      3 xl:grid-cols-
      2 md:text-
      2 md:gap-
      1 xl:block
   ```

   (The pattern stops at digits, so counts like `md:grid-cols-` are truncated
   prefixes; the touch-target classes use the `pointer-coarse:` variant, which
   this grep does not cover. `pointer-coarse:min-h-11` is confirmed present in
   the built CSS: `@media (pointer:coarse)` appears in the bundle.)

**Deviation:** `screens/AgentDecisionsScreen.test.tsx`,
`screens/ConversationsScreen.test.tsx` and `screens/EvalsScreen.test.tsx` are
new test files not listed in the allowed edit surfaces; T3 required their
assertions and the repo convention is co-located screen tests
(`OpsScreen.test.tsx` etc.). Everything else stayed inside the listed surfaces.

**Not verified here:** the visual result at 360px / 768px / 1440px (jsdom
cannot evaluate media queries) — left for the parent's screenshot pass,
per acceptance criterion 6.
