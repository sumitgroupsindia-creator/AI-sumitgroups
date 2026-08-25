# ENVIRONMENT.md

Every variable the application reads, what it does, and how to obtain a value.

Copy `.env.example` to `.env` and fill it in. **Never commit `.env`** — it is gitignored, and only
`.env.example` (with empty placeholders) belongs in version control.

## Core

| Variable | Required | Default | Notes |
|---|---|---|---|
| `ENVIRONMENT` | no | `development` | `production` in deployment. Informational; used in logs. |
| `DEBUG` | no | `false` | **Must be `false` in production.** When true, FastAPI exposes `/api/docs`, `/api/redoc` and `/api/openapi.json`. |
| `FRONTEND_URL` | yes | `http://localhost:3000` | The single origin allowed by CORS, and the base for password-reset links. Set to `https://ai.sumitgroups.com`. |
| `BACKEND_URL` | no | `http://localhost:8000` | Informational; used when composing absolute URLs. |
| `NEXT_PUBLIC_API_URL` | yes (frontend) | `/api/v1` | Baked into the frontend **at build time**. Use `/api/v1` when the reverse proxy serves both on one origin. |

## Database (MySQL 8)

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | yes | `mysql+aiomysql://user:pass@host:3306/dbname?charset=utf8mb4`. The async driver prefix is required. |
| `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DATABASE` / `MYSQL_ROOT_PASSWORD` | yes (Docker) | Consumed by the `mysql` container to provision the database on first boot. |

The MySQL server must run at UTC (`--default-time-zone=+00:00`, already set in the compose files).
MySQL `DATETIME` carries no timezone, so the application stores naive UTC and relies on the server
being UTC for any SQL-side defaults.

## Redis

| Variable | Required | Default | Notes |
|---|---|---|---|
| `REDIS_URL` | yes | `redis://localhost:6379/0` | Rate limiting and caching. |
| `CELERY_BROKER_URL` | yes | `redis://localhost:6379/1` | Job queue. Use a different DB index from the cache. |
| `CELERY_RESULT_BACKEND` | yes | `redis://localhost:6379/2` | Task results. |

## Authentication

| Variable | Required | Default | Notes |
|---|---|---|---|
| `JWT_SECRET` | yes | — | **Generate a unique value per environment:** `openssl rand -hex 32`. Rotating it invalidates every existing session. |
| `JWT_ALGORITHM` | no | `HS256` | |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | no | `15` | Short by design; the client refreshes silently. |
| `REFRESH_TOKEN_EXPIRE_DAYS` | no | `7` | How long a user stays signed in without re-entering a password. |

## AI providers

These keys are read **only by the backend** and are never sent to the browser.

| Variable | Required | Default | Where to get it |
|---|---|---|---|
| `OPENAI_API_KEY` | yes | — | https://platform.openai.com/api-keys |
| `OPENAI_CHAT_MODEL` | no | `gpt-4o-mini` | Overridable per environment; the admin UI can also change the stored model. |
| `OPENAI_IMAGE_MODEL` | no | `gpt-image-1` | |
| `GEMINI_API_KEY` | yes | — | https://aistudio.google.com/apikey |
| `GEMINI_CHAT_MODEL` | no | `gemini-2.0-flash` | |
| `GEMINI_IMAGE_MODEL` | no | `gemini-2.5-flash-image` | |

Users never see these model names — see the model presentation section in the README.

## Payments

| Variable | Required | Default | Notes |
|---|---|---|---|
| `PAYMENT_PROVIDER` | no | `razorpay` | The only implemented provider. Stripe would be added behind the same `PaymentProvider` interface. |
| `RAZORPAY_KEY_ID` | yes for paid plans | — | Razorpay Dashboard → Settings → API Keys. The key **id** is public and reaches the browser; the secret never does. |
| `RAZORPAY_KEY_SECRET` | yes for paid plans | — | Backend only. |
| `RAZORPAY_WEBHOOK_SECRET` | yes for paid plans | — | Set when creating the webhook in the Razorpay dashboard. Webhooks whose HMAC-SHA256 signature does not match are rejected with 400. |

Point the Razorpay webhook at `https://ai.sumitgroups.com/api/v1/subscription/webhook` and subscribe to
`payment.captured`, `subscription.activated`, `subscription.charged` and `subscription.cancelled`.

## Storage

| Variable | Required | Default | Notes |
|---|---|---|---|
| `STORAGE_PATH` | yes | `./storage` | `/app/storage` inside containers, bind-mounted to `./storage` on the host. **Must be on a persistent volume** — images live here, not in the database. |
| `MAX_UPLOAD_MB` | no | `10` | Enforced server-side. Keep the reverse proxy body limit above this (Caddy/Nginx configs use 25MB). |
| `MAX_IMAGE_DIMENSION` | no | `4096` | Rejects decompression-bomb-shaped images. |
| `ALLOWED_UPLOAD_EXTENSIONS` | no | `jpg,jpeg,png,webp` | Extension allow-list; content is separately sniffed and must agree. |

## Email (password reset)

| Variable | Required | Default | Notes |
|---|---|---|---|
| `EMAIL_BACKEND` | no | `console` | `console` logs the email instead of sending — fine for development, **not** for production. Set to `smtp` in production. |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` | yes when `EMAIL_BACKEND=smtp` | port `587` | STARTTLS is used. |
| `SMTP_FROM` | no | `no-reply@sumitgroups.com` | Must be an address your SMTP provider permits. |

## Rate limiting

| Variable | Required | Default | Notes |
|---|---|---|---|
| `RATE_LIMIT_ENABLED` | no | `true` | Set `false` only in test runs. |
| `RATE_LIMIT_PER_MINUTE` | no | `60` | Per authenticated user on general API routes. |
| `AUTH_RATE_LIMIT_PER_MINUTE` | no | `10` | Per IP on login/register/forgot-password — brute-force protection. |

If Redis is unreachable the limiter **fails open** rather than taking the API down.

## Observability

| Variable | Required | Default | Notes |
|---|---|---|---|
| `LOG_LEVEL` | no | `INFO` | Logs are structured JSON; every line carries `request_id` and `user_id`. |
| `SENTRY_DSN` | no | — | Leave empty to disable error reporting. |

## Test-only

| Variable | Default | Notes |
|---|---|---|
| `TEST_DATABASE_URL` | `mysql+aiomysql://test:test@127.0.0.1:53306/ai_saas_test?charset=utf8mb4` | **Must point at a schema used only for tests** — the suite drops and recreates every table, so aiming it at a development database destroys that data. |

## Production checklist

- [ ] `DEBUG=false` and `ENVIRONMENT=production`
- [ ] `JWT_SECRET` freshly generated, not reused from another environment
- [ ] `FRONTEND_URL` exactly `https://ai.sumitgroups.com` (CORS depends on it)
- [ ] Database and Redis passwords changed from the `.env.example` placeholders
- [ ] `EMAIL_BACKEND=smtp` with working credentials, so password reset actually delivers
- [ ] `RAZORPAY_WEBHOOK_SECRET` set and the webhook registered in the Razorpay dashboard
- [ ] `./storage` on persistent, backed-up disk
- [ ] `.env` readable only by the deploying user (`chmod 600 .env`)
