# LocalLead — Backend (FastAPI)

Real backend for the LocalLead marketing site: auth, plans + Stripe billing,
Google Places lead discovery, a live website-audit engine, opportunity
scoring, a lead pipeline, and CSV export.

## Stack
- **FastAPI** + **SQLAlchemy 2** + **SQLite** (swap `DATABASE_URL` for Postgres)
- **PyJWT** auth (bcrypt-hashed passwords)
- **Google Places API (New)** for lead data
- **Stripe** subscriptions for Pro / Agency

## Run

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill in keys (see below)
uvicorn app.main:app --reload
```

Open http://localhost:8000 (serves the marketing site) and
http://localhost:8000/docs for the interactive API.

## Configuration (`.env`)
The server boots without keys, but:
- `/api/search` returns **503** until `GOOGLE_PLACES_API_KEY` is set
  (enable *Places API (New)* in Google Cloud).
- `/api/billing/checkout` returns **503** until Stripe keys + price IDs are set.

Check `/api/health` to see what's wired up.

## API

| Method | Path | Notes |
|---|---|---|
| POST | `/api/auth/signup` | → JWT |
| POST | `/api/auth/login` | → JWT |
| GET | `/api/auth/me` | current user + usage |
| POST | `/api/search` | `{category, city, limit}` → audited, scored, sorted leads (enforces plan limit) |
| GET | `/api/leads` | saved pipeline (optional `?status=`) |
| PATCH | `/api/leads/{id}` | update `status` / `notes` |
| DELETE | `/api/leads/{id}` | remove lead |
| GET | `/api/leads/export.csv` | CSV export |
| GET | `/api/billing/plans` | plan catalog |
| POST | `/api/billing/checkout` | `{plan}` → Stripe Checkout URL |
| POST | `/api/billing/webhook` | Stripe webhook (updates plan) |

All `/api/leads*`, `/api/search`, `/api/auth/me`, and checkout require
`Authorization: Bearer <token>`.

## How it works
- **Audit engine** (`services/audit.py`): fetches each lead's site and checks
  reachability, SSL validity/expiry, mobile viewport, load time, LocalBusiness
  schema, meta tags, maps embed, click-to-call, and review count — real network
  checks, no mock data.
- **Scoring** (`services/scoring.py`): weighted 0–100 opportunity score with
  per-path normalization (no-site / broken / live-but-weak) plus activity and
  rating bumps. Hot ≥ 80, warm ≥ 60.
- **Plan limits** (`usage.py`): Starter = 10 searches / 30-day period; Pro &
  Agency = unlimited. Period auto-resets.

## Roadmap (not yet built)
PDF audit reports, contact finder enrichment, new-lead alerts, CRM push.
