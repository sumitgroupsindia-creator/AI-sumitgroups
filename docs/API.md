# API.md

Base URL: `https://ai.sumitgroups.com/api/v1`

All endpoints except `/auth/*`, `/subscription/plans`, `/subscription/webhook`, `/health` and `/ready`
require `Authorization: Bearer <access_token>`.

## Conventions

**Errors** always return the same shape — never a stack trace, never a raw provider message:

```json
{ "error": "Human-readable message", "request_id": "6f1c…" }
```

Quote the `request_id` when reporting a problem; it appears on every structured log line for that request.

| Status | Meaning |
|---|---|
| 400 | Invalid input (bad provider, failed file validation) |
| 401 | Missing, malformed or expired access token |
| 402 | Insufficient credits |
| 403 | Authenticated but not an admin |
| 404 | Not found **or not yours** — the API never confirms another user's resource exists |
| 422 | Request body failed schema validation |
| 429 | Rate limited; a `Retry-After` header is included |
| 500 | Unexpected server error |

**Model slots.** `provider` (`openai` \| `gemini`) is an opaque slot key used to address Model 1 and
Model 2. User-facing responses deliberately omit the underlying vendor model id, and clients cannot
choose one — see the model presentation section in the README.

---

## Auth

### `POST /auth/register` → 201

```json
{ "email": "user@example.com", "password": "at-least-8-chars", "full_name": "Optional Name" }
```

Returns a token pair. A new account is placed on the Free plan with its credit allowance.
409 if the email is already registered.

### `POST /auth/login` → 200

```json
{ "email": "user@example.com", "password": "…" }
```

```json
{ "access_token": "…", "refresh_token": "…", "token_type": "bearer" }
```

401 on bad credentials — the message is identical whether or not the account exists.

### `POST /auth/refresh` → 200

```json
{ "refresh_token": "…" }
```

Returns a fresh pair. An access token presented here is rejected.

### `POST /auth/logout` → 204

JWTs are stateless; the client discards its tokens.

### `POST /auth/forgot-password` → 202

```json
{ "email": "user@example.com" }
```

Always returns the same body regardless of whether the account exists. The emailed link is valid for
one hour and single-use.

### `POST /auth/reset-password` → 204

```json
{ "token": "…from the email link…", "new_password": "at-least-8-chars" }
```

---

## User

### `GET /user/me` → 200

```json
{ "id": "uuid", "email": "…", "full_name": "…", "is_admin": false, "is_verified": false }
```

### `PATCH /user/me` → 200

```json
{ "full_name": "New Name" }
```

---

## Chat

### `POST /chat/stream` → 200 `text/event-stream`

```json
{ "conversation_id": "uuid or null", "message": "Hello", "provider": "openai" }
```

Omit `conversation_id` to start a new conversation; its id is returned in the `X-Conversation-Id`
response header and in the final `done` event.

Server-sent events:

| Event | Data | Meaning |
|---|---|---|
| `delta` | `{"content": "next chunk"}` | Append to the assistant message |
| `error` | `{"message": "…", "code": "provider_error" \| "insufficient_credits"}` | Show the message with a retry affordance |
| `done` | `{"conversation_id": "uuid"}` | Stream finished |

Credits are reserved before the call and **refunded automatically if nothing was generated**, so a
provider outage never costs the user anything.

To stop generation, abort the HTTP request client-side (`AbortController`); the server detects the
disconnect and stops.

### `GET /conversations` → 200

Array of conversation summaries, newest first. Only the caller's own conversations.

### `GET /conversations/{id}` → 200

The conversation plus its full `messages` array. 404 if it isn't yours.

### `PATCH /conversations/{id}` → 200

```json
{ "title": "Renamed" }
```

### `DELETE /conversations/{id}` → 204

Cascades to the conversation's messages.

---

## Images

### `POST /images/generate` → 202

```json
{ "prompt": "A cinematic portrait…", "providers": ["openai", "gemini"], "upload_file_id": null }
```

Optional header `Idempotency-Key: <uuid>` — replaying the same key returns the original response
instead of charging again.

Responds **immediately**, before generation runs, so the UI can render one loading card per model:

```json
{
  "id": "uuid",
  "prompt": "A cinematic portrait…",
  "status": "processing",
  "created_at": "2026-08-25T10:00:00",
  "results": [
    { "id": "uuid", "provider": "openai", "status": "pending", "error": null,
      "image_url": null, "thumbnail_url": null, "created_at": "…" },
    { "id": "uuid", "provider": "gemini", "status": "pending", "error": null,
      "image_url": null, "thumbnail_url": null, "created_at": "…" }
  ]
}
```

Credits for **all** requested providers are reserved up front. If the balance covers one provider but
not both, the request is rejected with 402 and the partial reservation is rolled back.

402 if credits are insufficient, 400 if `upload_file_id` is not yours or no valid provider was given.

### `POST /images/generate-with-upload` → 202

`multipart/form-data`:

| Field | Type | Notes |
|---|---|---|
| `file` | file | JPG/PNG/WEBP, within `MAX_UPLOAD_MB` and `MAX_IMAGE_DIMENSION` |
| `prompt` | text | |
| `providers` | text | Comma-separated, e.g. `openai,gemini` |

The upload is validated by extension **and** content sniffing, then re-encoded to strip metadata and
any appended payload, and stored under a server-generated UUID filename. The original filename is kept
as metadata only and never used to build a path.

400 with a specific message on: disallowed extension, not a valid image, content/extension mismatch,
too large, dimensions too large, empty file.

### `GET /images?limit=20&offset=0` → 200

The caller's generations, newest first.

### `GET /images/{id}` → 200

One generation with its current results. **Poll this** while `status` is `pending` or `processing`.

Each result flips independently, which is what produces the side-by-side behaviour:

| Request `status` | Meaning |
|---|---|
| `processing` | At least one model still running |
| `completed` | All models succeeded |
| `partial` | Some succeeded, some failed — successful results are still returned |
| `failed` | All models failed |

### `POST /images/{id}/regenerate` → 202

```json
{ "provider": "openai" }
```

Omit `provider` to regenerate every model on that request. Adds a new result row linked to the previous
one via `parent_result_id`, so history is preserved rather than overwritten.

---

## Files

Private media is only reachable through these ownership-checked endpoints. There is no public URL for
a generated or uploaded image.

| Endpoint | Returns |
|---|---|
| `GET /files/generated/{image_id}` | Full-size generated image |
| `GET /files/thumbnail/{image_id}` | Thumbnail |
| `GET /files/uploaded/{file_id}` | The user's own upload |

404 if the file does not exist **or** belongs to someone else.

---

## Subscription

### `GET /subscription/plans` → 200 (public)

Plans come from the database — pricing and limits are never hard-coded in the frontend.

### `GET /subscription` → 200

The caller's current subscription with its embedded plan, or `null`.

### `POST /subscription/checkout` → 200

```json
{ "plan_code": "pro" }
```

```json
{ "provider": "razorpay", "order_id": "order_…", "amount": 99900,
  "currency": "INR", "key_id": "rzp_…", "subscription_id": "uuid" }
```

`amount` is in minor units (paise). Hand these to Razorpay Checkout in the browser. 400 for an unknown,
inactive, or free plan.

**A subscription is not activated by the browser.** It becomes active only when the signed webhook arrives.

### `POST /subscription/webhook` → 200

Called by Razorpay, not by your frontend. Requires header `X-Razorpay-Signature`; the raw body is
verified with HMAC-SHA256 against `RAZORPAY_WEBHOOK_SECRET` and a mismatch is rejected with 400.

Handled events: `payment.captured`, `subscription.activated`, `subscription.charged` (activate and
grant the plan's credit allowance), `subscription.cancelled`, `subscription.completed`,
`subscription.halted` (expire).

### `POST /subscription/cancel` → 200

Cancels at period end; the user keeps access until `current_period_end`.

---

## Credits & usage

### `GET /credits` → 200

```json
{ "chat_balance": 950, "image_balance": 180 }
```

### `GET /usage?limit=50&offset=0` → 200

One row per AI operation: slot, operation, credits consumed, status and timestamp.

---

## Admin

All require `is_admin`; a non-admin gets 403. These are the only endpoints that expose real provider
and model identifiers.

| Endpoint | Purpose |
|---|---|
| `GET /admin/stats` | Users, active subscriptions, conversations, generations, failures in 24h |
| `GET /admin/users` | List users |
| `PATCH /admin/users/{id}` | Enable/disable an account, grant/revoke admin |
| `GET /admin/plans` | All plans, including inactive |
| `PATCH /admin/plans/{id}` | Change price, credit allowances, upload limit, active flag |
| `GET /admin/models` | Provider configs with real model ids |
| `PATCH /admin/models/{id}` | Enable/disable a model, change its credit cost or model id |
| `GET /admin/generations/failed` | Recent failures with the underlying error, for debugging |

---

## Health

| Endpoint | Purpose |
|---|---|
| `GET /health` | Liveness — always 200 if the process is up. Use for container/LB checks. |
| `GET /ready` | Readiness — verifies MySQL and Redis; returns `{"status":"ready"\|"degraded","checks":{…}}` |

Both are also available unprefixed at `/health` and `/ready`.
