#!/usr/bin/env bash
# Tchoucti — incremental deploy (run after each git push).
#
# Sequence: git pull → build images → up -d → prune.
# Idempotent: rerun anytime; no downtime is expected for code-only changes.
# If you change deploy/docker-compose.prod.yml or Dockerfiles, the new
# containers are recreated; the old ones drain on health.
#
# Usage:
#     bash /opt/tchoucti/deploy/deploy.sh
#     # or with a different ref:
#     REF=feat/new-branch bash deploy/deploy.sh

set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/tchoucti}"
COMPOSE_FILE="$INSTALL_DIR/deploy/docker-compose.prod.yml"
ENV_FILE="$INSTALL_DIR/deploy/.env"
REF="${REF:-main}"

log() { printf "\n\033[1;36m▸ %s\033[0m\n" "$*"; }
die() { printf "\n\033[1;31m✗ %s\033[0m\n" "$*"; exit 1; }

[ -f "$COMPOSE_FILE" ] || die "Missing $COMPOSE_FILE — run init-server.sh first?"
[ -f "$ENV_FILE" ]     || die "Missing $ENV_FILE — copy deploy/.env.example and fill it in."

cd "$INSTALL_DIR"

log "Pulling latest from origin/$REF"
git fetch --prune
git checkout "$REF"
git pull --ff-only

log "Building images"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" build --pull

log "Starting stack (detached)"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d --remove-orphans

log "Pruning dangling images"
docker image prune -f >/dev/null

log "Current status"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" ps

cat <<EOF

✅ Deploy done.

Tail logs:    docker compose -f $COMPOSE_FILE logs -f
Backend:      docker logs -f tchoucti_backend
Traefik ACME: docker logs -f tchoucti_traefik | grep -i acme

EOF
