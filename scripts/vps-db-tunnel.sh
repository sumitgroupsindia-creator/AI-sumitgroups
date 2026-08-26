#!/usr/bin/env bash
# Forward the production MySQL to localhost:3307, for running the local app against real data.
#
#   ./scripts/vps-db-tunnel.sh          # keep this terminal open; Ctrl-C closes the tunnel
#
# MySQL on the VPS listens only on an internal Docker network — nothing is published beyond 80 and
# 443. Rather than opening a port to the internet, this forwards through SSH: the far end of the
# tunnel is the mysql *container*, resolved fresh each time because its IP changes whenever the
# container is recreated.
set -euo pipefail

VPS_HOST="${VPS_HOST:-187.52.126.134}"
VPS_USER="${VPS_USER:-root}"
VPS_PORT="${VPS_PORT:-22}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/sumitgroups_deploy}"
LOCAL_PORT="${LOCAL_PORT:-3307}"
COMPOSE_DIR="${COMPOSE_DIR:-/opt/ai-sumitgroups}"

ssh_vps() { ssh -o BatchMode=yes -o ConnectTimeout=10 -i "$SSH_KEY" -p "$VPS_PORT" "$VPS_USER@$VPS_HOST" "$@"; }

echo "Finding the mysql container on $VPS_HOST…"
container_ip=$(ssh_vps "docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' \
  \$(docker compose -f $COMPOSE_DIR/docker-compose.yml ps -q mysql)" | tr -d '\r')

if [[ -z "$container_ip" ]]; then
  echo "Could not find the mysql container. Is the stack up on the VPS?" >&2
  exit 1
fi
echo "mysql container is at $container_ip"

if lsof -i ":$LOCAL_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port $LOCAL_PORT is already in use — a tunnel may already be open." >&2
  exit 1
fi

cat <<EOF

Tunnel: localhost:$LOCAL_PORT  ->  $container_ip:3306 (on $VPS_HOST)

Put this in your shell before starting the stack — the password is the MYSQL_PASSWORD
from the VPS's own .env, so read it from there rather than copying it around:

  export REMOTE_DATABASE_URL="mysql+aiomysql://ai_saas:<MYSQL_PASSWORD>@host.docker.internal:$LOCAL_PORT/ai_saas?charset=utf8mb4"

This is the production database. Every write is real.
Ctrl-C to close the tunnel.

EOF

exec ssh -N -o BatchMode=yes -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \
  -i "$SSH_KEY" -p "$VPS_PORT" \
  -L "$LOCAL_PORT:$container_ip:3306" "$VPS_USER@$VPS_HOST"
