# DEPLOYMENT.md

Deploying to **ai.sumitgroups.com** on your own server with Docker Compose and Caddy.

## What you need

- A Linux server (2 vCPU / 4 GB RAM minimum; 4 vCPU / 8 GB if you expect concurrent image generation)
- Docker Engine 24+ with the Compose plugin
- Ports **80** and **443** open — Caddy needs both to obtain and renew certificates
- A DNS **A record** for `ai.sumitgroups.com` pointing at the server's public IP, resolving *before* you start the stack
- OpenAI and Gemini API keys, and Razorpay credentials if you're selling paid plans

## 1. Install Docker

```bash
curl -fsSL https://get.docker.com | sh
```

```bash
sudo usermod -aG docker $USER && newgrp docker
```

## 2. Get the code

```bash
git clone git@github.com:sumitgroupsindia-creator/AI-sumitgroups.git /opt/ai-sumitgroups
```

```bash
cd /opt/ai-sumitgroups && cp .env.example .env
```

## 3. Configure

Edit `.env`. The values that matter most in production:

```bash
ENVIRONMENT=production
DEBUG=false
DOMAIN=ai.sumitgroups.com
FRONTEND_URL=https://ai.sumitgroups.com
NEXT_PUBLIC_API_URL=/api/v1

DATABASE_URL=mysql+aiomysql://ai_saas:STRONG_PASSWORD@mysql:3306/ai_saas?charset=utf8mb4
MYSQL_USER=ai_saas
MYSQL_PASSWORD=STRONG_PASSWORD
MYSQL_ROOT_PASSWORD=DIFFERENT_STRONG_PASSWORD
MYSQL_DATABASE=ai_saas

REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2

STORAGE_PATH=/app/storage
EMAIL_BACKEND=smtp
```

Generate a unique signing secret — do not reuse one from another environment:

```bash
openssl rand -hex 32
```

Put it in `JWT_SECRET`, then lock the file down:

```bash
chmod 600 .env
```

`docs/ENVIRONMENT.md` documents every variable and has a production checklist.

> `NEXT_PUBLIC_API_URL` is compiled into the frontend **at build time**. Changing it later requires
> `docker compose build frontend`, not just a restart.

## 4. Launch

```bash
cd /opt/ai-sumitgroups && docker compose up -d --build
```

Startup order is handled by health checks: MySQL and Redis come up first, `migrate` runs
`alembic upgrade head` to completion, and only then do `backend`, `worker` and `frontend` start.

Watch it come up:

```bash
docker compose logs -f
```

Caddy obtains a Let's Encrypt certificate on first request. This only works if DNS already resolves to
this server — if it doesn't, fix DNS and run `docker compose restart caddy`.

## 5. Verify

```bash
curl -fsS https://ai.sumitgroups.com/health
```

```bash
curl -fsS https://ai.sumitgroups.com/ready
```

`/ready` should report `{"status":"ready","checks":{"database":true,"redis":true}}`. A `degraded`
response means the backend cannot reach MySQL or Redis.

Then in a browser: sign up, send a chat message, and run an image generation with **Both** selected.
Two result cards should appear and resolve independently.

## 6. Create your admin account

Sign up through the UI first, then promote that account:

```bash
docker compose exec mysql mysql -u root -p"$MYSQL_ROOT_PASSWORD" ai_saas -e "UPDATE users SET is_admin = 1 WHERE email = 'you@example.com';"
```

Sign out and back in — the admin flag is carried in the token. `/admin` will then appear in the sidebar.

## 7. Razorpay webhook

In the Razorpay dashboard → Settings → Webhooks, add:

- **URL** `https://ai.sumitgroups.com/api/v1/subscription/webhook`
- **Secret** the same value as `RAZORPAY_WEBHOOK_SECRET` in `.env`
- **Events** `payment.captured`, `subscription.activated`, `subscription.charged`, `subscription.cancelled`

Subscriptions are activated **only** by a signature-verified webhook — never by the browser — so a user
cannot grant themselves a plan by tampering with client-side code. Requests with a bad signature are
rejected with 400 and logged.

## Operations

### Logs

```bash
docker compose logs -f backend worker
```

Logs are structured JSON. Every line carries `request_id`, `user_id`, `provider`, `operation`,
`status` and `latency_ms`, so you can trace one user's request end to end by its `request_id` — the
same id shown to the user in any error message.

### Updating

```bash
cd /opt/ai-sumitgroups && git pull && docker compose up -d --build
```

Migrations run automatically via the `migrate` service before the app starts.

### Backups

Both the database **and** the storage directory are needed — the database holds image metadata while
the bytes live on disk. Back them up together.

```bash
docker compose exec -T mysql mysqldump -u root -p"$MYSQL_ROOT_PASSWORD" --single-transaction --routines ai_saas > /backup/db-$(date +%F).sql
```

```bash
tar czf /backup/storage-$(date +%F).tar.gz -C /opt/ai-sumitgroups storage
```

A nightly cron entry:

```bash
0 3 * * * cd /opt/ai-sumitgroups && docker compose exec -T mysql mysqldump -u root -p"$MYSQL_ROOT_PASSWORD" --single-transaction ai_saas | gzip > /backup/db-$(date +\%F).sql.gz
```

Restore:

```bash
docker compose exec -T mysql mysql -u root -p"$MYSQL_ROOT_PASSWORD" ai_saas < /backup/db-2026-08-25.sql
```

### Scaling image generation

Generation runs on Celery workers, so throughput scales with worker count:

```bash
docker compose up -d --scale worker=3
```

All workers share the `./storage` bind mount, so any of them can serve any result.

### Using Nginx instead of Caddy

A complete config is provided at `deploy/nginx/ai.sumitgroups.com.conf`. Remove the `caddy` service
from `docker-compose.yml`, publish `frontend`/`backend` ports to localhost, and obtain certificates
with certbot. The critical settings are already in that file:

- `proxy_buffering off` on `/api/` — without it SSE chat responses are buffered and arrive all at once
- `proxy_read_timeout 300s` — image generation legitimately takes minutes
- `client_max_body_size 25M` — must exceed `MAX_UPLOAD_MB`

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Certificate never issues | DNS isn't pointing at this server yet, or port 80 is blocked. Check with `dig ai.sumitgroups.com`, then `docker compose restart caddy`. |
| Chat replies appear all at once instead of streaming | A proxy is buffering. With Nginx, confirm `proxy_buffering off` on `/api/`. |
| Images stay "Queued" forever | The worker isn't running or can't reach Redis: `docker compose logs worker`. |
| Generations fail immediately | Invalid or unfunded provider API keys. Check `/admin` → Failures for the underlying error. |
| Images vanish after redeploy | `./storage` wasn't persisted. Confirm the `./storage:/app/storage` mount exists. |
| 429 responses under normal use | Raise `RATE_LIMIT_PER_MINUTE`, then `docker compose up -d backend`. |
| CORS errors in the browser console | `FRONTEND_URL` doesn't exactly match the origin being served, scheme included. |
| Login works then immediately logs out | `JWT_SECRET` changed, invalidating existing tokens. Expected once after rotating it. |

## Security checklist

- [ ] `DEBUG=false` — otherwise API docs are publicly exposed at `/api/docs`
- [ ] `JWT_SECRET` unique to this environment
- [ ] Database/Redis passwords changed from the placeholders
- [ ] `.env` is `chmod 600` and never committed
- [ ] Only ports 80/443 exposed publicly; MySQL and Redis stay on the internal Docker network (the production compose file does not publish their ports)
- [ ] Firewall enabled (`ufw allow 22,80,443/tcp`)
- [ ] Backups running *and* a restore tested at least once
- [ ] `EMAIL_BACKEND=smtp`, so password reset actually delivers
