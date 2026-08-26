# DATABASE.md

MySQL 8, accessed asynchronously via SQLAlchemy 2 (`mysql+aiomysql`) and migrated with Alembic.

## MySQL-specific decisions

These are not cosmetic — each one fixes a real failure mode found while building on MySQL:

| Decision | Why |
|---|---|
| **UUID primary keys stored as `CHAR(32)`** | SQLAlchemy's generic `Uuid` type. MySQL has no native UUID column and no `gen_random_uuid()`, so ids are generated in Python (`default=uuid.uuid4`). This also means the application knows the id before INSERT. |
| **Client-side timestamp defaults, not just server defaults** | MySQL has no `RETURNING`. With only a server default, `created_at`/`updated_at` stay *expired* after INSERT and lazy-load on first access — which happens during response serialisation, outside SQLAlchemy's async greenlet, raising `MissingGreenlet`. Python-side defaults populate the value immediately. |
| **`DATETIME(6)` (microsecond precision)** | Plain `DATETIME` truncates to whole seconds. Rows created in the same second then tie, scrambling `created_at` ordering — chat messages could render out of order and "latest subscription" became non-deterministic. |
| **Server runs at UTC** (`--default-time-zone=+00:00`) | `DATETIME` carries no timezone. The app stores naive UTC and pins the server to UTC so SQL-side defaults agree. |
| **InnoDB + `utf8mb4`** | Transactions and row locks (required by the credit system) and full Unicode including emoji. |

## Tables

### `users`
| Column | Type | Notes |
|---|---|---|
| `id` | CHAR(32) PK | |
| `email` | VARCHAR(255) | UNIQUE, indexed |
| `hashed_password` | VARCHAR(255) NULL | bcrypt. NULL for future OAuth-only accounts. |
| `full_name` | VARCHAR(255) NULL | |
| `is_active` | BOOL | Disabling blocks login immediately |
| `is_admin` | BOOL | Gates `/api/v1/admin/*` |
| `is_verified` | BOOL | |
| `auth_provider`, `provider_user_id` | VARCHAR NULL | Present so OAuth is additive, not a migration |

### `password_resets`
`user_id` FK → users (CASCADE), `token_hash` UNIQUE, `used` BOOL.
Only the SHA-256 hash of the token is stored, so a database leak does not yield usable reset links.
Tokens expire one hour after `created_at` and are single-use.

### `plans`
`code` UNIQUE (`free`/`pro`/`business`), `name`, `description`, `price` DECIMAL(10,2), `currency`,
`billing_interval`, `monthly_credits`, `max_upload_mb`, `priority_queue`, `is_active`.

Pricing and limits live here so the frontend never hard-codes them and admins can change them without
a deploy.

### `subscriptions`
`user_id` FK (CASCADE), `plan_id` FK, `status`, `provider`, `provider_subscription_id` (indexed —
the webhook looks up by it), `current_period_start`/`current_period_end`, `cancel_at_period_end`,
`cancelled_at`.

`status`: `pending` → `active` → (`past_due` | `cancelled` | `expired`).

### `credits`
One row per user (`UNIQUE(user_id)`), with a single `balance`.

**One credit is one rupee.** Chat and images spend the same wallet: a split balance could leave a
customer out of pictures while still holding words, which is not something a rupee-denominated
credit can honestly describe.

Balances are mutated only through `credit_service`, which takes a row lock:

```sql
SELECT … FROM credits WHERE user_id = ? FOR UPDATE
```

That lock is what makes concurrent spending safe — two overlapping requests against a balance that
covers only one result in exactly one success and one rejection, never a negative balance. This is
covered directly by `test_concurrent_spends_cannot_double_spend`.

### `usage_records`
`user_id` FK (indexed), `request_id` (indexed, correlates with logs), `provider`, `model`, `operation`,
`credits_consumed`, `status`, `latency_ms`, `error`.

An append-only audit trail. Failed operations are recorded with `credits_consumed = 0` because the
reservation is refunded.

### `idempotency_keys`
`UNIQUE(user_id, key)` with the stored `status_code` and `response_body`. Replaying an
`Idempotency-Key` returns the original response instead of charging credits twice.

### `conversations`
`user_id` FK (CASCADE), `title`, `model`, `provider`, `is_archived`.
Composite index `(user_id, created_at)` for the sidebar listing.

### `messages`
`conversation_id` FK (CASCADE), `role`, `content` TEXT, `provider`, `model`, `tokens_used`, `error`.
Composite index `(conversation_id, created_at)` — the microsecond precision above is what keeps this
ordering correct.

Note there is no `user_id` here: ownership is established through the parent conversation, and every
query joins from a conversation already filtered by `user_id`.

### `uploaded_files`
`user_id` FK (CASCADE), `stored_filename` UNIQUE (a server-generated UUID), `original_filename`
(**metadata only — never used to build a path**), `content_type`, `size_bytes`, `width`, `height`.

### `generation_requests`
`user_id` FK (CASCADE), `prompt` TEXT, `upload_file_id` FK NULL (SET NULL), `status`, `request_ref`
(indexed, the observability request id). Composite index `(user_id, created_at)`.

`status`: `pending` | `processing` | `completed` | `partial` | `failed`.

### `generation_results`
One row **per provider per attempt** — this is the table that makes side-by-side comparison work.

`request_id` FK (CASCADE, indexed), `provider`, `model`, `status`, `error`, `latency_ms`,
`generated_image_id` FK NULL, `parent_result_id` FK NULL (self-referential — a regeneration points at
the result it replaced, so history is preserved).

Because each row carries its own status, one provider can be `completed` while its sibling is still
`pending`, and a `failed` row never hides a `completed` one.

### `generated_images`
`user_id` FK (CASCADE), `stored_filename` UNIQUE, `thumbnail_filename`, `content_type`, `width`,
`height`, `size_bytes`.

**Only metadata lives here — image bytes are on disk** under `storage/images/generated/`.

### `provider_configs`
`UNIQUE(provider, capability)`, with `model`, `is_enabled`, `display_name` and three numbers that
together define the economics of one operation:

| Column | Meaning |
|---|---|
| `provider_cost_inr` DECIMAL(10,4) | what the vendor bills us |
| `credit_cost` | charged to the customer before margin |
| `margin_credits` | profit added on top |

The customer pays `credit_cost + margin_credits`; the margin is `charge − provider_cost_inr`. Every
price is resolved through `app.services.pricing_service`, never read off this row directly, so a
reservation, a refund and the figure quoted in the UI cannot disagree.

Margin is charged **per operation**, not per prompt: asking both slots for an image produces two
vendor bills, so it produces two margins, and a refund for one failed slot hands back exactly what
that slot was charged.

### `prompt_templates`
`key` UNIQUE, with `scope` (chat|image), `kind` (base|task|tool), `name`, `description`, `content`,
`is_enabled`, `sort_order`.

The instructions the product adds around every request — the assistant's identity, the house style,
and the task styles. They live here rather than in source because prompt wording is the thing most
likely to need changing.

`kind` decides when a row is used:

| kind | when |
|---|---|
| `base` | always, for its scope |
| `task` | when the router judges it a fit for the request; its `description` is what the router reads |
| `tool` | run by the machinery itself — the router's own prompt, and the brief for reading an attached photo. Disabling one turns that step and the API call it costs off. |

Composed in `app.services.prompt_service`. Helper calls are recorded in `usage_records` as
`assist_route` / `assist_vision` with `credits_consumed = 0` and a real `cost_inr`: they are spent
out of the margin, so the profit report has to be able to see them.

## Relationships

```
users ─┬─< subscriptions >── plans
       ├─── credits (1:1)
       ├─< usage_records
       ├─< idempotency_keys
       ├─< password_resets
       ├─< conversations ─< messages
       ├─< uploaded_files ──┐
       ├─< generated_images │
       └─< generation_requests ─< generation_results
                                        │
              generation_results.parent_result_id ──┘ (self)
```

## User data isolation

The guarantee that User A can never reach User B's data rests on three things:

1. **Every user-owned table carries an indexed `user_id` with an FK to `users`.**
2. **Every read filters by the authenticated user**, taken from the JWT — never from a client-supplied
   parameter: `WHERE id = :id AND user_id = :current_user_id`.
3. **A miss returns 404, not 403**, so the API does not reveal that another user's resource exists.

File serving follows the same rule: `GET /files/generated/{id}` loads the row, compares `user_id`, and
only then streams from disk. Since on-disk names are server-generated UUIDs, a client-supplied string
can never influence a filesystem path.

`backend/tests/test_user_isolation.py` covers all of this — including the subtle case of attempting to
generate an image using someone else's uploaded photo.

## Migrations

```bash
cd backend && alembic upgrade head
```

```bash
cd backend && alembic revision --autogenerate -m "describe the change"
```

| Revision | Contents |
|---|---|
| `0001_initial` | All tables, indexes, FKs and constraints |
| `0002_seed_data` | Free/Pro/Business plans and the four provider configs |

Always review autogenerated migrations before committing — Alembic's MySQL diffing can miss index and
type changes.

## Backups

```bash
docker compose exec mysql mysqldump -u root -p"$MYSQL_ROOT_PASSWORD" --single-transaction --routines ai_saas > backup.sql
```

`--single-transaction` gives a consistent InnoDB snapshot without locking writes.

**The database alone is not a complete backup** — it stores image *metadata*, while the bytes live in
`./storage`. Back up both together or restored rows will point at missing files.
