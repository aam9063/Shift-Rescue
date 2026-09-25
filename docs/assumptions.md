# Assumptions Log

Decisions made on unproven premises or under ambiguity, with the conservative
choice recorded (spec §0). Each entry should be validated before a real client
deployment.

## A1 — Typeface substitution (2026-09-24, frontend-foundation)

- **Premise:** DESIGN.md specifies the proprietary `SoDoSans` typeface, which
  is not publicly available.
- **Decision:** Use **Inter** (Google Fonts) as the substitute, per the
  substitution note in DESIGN.md §9, keeping the tight `-0.01em` tracking.
- **Where:** `frontend/index.html` (font load), `frontend/src/design/tokens.css`
  (`--font-sans`).
- **Validate:** With the client/design review — confirm Inter reads well at
  dashboard text sizes, or license a closer match if the brand requires it.

## A2 — Spacing anchor deviation (2026-09-24, frontend-foundation)

- **Premise:** DESIGN.md documents a rem scale anchored at `1rem = 10px`
  (the Starbucks `font-size: 62.5%` root trick).
- **Decision:** Keep the browser default `1rem = 16px` and preserve the
  DESIGN.md spacing values as absolute rem tokens (`--space-*`). Tailwind v4
  utilities are used with the token values directly; no root font-size hack.
- **Consequence:** Pixel parity with the documented scale holds; only the
  rem-to-px arithmetic differs from the original site.
- **Validate:** If pixel-exact porting of Starbucks-sourced metrics becomes a
  requirement, revisit the 62.5% root trick.

## A3 — Token contract testing approach (2026-09-24, frontend-foundation)

- **Premise:** jsdom + Tailwind v4 under vitest cannot compute styles for CSS
  custom properties reliably, and the Tailwind Vite plugin makes `?raw` CSS
  imports return empty strings in tests.
- **Decision:** Design tokens are locked by file-content contract tests
  (`tokens.test.ts` reads `tokens.css` from disk), plus component-level tests
  asserting utility class names on primitives.
- **Consequence:** Exact DESIGN.md values are enforced at test time without a
  browser; visual verification still requires the demo environment.

## A4 — Langfuse Cloud instead of self-hosted Langfuse (2026-09-24, deploy)

- **Instruction (user, late-breaking):** for the AWS EC2 deployment, use
  **Langfuse Cloud** (free tier) instead of self-hosting Langfuse. No
  Langfuse-owned Postgres/ClickHouse/Redis on the instance. Configure only
  `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` and
  `LANGFUSE_HOST=https://cloud.langfuse.com` (or the EU regional host) so the
  OpenTelemetry SDK exports traces directly.
- **Consequence:** `docker-compose.prod.yml` hosts only FastAPI, Celery
  worker, Celery beat, Redis (broker/locks) and Shift Rescue's own
  PostgreSQL. Instance sizing drops to **t3.large (2 vCPU, 8 GB)** — no
  t3.xlarge needed.
- **Where documented:** the deployment ADR (ADR-003, written with the
  `deploy-delivery` feature) must capture this decision and the savings vs
  self-hosting. The dev compose keeps Langfuse behind an optional profile as
  a local alternative only.
- **Spec amendment:** spec §9.1 said "Langfuse self-hosted"; amended by this
  instruction (spec §0 rule 5: scope changes update intent and tasks).
