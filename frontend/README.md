# Shift Rescue — Manager Dashboard

The manager-facing SPA for [Shift Rescue](../README.md): real-time visibility
of today's shifts and rescue cases, approvals, conversations, agent decisions
and evals. React 19 + TypeScript + Vite + Tailwind CSS v4 + TanStack Query.

![Today view](public/img/shift-rescue/dashboard.png)

## Quick start

Prerequisites: [Node 24](https://nodejs.org) and [pnpm 11](https://pnpm.io),
with the [backend stack](../README.md#quick-start) running on `:8000`.

```bash
pnpm install
pnpm dev        # → http://localhost:5173
```

### Offline mode (no backend)

The app has a data-source seam: by default it talks to the API, but with

```bash
VITE_USE_MOCK=true pnpm dev
```

it runs entirely on the mock fixture (`src/services/mock.ts`) — useful for
offline demos and UI work without the backend. Tests run hermetically the
same way (see [Testing](#testing)).

## Scripts

| Command | What it does |
|---|---|
| `pnpm dev` | Vite dev server on :5173, proxying `/api`, `/dev` and `/ws` to :8000 |
| `pnpm build` | Type-check (`tsc -b`) + production build |
| `pnpm test` | Vitest run (hermetic, mock data source) |
| `pnpm lint` | oxlint |

## Architecture

```
src/
├── screens/       one module per screen (state-based routing, hash deep links)
├── components/    shared UI (header, nav, dialogs, guards) + ui/ primitives
├── domain/        pure types and view logic, no I/O (mirrors backend entities)
├── services/      the data layer: data-source seam, API client, auth, live events
├── design/        design tokens (see DESIGN.md at the repo root)
└── test/          vitest setup and renderWithProviders helper
```

The layering rule is one-directional: **screens and components never import a
data source directly** — they consume hooks (`services/hooks.ts`), which read
from the single `dataSource` instance selected by the seam.

### Screens

One module per screen, matching the spec (§7.6): `TodayScreen`,
`RescueDetailScreen`, `ApprovalsScreen`, `ConversationsScreen`, `OpsScreen`,
`AgentDecisionsScreen`, `EvalsScreen`, `SettingsScreen`, `SimulatorScreen`,
plus `LoginScreen`. Routing is state-based with the current view in the URL
hash (so deep links survive the login round-trip); a real router lands when
the number of screens justifies it.

### Data source seam (`services/dataSource.ts`)

`getDataSource()` returns `ApiDashboardDataSource` or
`MockDashboardDataSource` depending on `VITE_USE_MOCK`. Both implement the
same `DashboardDataSource` interface, so screens are identical in both modes
and tests never touch the network.

### Live events (`services/liveEvents.ts`)

The dashboard subscribes to `WS /ws/locations/{id}` for real-time updates.
The socket **only tells screens what to refetch**: each event type maps to the
same TanStack Query keys the actions already invalidate, so nothing is
duplicated in the client cache. It degrades like the rest of the dashboard:
the connection state (`connecting | live | offline`) is rendered, never a
silent promise. A `4401` close code (see `app/api/ws.py`) clears the session
the same way a 401 does.

### Auth (`services/auth.ts`, `components/RequireAuth.tsx`)

Token-based session (spec §7.5): token + manager profile stored in
`localStorage` under one key, never logged. Any API call answering 401
dispatches `SESSION_EXPIRED_EVENT`, which clears the session and lets the
`RequireAuth` guard show the login. Role gating (`manager` vs `operator`)
hides Agent decisions and Evals from managers.

### Retry policy

Queries never replay client errors: a 403 (wrong role) or a 404 answers the
same however many times it is asked, so there is no retry storm in the
network tab. Transient failures (network, 5xx) still get two attempts.

## Design system

The visual theme (dark-green header band, warm cream canvas, gold accents)
is defined in [`DESIGN.md`](../DESIGN.md) at the repo root and implemented as
CSS custom properties in `src/design/tokens.css`. Fonts: Inter (UI) and Lora
(display headings). Every screen is usable from 360 px up — the responsive
contract lives in `DESIGN.md` §8.

## Testing

25 test files across screens, components, domain and services, with Vitest +
Testing Library. Tests are **hermetic**: the vitest environment forces
`VITE_USE_MOCK=true`, so no test touches the network or needs the backend.
Shared helpers live in `src/test/` (`renderWithProviders` wraps the app in
the query client and router context).

```bash
pnpm test
```

## Project docs

- [Root README](../README.md) — the product, quick start and deployment
- [System design](../docs/system-design.md) — the complete walkthrough
- [Specification](../docs/SHIFT_RESCUE_SPEC.md) §7.6 — the dashboard contract
