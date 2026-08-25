# ARCHITECTURE.md — ai.sumitgroups.com

## 1. Product summary

A ChatGPT-style SaaS: users sign up, subscribe, chat with a streaming LLM, and generate images from a
single prompt across **OpenAI** and **Google Gemini** simultaneously, comparing results side by side
("Model 1" / "Model 2"). Credits gate usage; Razorpay handles billing (Stripe added later behind the
same interface).

## 2. Gaps in the brief and the decisions made to close them

The brief is very complete but leaves some implementation-level choices open. Rather than block on
these, the following production-grade defaults are adopted. All are isolated behind config/interfaces
so they can be changed later without a rewrite.

| Gap | Decision | Rationale |
|---|---|---|
| Chat transport | **SSE** (`text/event-stream`) via a `POST /api/v1/chat/stream` endpoint, not WebSockets | Simpler infra behind a reverse proxy, works with HTTP/1.1 & 2, easy to cancel client-side (AbortController), no extra socket server |
| OpenAI chat model | `gpt-4o-mini` default, configurable per plan via `provider_configs` | Cost/latency balance; swappable without code change |
| OpenAI image model | `gpt-image-1` (edits endpoint used when an input photo is supplied) | Current OpenAI image-gen API; supports both text→image and image edits |
| Gemini image model | `gemini-2.5-flash-image` (aka "nano-banana") via `google-genai` SDK | Current Gemini model with native image generation + image-conditioned generation |
| Gemini chat model | `gemini-2.0-flash` | Fast, cheap, good default |
| Password reset delivery | Pluggable `EmailSender` interface; concrete `SMTPEmailSender` reading `SMTP_*` env vars; a `ConsoleEmailSender` for dev | Brief asks for "forgot password architecture" — needs a real send path, but SMTP creds are user-supplied later |
| OAuth | Not implemented in v1, but `auth_provider`/`provider_user_id` columns + a `AuthProvider` service abstraction are in place so Google/GitHub OAuth is additive | "Keep OAuth extensible" |
| Rate limiting | Redis-backed sliding-window limiter (`app/middleware/rate_limit.py`), applied per-user and per-IP | Redis already required for Celery; avoids extra infra |
| Background jobs | Celery + Redis broker/result-backend. Chat streaming runs in-request (needs the live connection); image generation, thumbnailing, and webhook post-processing run as Celery tasks | Matches "Celery/background workers where required" |
| Reverse proxy / HTTPS | **Caddy** by default (automatic Let's Encrypt for `ai.sumitgroups.com`), Nginx config also provided as an alternative | Caddy needs near-zero TLS config for a self-hosted single domain; Nginx variant included for teams that standardize on it |
| Admin auth | Reuses the normal JWT auth; an `is_admin` boolean on `users` gates `/api/v1/admin/*` and the `/admin` frontend route group | No separate admin app needed at this scale |
| Currency / region | INR as primary currency (Razorpay-native), `plans.currency` column so USD/other plans can be added | Matches Razorpay-first requirement |
| Credit costs | Configurable per operation in `provider_configs`/`plans` tables, not hard-coded. Seed defaults: chat message = 1 credit / 1k tokens (rounded up), image generation = 10 credits per provider per image | Brief explicitly forbids hard-coding pricing/limits |
| File size/dimension limits | Configurable via env (`MAX_UPLOAD_MB=10`, `MAX_IMAGE_DIMENSION=4096`), enforced server-side with Pillow | "Validate size/dimensions" |
| Idempotency | `Idempotency-Key` header supported on `POST /images/generate*` and the Razorpay webhook; stored in `idempotency_keys` table | Prevents double-charging credits/webhook replay |
| Testing frameworks | Backend: `pytest` + `pytest-asyncio` + `httpx.AsyncClient` against a test Postgres schema. Frontend: `vitest` + `@testing-library/react` for units, `playwright` for one critical e2e (signup→chat→image) | Standard, well-supported choices |
| Package managers | Backend: `pip`/`poetry`-style `pyproject.toml`. Frontend: `pnpm` | pnpm is fastest for Docker layer caching |

## 3. High-level architecture

```
                         ┌─────────────────────┐
                         │   Caddy / Nginx      │  TLS termination, ai.sumitgroups.com
                         └──────────┬───────────┘
                    ┌───────────────┼────────────────┐
                    │                                 │
             /  /login /chat ...                 /api/v1/*
                    │                                 │
           ┌────────▼────────┐               ┌────────▼─────────┐
           │  Next.js 15      │  REST + SSE   │   FastAPI          │
           │  (frontend svc)  │◄─────────────►│   (backend svc)    │
           └──────────────────┘               └───────┬────────────┘
                                                        │
                     ┌──────────────────────────────────┼───────────────────────────┐
                     │                                   │                            │
             ┌───────▼───────┐                  ┌────────▼────────┐         ┌─────────▼────────┐
             │ PostgreSQL    │                  │ Redis            │         │ storage/ volume   │
             │ (SQLAlchemy + │                  │ (cache, queue,   │         │ (uploaded/generated│
             │  Alembic)     │                  │  rate-limit,     │         │  images, local FS) │
             └───────────────┘                  │  celery broker)  │         └────────────────────┘
                                                 └────────┬─────────┘
                                                          │
                                                 ┌────────▼─────────┐
                                                 │ Celery worker(s)  │──► OpenAI API
                                                 │ (image gen,       │──► Gemini API
                                                 │  thumbnails,      │──► Razorpay API
                                                 │  webhook jobs)    │
                                                 └────────────────────┘
```

## 4. Backend module layout

```
backend/app/
├── main.py                 FastAPI app factory, router mounting, middleware, startup/shutdown
├── api/v1/
│   ├── auth.py              register/login/logout/refresh/forgot/reset/me
│   ├── chat.py              POST /chat/stream, GET/DELETE conversations
│   ├── images.py            generate, generate-with-upload, list, get, regenerate
│   ├── files.py             authenticated file serving GET /files/{file_id}
│   ├── subscription.py      plans, checkout, webhook, current subscription
│   ├── credits.py           GET /credits, GET /usage
│   ├── admin.py             admin CRUD + stats
│   └── health.py            /health /ready
├── core/
│   ├── config.py            pydantic Settings (env-driven, no secrets hard-coded)
│   ├── security.py          password hashing (bcrypt), JWT issue/verify
│   ├── logging.py           structured JSON logging w/ request_id context var
│   └── deps.py              get_db, get_current_user, get_admin_user, get_redis
├── models/                  SQLAlchemy ORM models (one file per table group)
├── schemas/                 Pydantic request/response schemas
├── providers/
│   ├── base.py              AIProvider / ChatProvider / ImageProvider ABCs
│   ├── openai_provider.py
│   ├── gemini_provider.py
│   └── registry.py          provider lookup by name, enable/disable via provider_configs
├── services/
│   ├── auth_service.py
│   ├── chat_service.py       orchestrates streaming, saves messages
│   ├── image_service.py      orchestrates concurrent multi-provider generation
│   ├── credit_service.py     atomic debit/credit, prevents negative balance
│   ├── storage/
│   │   ├── base.py           StorageProvider ABC
│   │   └── local_storage.py  LocalStorageProvider
│   ├── payment/
│   │   ├── base.py           PaymentProvider ABC (checkout, verify_webhook, cancel)
│   │   └── razorpay_provider.py
│   └── email_service.py
├── repositories/            DB access per aggregate (keeps services thin & testable)
├── workers/                 celery_app.py + tasks (image_tasks.py, webhook_tasks.py)
├── middleware/              rate_limit.py, request_id.py, security_headers.py, error_handler.py
└── utils/                   file_validation.py, image_processing.py, idempotency.py
```

### Provider abstraction (core requirement)

```python
class ChatProvider(ABC):
    name: str
    async def stream_chat(self, messages, model, **kw) -> AsyncIterator[str]: ...

class ImageProvider(ABC):
    name: str
    async def generate_image(self, prompt, input_image=None, **kw) -> ImageResult: ...

class OpenAIProvider(ChatProvider, ImageProvider): ...
class GeminiProvider(ChatProvider, ImageProvider): ...
```

`image_service.generate_both()` fires `asyncio.gather(*, return_exceptions=True)` across the two
providers so one failing/slow provider never blocks the other; each result is persisted and streamed
back to the frontend as soon as it resolves (via two independent promises client-side, not a single
blocking call — see §6).

## 5. Database schema (summary — full DDL in DATABASE.md)

All PKs are UUID (`gen_random_uuid()`). All tables have `created_at`/`updated_at`. Every user-owned
row carries `user_id` with an FK + index, and every read path filters by
`WHERE user_id = :current_user_id` at the repository layer (never trusted from client input) — this is
the mechanism that guarantees cross-user isolation and is covered by dedicated security tests.

`users, plans, subscriptions, credits, usage_records, conversations, messages, generation_requests,
generation_results, uploaded_files, generated_images, provider_configs, idempotency_keys,
password_resets`

## 6. Image generation flow (detailed)

1. Frontend `POST /api/v1/images/generate` `{ prompt, providers: ["openai","gemini"], upload_file_id? }`
2. Backend: auth → validate request → check credits ≥ cost×providers → create `generation_requests` row
   (status `pending`) → create one `generation_results` row per provider (status `pending`) → return the
   request id + result ids immediately (202-style response) so the UI can render two loading cards.
3. Backend kicks off Celery task `run_generation(request_id)` which does
   `asyncio.gather(openai_job, gemini_job, return_exceptions=True)`.
4. Frontend polls `GET /images/{id}` (or subscribes via SSE `GET /images/{id}/stream`) — each
   `generation_results` row flips to `completed`/`failed` independently, so Model 1 can render while
   Model 2 still spins, and a Model 2 failure still shows Model 1.
5. On success: image bytes saved via `LocalStorageProvider` under `storage/images/generated/{uuid}.png`,
   a thumbnail generated, credits debited transactionally (`SELECT ... FOR UPDATE` on the credits row),
   `usage_records` row written.
6. Regenerate = same flow with the same prompt/input, new `generation_results` row, linked to the
   original request via `parent_result_id`.

## 7. Security model

- JWT access token (15 min) + refresh token (7 days, httpOnly cookie), rotation on refresh.
- Passwords: bcrypt via `passlib`.
- All `/api/v1/*` except `/auth/*`, `/health`, `/ready` require a valid access token.
- Ownership check helper `assert_owns(resource, user)` used in every service method that loads a
  user-scoped row — 404 (not 403) is returned on mismatch to avoid leaking existence.
- File serving never trusts client-provided paths: `GET /files/{file_id}` looks up the DB row by UUID,
  checks `owner_id == current_user.id`, then streams from the resolved on-disk path — the filename on
  disk is always a server-generated UUID, original filenames are stored as metadata only (never used to
  build a path) → eliminates path traversal.
- Uploads validated by: extension allow-list, real MIME sniffing (`python-magic`/Pillow open), max size,
  max pixel dimensions, re-encoded on save (strips EXIF/embedded payloads).
- Rate limiting: Redis sliding window, per-user for authenticated routes, per-IP for `/auth/*`.
- CORS locked to `FRONTEND_URL`. Security headers middleware (HSTS, X-Content-Type-Options,
  X-Frame-Options, CSP). No stack traces or provider errors ever reach the client — a generic
  `{ error, request_id }` body is returned and the detail is logged server-side.
- Provider API keys live only in backend env; never referenced from any frontend code path.

## 8. Implementation phases (this session)

1. ✅ Project skeleton + this document
2. Database models + Alembic migration
3. Core config/security/logging + auth endpoints
4. Provider abstraction (OpenAI + Gemini)
5. Storage abstraction + file endpoints
6. Chat (streaming) service + endpoints
7. Image generation (parallel) service + endpoints
8. Credit system
9. Subscription/Razorpay (abstract `PaymentProvider`)
10. Admin endpoints
11. Middleware/security/observability wiring + `main.py`
12. Frontend scaffold (Next.js 15, Tailwind, shadcn) + API client
13. Frontend pages (marketing, auth, chat, images, pricing, settings, admin)
14. Docker + Compose + reverse proxy
15. Backend tests (auth, isolation, credits, providers, upload)
16. Docs (README/API/DATABASE/DEPLOYMENT/ENVIRONMENT)

Each phase is committed independently so progress is inspectable and revertible.
