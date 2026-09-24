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
2. The page has a **Sandbox Participants** panel with the authoritative data
   for YOUR account:
   - the sandbox **number** (the default US sandbox is `+1 415 523 8886`; some
     accounts get a region-specific number),
   - the **join code**, e.g. `join voice-favorite`,
   - the list of joined numbers.
   Take the number and the code from HERE — not from doc examples (a doc
   snippet showing `+4915888620339` is an illustration, not your sandbox).
3. **From each demo phone** (at least TWO — one reports the absence, the other
   may cover it): open WhatsApp, start a chat with that sandbox number and send
   the join message exactly as shown (e.g. `join voice-favorite`). Twilio replies
   “You are all set”. The panel then lists each joined number.

   > Trial accounts can only deliver to **joined** numbers, so with a single
   > phone you will see the absence flow but the offer to another employee will
   > never arrive.
4. Note the sandbox number in `whatsapp:+14155238886` format — that is your
   `TWILIO_WHATSAPP_FROM`.

## 3. Expose your local API to the internet (only for local testing)

Twilio has to POST to a public URL. Your laptop is not public, so **for local
testing** you need a tunnel; **when the demo is deployed on EC2** you skip this
and use the instance URL directly.

**Option A — cloudflared (no account needed, quickest)**

```bash
# one-time install: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
cloudflared tunnel --url http://localhost:8000
```

It prints a URL like `https://random-words.trycloudflare.com` — that is your
public base URL.

**Option B — ngrok**

```bash
# one-time: https://ngrok.com/download  (then `ngrok config add-authtoken <token>`)
ngrok http 8000
```

Prints a URL like `https://abc123.ngrok-free.app`.

**Option C — deployed EC2 host** (after the deployment feature): use
`https://<your-domain>` and ignore the tunnel entirely.

> Note: free tunnels get a NEW url every restart — if you restart it, redo
> step 4 with the new URL.

## 4. Point the sandbox webhooks at your API

In the Twilio Console, the WhatsApp sandbox page has the join QR/code on the
**Participants** side and the URL fields under **Sandbox settings**. Routes to
find it (any of these works):

- Direct link: <https://console.twilio.com/us1/develop/sms/settings/whatsapp-sandbox>
- Console → **Develop** → **Messaging** → **Try it out** → **Send a WhatsApp
  message** → tab **Sandbox settings**
- Console → **Messaging** → **Settings** → **WhatsApp Sandbox Settings**

| Field | Value |
|---|---|
| **When a message comes in** | `https://<your-public-url>/webhooks/twilio/inbound` (HTTP **POST**) |
| **Status callback URL** | `https://<your-public-url>/webhooks/twilio/status` (POST) |

Save. If the page has no such fields, your console version keeps them under
**Messaging → Settings → WhatsApp Sandbox Settings** (the same two boxes).

> If you restart the tunnel (cloudflared/ngrok) the URL changes: update both
> fields again.

## 5. Configure the backend

In `backend/.env` (copy from `backend/.env.example`; the real `.env` is gitignored):

```bash
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token
# Copy the number from the Console's "Sandbox Participants" panel.
# US default sandbox: +14155238886. Format: whatsapp:<number>, no spaces.
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
TWILIO_VALIDATE_SIGNATURE=true
```

`backend/.env` is already wired into the containers (`env_file` in
`infra/docker-compose.yml`), so recreate the stack to pick the values up:

```bash
make up      # or: docker compose -f infra/docker-compose.yml up -d
```

Check the API sees them:

```bash
docker compose -f infra/docker-compose.yml exec api uv run python -c   "from app.core.config import get_settings; s=get_settings(); print(bool(s.twilio_account_sid), s.twilio_whatsapp_from)"
```

Signature validation is on: requests without a valid `X-Twilio-Signature`
are rejected with 403. Only disable it (`false`) for local debugging.

## 6. Map your two real phones to seeded employees

The webhook finds the employee by phone (`employee.phone_e164`). The seed reads
`DEMO_REAL_PHONES`: up to 3 entries, `employee_id=phone` (or `full_name=phone`),
separated by `|`, phones in E.164 (with `+`, no spaces).

**a)** Open `backend/.env` and add the two phones that joined the sandbox — the
one that reports the absence and the one who may cover it:

```bash
DEMO_REAL_PHONES=emp_09_floor=+34600111222|emp_10_floor=+34600333444
```

**Suggested demo pair** (the seed starts the schedule on *today*, so these
roles always exist for a same-day demo):

- phone A → `emp_09_floor`: has today's floor **evening** shift (15:00–23:00)
  → this is the one that reports the absence.
- phone B → `emp_11_floor`: free that evening → this is the one who can cover.

```bash
DEMO_REAL_PHONES=emp_09_floor=+34600360794|emp_11_floor=+34600XXXXXX
```

Seeded floor employees are `emp_09_floor` … `emp_17_floor`. To list them all:

```bash
docker compose -f infra/docker-compose.yml exec postgres \
  psql -U shift_rescue -c "SELECT id, full_name FROM employee ORDER BY id;"
```

**b)** Recreate the stack (so the API picks up the new value) and re-seed:

```bash
make up
make seed
# equivalent of make seed:
# docker compose -f infra/docker-compose.yml exec api uv run python -m app.db.seed_cli
```

**c)** Verify the mapping landed:

```bash
docker compose -f infra/docker-compose.yml exec postgres \
  psql -U shift_rescue -c "SELECT id, full_name, phone_e164 FROM employee WHERE phone_e164 NOT LIKE '+34600000%' ORDER BY id;"
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

## Troubleshooting (real errors hit while wiring this up)

### Inbound reaches the API but nothing happens
Check the API logs and the DB:

```bash
docker compose -f infra/docker-compose.yml logs --since 10m api | grep -E "webhooks|TwilioChannelError|Traceback"
docker compose -f infra/docker-compose.yml exec postgres   psql -U shift_rescue -c "SELECT id, direction, provider_message_id, template_key FROM message ORDER BY created_at DESC LIMIT 5;"
```

- **No employee for that phone** → the webhook ignores unknown senders. Run the
  `DEMO_REAL_PHONES` mapping (step 6) and `make seed`.
- **No shift today for that employee** → the agent answers "out of scope". The
  seed starts the schedule on the day it runs, so re-run `make seed` on the
  demo day.

### `403 Forbidden` on `/webhooks/twilio/inbound`
Signature validation failed. Two causes:
1. `TWILIO_AUTH_TOKEN` does not match the account (verify with:
   `curl -u "$SID:$TOKEN" https://api.twilio.com/2010-04-01/Accounts/$SID.json`).
2. The app is behind a TLS proxy (cloudflared/ngrok/Caddy): Twilio signs the
   public `https://…` URL. The app reconstructs it from
   `X-Forwarded-Proto`/`X-Forwarded-Host` (see `app/api/webhooks_twilio.py`) and
   uvicorn runs with `--proxy-headers`.

### `21654 ContentSid Required` when sending
The `From` number is not the sandbox the employee messaged, so Twilio sees **no
open 24h session** and demands an approved template. An account can expose more
than one sandbox (legacy page vs new console) — the authoritative source is the
Twilio **message log**:

```bash
curl -s -u "$SID:$TOKEN" "https://api.twilio.com/2010-04-01/Accounts/$SID/Messages.json?PageSize=10" | python -c "import sys,json;[print(m['from'],'->',m['to'],m['status']) for m in json.load(sys.stdin)['messages']]"
```

Whatever number appears on the *inbound* line (`+34… -> whatsapp:<sandbox>`) is
the one that goes in `TWILIO_WHATSAPP_FROM`.

### Error `12300 Invalid Content-Type` on incoming messages
Twilio requires a `Content-Type` on every webhook response; without it the
Debugger reports a 502/12300. Our endpoints answer with empty TwiML
(`application/xml`).

### Trial account limits (expected, not bugs)
- Only **joined** numbers receive messages (others fail with 63016/63015).
- Business-initiated messages need approved templates; replies inside the 24h
  window are free-form.
- The sandbox session expires ~3 days after joining → rejoin with `join <code>`.
- Messages are prefixed with "Sent from your Twilio trial account".
