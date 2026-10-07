# Laxmi Saree House — WhatsApp Orders backend

WhatsApp-first ordering for the storefront. Customers tap **Order on WhatsApp**
on a product, and this FastAPI service — driven by **Interakt** (WhatsApp) and
**PhonePe** (payments) — walks them through quantity → address → payment.

```
Storefront (Next.js) ──wa.me deep link (Ref: #slug)──▶ WhatsApp
                                                          │
                                              Interakt webhook
                                                          ▼
                                   ┌──────────  FastAPI  ──────────┐
                                   │  catalog (Sanity)             │
                                   │  conversation state machine   │
                                   │  interakt (send messages)     │
                                   │  phonepe (create/verify pay)  │
                                   └───────────────────────────────┘
                                                          ▲
                                              PhonePe webhook
```

## Run locally

```bash
cd backend
python -m venv .venv && source .venv/Scripts/activate   # Windows Git Bash
pip install -r requirements.txt
cp .env.example .env            # then fill in the values
uvicorn app.main:app --reload   # http://localhost:8000  (/health, /docs)
```

Webhooks must be reachable from the internet. In dev, tunnel localhost and set
`PUBLIC_BASE_URL` to the tunnel URL:

```bash
ngrok http 8000     # or: cloudflared tunnel --url http://localhost:8000
```

## Configure the providers

**Interakt** (app.interakt.ai → Settings → Developer Setup)
- Copy the API key into `INTERAKT_API_KEY`.
- Set the incoming-message webhook to `<PUBLIC_BASE_URL>/webhooks/interakt`.
- `WHATSAPP_BUSINESS_NUMBER` = the number customers message (digits, e.g. `9199...`).

**PhonePe** (business.phonepe.com → Developer Settings)
- Set `PHONEPE_MERCHANT_ID`, `PHONEPE_SALT_KEY`, `PHONEPE_SALT_INDEX`.
- Sandbox host is the default; switch `PHONEPE_BASE_URL` to the prod host to go live.
- No dashboard webhook config needed — the callback URL is sent per-payment.

**Sanity** — reuses the storefront's project. Copy `SANITY_API_READ_TOKEN` from
`jewellery/.env.local`.

## Two things to verify before go-live

Both are isolated to one spot each, marked with `# VERIFY` in the code:

1. **Interakt session-text payload** (`app/interakt.py → send_text`) — confirm the
   exact request body for free-form messages against your Interakt API docs.
   Without a key set, the bot logs replies to stdout so you can test the flow.
2. **PhonePe credentials** (`.env`) — the X-VERIFY flow in `app/phonepe.py` is
   stable; you only need real merchant credentials.

## Flow (state machine — `app/conversation.py`)

| State | Trigger | Next |
|---|---|---|
| any | message contains `#slug` | look up product, ask quantity |
| `awaiting_qty` | a number | add to cart, show cart |
| `cart_review` | "pay" | ask for address |
| `awaiting_address` | address text | create PhonePe payment, send link |
| `awaiting_payment` | PhonePe webhook | mark paid, send confirmation |

State is one row per phone in SQLite (`orders.db`). Point `DATABASE_URL` at
Postgres for production — no code change.
