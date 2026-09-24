# Feature: WhatsApp real (`whatsapp-channel`)

Status: **in progress**
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

- [ ] AC1: Signature validation rejects forged/absent signatures and accepts
      valid ones (unit-tested with computed HMAC).
- [ ] AC2: Inbound webhook maps the sender phone → employee and triggers the
      orchestrator; duplicate MessageSid processed once (204).
- [ ] AC3: Status callback updates `Message.delivery_status`.
- [ ] AC4: `TwilioWhatsAppChannel.send` posts the correct form to Twilio and
      returns the provider message id (httpx MockTransport test).
- [ ] AC5: Sandbox setup guide written; DoD demo documented (2 real phones).
- [ ] AC6: Work-unit commits recorded.

## Tasks

- [ ] T1 — Signature validator + config + TwilioWhatsAppChannel (TDD).
- [ ] T2 — Webhook inbound/status endpoints wired to the orchestrator (TDD).
- [ ] T3 — Sandbox setup guide + verification with real phones (user-assisted).

## Verification evidence

(appended per task)

## Commits

(appended per commit)

## Progress / Next step

Next: T1.
