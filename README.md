# ai.sumitgroups.com

A ChatGPT-style AI platform where **one prompt runs through two AI models simultaneously** and the
results are shown side by side for comparison.

> **One Prompt. Multiple AI Models. Better Results.**

## What it does

- **Streaming chat** with conversation history, stop-generation, regenerate, rename and delete
- **Side-by-side image generation** — a single prompt is dispatched to two providers concurrently and
  each result renders independently, so a fast model never waits on a slow one and a failed model
  never hides a successful one
- **Photo upload** — bring your own JPG/PNG/WEBP and use it as the generation input
- **Credits and usage tracking** — one wallet where **1 credit = ₹1**, spent on chat and images
  alike; every AI operation is metered and failed operations are refunded in full
- **Subscriptions** via Razorpay, with plans and limits driven entirely from the database
- **Editable master prompts** — the assistant's identity and house style live in the database; a
  router picks the writing style that fits each request, and an attached photo is read before
  anything is generated from it
- **Per-operation margin** — admins record what each provider bills us and what to charge on top,
  and see revenue, cost and profit per slot
- **Admin dashboard** for users, plans, pricing, model enable/disable and failure inspection

## Tech stack

| Layer | Choice |
|---|---|
| Frontend | Next.js 15 (App Router), React 19, TypeScript, Tailwind CSS, shadcn/ui-style components |
| Backend | Python 3.11, FastAPI, SQLAlchemy 2 (async), Alembic |
| Database | MySQL 8 |
| Cache / queue | Redis 7, Celery |
| AI | OpenAI + Google Gemini, behind a provider abstraction |
| Payments | Razorpay, behind a `PaymentProvider` abstraction (Stripe is additive) |
| Storage | Local filesystem, behind a `StorageProvider` abstraction (S3/GCS are additive) |
| Deployment | Docker Compose + Caddy (automatic HTTPS); Nginx config also provided |

## Model presentation

The product deliberately **never shows vendor names to end users**. Customers see neutral, product-owned
slots:

| Slot | Tier | Backed by |
|---|---|---|
| Model 1 | Standard | configured in `provider_configs` |
| Model 2 | Premium | configured in `provider_configs` |

This is enforced in two places, not just in the UI copy:

- `frontend/lib/model-labels.ts` is the single source of truth for customer-facing labels
- user-facing API responses omit vendor model ids entirely, and clients cannot choose a model —
  it is always resolved server-side from `provider_configs`

Admin screens and `/api/v1/admin/*` do show real providers and model ids, since that is what an
administrator configures. `backend/tests/test_white_labeling.py` locks this contract in place.

## Quick start (local, without Docker)

Requires Python 3.11+, Node 20+, pnpm, and running MySQL 8 + Redis.

```bash
cp .env.example .env    # then fill in OPENAI_API_KEY, GEMINI_API_KEY, JWT_SECRET, DB creds
```

Set `ADMIN_EMAIL` and `ADMIN_PASSWORD` too and that account is created as an administrator on
first boot. There is no built-in default admin: a credential shipped in this repository would be
a credential every deployment shares. Once the account exists its password is left alone, so
rotating it in the app is not undone by the next restart.

Backend:

```bash
cd backend && python -m venv .venv && source .venv/bin/activate && pip install -r requirements-dev.txt
```

```bash
cd backend && alembic upgrade head && uvicorn app.main:app --reload
```

Worker (separate terminal):

```bash
cd backend && source .venv/bin/activate && celery -A app.workers.celery_app worker --loglevel=info
```

Frontend (separate terminal):

```bash
cd frontend && pnpm install && pnpm dev
```

The app is then at http://localhost:3000 with the API at http://localhost:8000.

## Quick start (Docker)

```bash
docker compose -f docker-compose.dev.yml up --build
```

For production deployment to `ai.sumitgroups.com`, see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Tests

Backend (needs a MySQL schema dedicated to tests — it drops and recreates every table):

```bash
cd backend && source .venv/bin/activate && pytest -q
```

Frontend type check and build:

```bash
cd frontend && pnpm typecheck && pnpm build
```

## Documentation

| Document | Contents |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System design, the decisions behind it, and the gaps they close |
| [docs/API.md](docs/API.md) | Every endpoint, with request/response shapes and error codes |
| [docs/DATABASE.md](docs/DATABASE.md) | Schema, relationships, indexes and the isolation model |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Production deployment, TLS, backups, upgrades |
| [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md) | Every environment variable and how to obtain its value |

## Project layout

```
backend/     FastAPI app, Alembic migrations, Celery workers, tests
frontend/    Next.js app, feature modules, API service layer
storage/     Persistent image storage (bind-mounted into containers)
deploy/      Caddy and Nginx reverse-proxy configuration
docs/        API, database, deployment and environment reference
```

## Security posture

- JWT access/refresh authentication with bcrypt password hashing
- Every user-scoped query filters by the authenticated user; cross-user access returns 404, never 403,
  so the API does not confirm that another user's resource exists
- Private files are served only through ownership-checked endpoints; on-disk names are server-generated
  UUIDs, so client filenames can never influence a path
- Uploads are size/dimension/extension checked, content-sniffed, and re-encoded to strip embedded payloads
- Redis-backed rate limiting, security headers, CORS locked to the frontend origin
- Provider API keys exist only in backend environment variables and are never sent to the browser
- Errors return a generic message plus a `request_id`; stack traces and provider errors stay in the logs
