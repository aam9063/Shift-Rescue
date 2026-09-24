# Twilio WhatsApp sandbox — step-by-step setup

Everything **outside the code** you need to do, once, to run a real rescue
over WhatsApp. You need: a Twilio account and at least two phones.

> This is the sandbox flow (perfect for the demo). Production requires an
> approved WhatsApp sender and approved Content Templates — noted at the end.

## 1. Create the Twilio account

1. Go to <https://www.twilio.com/try-twilio> and sign up (free trial).
2. Verify your own email and phone number when prompted.
3. From the **Console home** (<https://console.twilio.com>), copy:
   - **Account SID** (starts with `AC…`)
   - **Auth Token**
   Keep them for step 5.

## 2. Activate the WhatsApp Sandbox

1. Console → **Messaging** → **Try it out** → **Send a WhatsApp message**
   (direct link: <https://console.twilio.com/us1/develop/sms/try-it-out/whatsapp-learn>).
2. You will see a sandbox number (usually `+1 415 523 8886`) and a join code
   like `join <two-random-words>`.
3. **From each demo phone** (at least two): open WhatsApp, start a chat with
   that sandbox number and send the join message exactly (e.g. `join happy-otter`).
   Twilio replies “You are all set”.
4. Note the sandbox number in `whatsapp:+14155238886` format — that is your
   `TWILIO_WHATSAPP_FROM`.

## 3. Expose your local API to the internet

Twilio must reach your machine. Two options:

**Option A — ngrok (development)**

```bash
# one-time: https://ngrok.com/download  (then `ngrok config add-authtoken <token>`)
ngrok http 8000
```

Copy the public URL, e.g. `https://abc123.ngrok-free.app`.

**Option B — deployed host** (the EC2 instance from ADR-003, once deployed):
use its public HTTPS URL.

## 4. Point the sandbox webhooks at your API

In Console → Messaging → Try it out → WhatsApp sandbox → **Sandbox settings**:

| Field | Value |
|---|---|
| “When a message comes in” | `https://<your-public-url>/webhooks/twilio/inbound` (HTTP **POST**) |
| “Status callback URL” | `https://<your-public-url>/webhooks/twilio/status` (POST) |

Save. (If you restart ngrok you get a new URL: update both fields.)

## 5. Configure the backend

In `backend/.env` (copy from `backend/env.example`; the dotted filename is gitignored):

```bash
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
TWILIO_VALIDATE_SIGNATURE=true
```

Then restart the API (`make up` or `make dev-backend`).

Signature validation is on: requests without a valid `X-Twilio-Signature`
are rejected with 403. Only disable it (`false`) for local debugging.

## 6. Make sure the demo employees exist with real numbers

The webhook maps the sender phone to an employee by `phone_e164`. Map your
two sandbox phones to seeded employees:

```bash
DEMO_REAL_PHONES="emp_09_floor=+34600111222|emp_10_floor=+34600333444" \
  uv run python -m app.db.seed_cli
```

Then run a real rescue:

1. From one phone, text the sandbox: *“me encuentro fatal, hoy no puedo ir”*.
2. The agent answers asking to confirm (SÍ/NO).
3. Reply **SÍ** → the second phone receives the offer; reply **SÍ** there.
4. You receive the confirmation and the manager gets the notice in the
   dashboard.

## Sandbox limitations (why the demo looks a bit odd)

- **24-hour session window**: you (the business) can only send free-form
  messages if the employee wrote to you in the last 24 h. Outside it, an
  approved **Content Template** is required (production concern; in the
  sandbox, everyone has just joined, so you are inside the window).
- **Trial prefix**: trial-account messages are prefixed with
  “Sent from your Twilio trial account”.
- **Joined numbers only**: Twilio only delivers to numbers that sent the join
  code. Re-join if you change sandbox code.
- Sandbox join codes expire periodically (~72 h of inactivity) — rejoin if
  messages stop arriving.

## Production checklist (not needed for the demo)

1. Buy/approve a WhatsApp sender (Meta business verification).
2. Create and get approval for each business-initiated template
   (the `offers` and `absence_ack` style messages).
3. Store `TWILIO_*` in SSM Parameter Store (never in the repo) and inject
   them into the EC2 containers (see the deployment ADR).
4. Keep `TWILIO_VALIDATE_SIGNATURE=true` always.
