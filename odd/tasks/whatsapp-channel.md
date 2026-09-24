# Feature: WhatsApp real (`whatsapp-channel`)

Status: **code complete; real-phone demo pending user setup**
Branch: `feature/whatsapp-channel` (stacked on `feature/evals-observability`)
Created: 2026-09-24

## Objective

Deliver spec Feature 6: `TwilioWhatsAppChannel` (real outbound via Twilio REST),
webhook inbound with signature validation, status callbacks, and the sandbox
setup guide. DoD: a complete rescue works with at least two real phones joined
to the Twilio sandbox.

## Scope

- `app/channels/twilio_whatsapp.py`: `TwilioWhatsAppChannel` implementing the
  `Channel` protocol via Twilio REST API (httpx, Basic auth); Twilio signature
  validator (HMAC-SHA1 per Twilio spec).
- `app/api/webhooks.py`: `POST /webhooks/twilio/inbound` (validate signature →
  map From phone → employee → orchestrator.handle_inbound; 204 fast) and
  `POST /webhooks/twilio/status` (delivery_status update by MessageSid).
- Config: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`,
  `TWILIO_VALIDATE_SIGNATURE`.
- `docs/twilio-sandbox-setup.md`: step-by-step account/sandbox/ngrok guide.
- Sandbox constraint documented: messages only within the 24h session window
  unless approved templates; trial prefix notice.

Out of scope: approved Content Templates production flow (documented), voice,
media messages.

## Acceptance criteria

- [x] AC1: Signature validation rejects forged/absent signatures and accepts
      valid ones (unit-tested with computed HMAC).
- [x] AC2: Inbound webhook maps the sender phone → employee and triggers the
      orchestrator; duplicate MessageSid processed once (204).
- [x] AC3: Status callback updates `Message.delivery_status`.
- [x] AC4: `TwilioWhatsAppChannel.send` posts the correct form to Twilio and
      returns the provider message id (httpx MockTransport test).
- [x] AC5: Sandbox setup guide written; DoD demo documented (2 real phones).
- [x] AC6: Work-unit commits recorded.

## Tasks

- [x] T1 — Signature validator + config + TwilioWhatsAppChannel (TDD).
- [x] T2 — Webhook inbound/status endpoints wired to the orchestrator (TDD).
- [x] T3 — Sandbox guide written (docs/twilio-sandbox-setup.md); live 2-phone run pending user setup.

## Verification evidence

- T1: 7 tests RED to GREEN (signature validator + channel via httpx MockTransport).
- T2: 7 tests RED to GREEN (inbound routing, 403 forged, unknown sender ignored, status update); FastAPI Depends wiring; router mounted.
- T3: docs/twilio-sandbox-setup.md + backend/env.example with every spec section 12 variable.
- Full suite: 203 passed; ruff + mypy strict clean.

## Commits

- 1f84ce2 feat(backend): Twilio WhatsApp channel with signature-validated webhooks, status callbacks and sandbox setup guide (TDD)

## Commits

(appended per commit)

## Progress / Next step

Next: T1.
