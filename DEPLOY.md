# Deployment guide — Railway (backend + DB) + Vercel (frontend)

Fast and low-cost: backend and Postgres live in the **same Railway project and
region** (sub-millisecond DB hop, no cold starts). Frontend on Vercel's global CDN.

Deploy in this order — each step's config needs the previous one's URL:

```
1. Railway Postgres   → DATABASE_URL
2. Railway backend    → needs DATABASE_URL; gives the API URL
3. Vercel frontend    → needs the API URL
4. Back to Railway    → set CORS_ORIGINS to the frontend URL
```

---

## 1 + 2. Railway — Postgres AND backend (same project)

Push the `backend/` folder to a Git repo first.

1. Go to https://railway.app → **New Project**.
2. **Add Postgres:** New → **Database → PostgreSQL**. Railway provisions it and
   exposes a `DATABASE_URL` variable on that service. Pick the **Singapore**
   region (Project Settings → Region) — closest low-cost region to India.
3. **Add the backend:** New → **GitHub Repo** → pick your backend repo. Railway
   detects the `Dockerfile` (and `railway.toml`) automatically. Put it in the
   **same region** as the database.
4. **Wire the DB into the backend.** On the backend service → **Variables** →
   add a variable referencing the Postgres service:
   ```
   DATABASE_URL = ${{Postgres.DATABASE_URL}}
   ```
   (Railway's URL is `postgresql://…`; the backend auto-rewrites it to the
   psycopg driver — no manual editing needed.)
5. **Add the rest of the variables** on the backend service:
   | Key | Value |
   |---|---|
   | `WHATSAPP_BUSINESS_NUMBER` | your Interakt number (digits) |
   | `INTERAKT_API_KEY` | from Interakt Developer Setup |
   | `SANITY_PROJECT_ID` | `o2pv6j02` |
   | `SANITY_DATASET` | `production` |
   | `SANITY_API_VERSION` | `2026-06-01` |
   | `SANITY_API_READ_TOKEN` | from `jewellery/.env.local` |
   | `PHONEPE_BASE_URL` | sandbox or prod host |
   | `PHONEPE_MERCHANT_ID` / `PHONEPE_SALT_KEY` / `PHONEPE_SALT_INDEX` | from PhonePe |
   | `PUBLIC_BASE_URL` | set after step 6 |
   | `CORS_ORIGINS` | set after the frontend is live (step 4) |
6. **Generate a public URL:** backend service → Settings → Networking →
   **Generate Domain**. You get e.g. `https://laxmi-whatsapp-api.up.railway.app`.
   Set `PUBLIC_BASE_URL` to that exact URL and redeploy.
7. **Verify:** open `https://…up.railway.app/health` → `{"status":"ok"}`.
   Tables are created automatically on first boot.
8. **Register the webhook** in Interakt → Developer Setup → Webhooks:
   ```
   https://laxmi-whatsapp-api.up.railway.app/webhooks/interakt
   ```

> Cost: Railway Hobby is usage-based (starts with free credit). A small FastAPI
> service + small Postgres typically runs ~$5/mo, always on — no sleep.

---

## 3. Vercel — frontend

1. https://vercel.com → **New Project** → import the `jewellery` repo → Root
   Directory `jewellery`. Framework: **Next.js** (auto-detected).
2. **Environment Variables:**
   | Key | Value |
   |---|---|
   | `NEXT_PUBLIC_API_BASE_URL` | your Railway URL from step 6 |
   | `NEXT_PUBLIC_WHATSAPP_NUMBER` | same number as the backend |
   | `NEXT_PUBLIC_SANITY_PROJECT_ID` | `o2pv6j02` |
   | `NEXT_PUBLIC_SANITY_DATASET` | `production` |
   | `NEXT_PUBLIC_SANITY_API_VERSION` | `2026-06-01` |
   | `SANITY_API_READ_TOKEN` | server-only read token |
3. Deploy → you get `https://laxmi-saree-house.vercel.app`.

---

## 4. Close the loop — CORS

The Vercel site calls the Railway API cross-origin, so allow it:

1. Railway → backend service → Variables:
   ```
   CORS_ORIGINS = https://laxmi-saree-house.vercel.app
   ```
2. Redeploy.

Done: real phone → WhatsApp → Interakt → Railway backend → Railway Postgres, and
the Vercel site → Railway API for login — all live, all fast.

---

## Cost summary

| | Cost |
|---|---|
| Railway (backend + Postgres, Singapore) | ~$5/mo, always on |
| Vercel (frontend) | Free (Hobby) |

To go even closer to India later, the backend + Postgres can move to Fly.io /
Supabase in **Mumbai** — but Railway Singapore is the simplest fast+cheap start.
