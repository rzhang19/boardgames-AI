#!/bin/bash
set -euo pipefail

TARGET="${1:-production}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

if [[ "$TARGET" != "production" && "$TARGET" != "staging" ]]; then
    echo "Usage: $0 [production|staging]"
    exit 1
fi

if [[ "$TARGET" == "production" ]]; then
    SERVICE="web"
else
    SERVICE="staging-web"
fi

BRANCH="main"
HEALTH_TIMEOUT=60
HEALTH_INTERVAL=5
MAX_HISTORY=10
HISTORY_FILE="$SCRIPT_DIR/.deploy_history_${TARGET}"

echo "=== Deploying ${TARGET} (${SERVICE}) ==="

if ! git diff --quiet 2>/dev/null || ! git diff --cached --quiet 2>/dev/null; then
    echo "ERROR: Uncommitted changes detected. Commit or stash before deploying."
    exit 1
fi

BEFORE_SHA=$(git rev-parse HEAD)
BEFORE_SHORT=$(git rev-parse --short HEAD)

mkdir -p "$SCRIPT_DIR"
echo "$(date -Iseconds)|${BEFORE_SHA}" >> "$HISTORY_FILE"
tail -n "$MAX_HISTORY" "$HISTORY_FILE" > "${HISTORY_FILE}.tmp" && mv "${HISTORY_FILE}.tmp" "$HISTORY_FILE"

echo "Pulling latest code from ${BRANCH}..."
git pull origin "$BRANCH"

AFTER_SHA=$(git rev-parse HEAD)
AFTER_SHORT=$(git rev-parse --short HEAD)

if [[ "$BEFORE_SHA" == "$AFTER_SHA" ]]; then
    echo "Already up to date (${AFTER_SHORT}). Nothing to deploy."
    exit 0
fi

echo "Updating: ${BEFORE_SHORT} -> ${AFTER_SHORT}"

echo "Building ${SERVICE}..."
docker compose build "$SERVICE"

echo "Running migrations..."
docker compose run --rm "$SERVICE" python manage.py migrate --noinput

echo "Seeding default verified icons..."
docker compose run --rm "$SERVICE" python manage.py seed_verified_icons

echo "Starting ${SERVICE}..."
docker compose up -d --no-deps --force-recreate "$SERVICE"

echo "Running health check (timeout: ${HEALTH_TIMEOUT}s)..."
ELAPSED=0
HEALTHY=false

while [[ $ELAPSED -lt $HEALTH_TIMEOUT ]]; do
    CONTAINER_ID=$(docker compose ps -q "$SERVICE" 2>/dev/null || true)
    if [[ -n "$CONTAINER_ID" ]]; then
        HEALTH_STATUS=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}unknown{{end}}' "$CONTAINER_ID" 2>/dev/null || echo "unknown")
        if [[ "$HEALTH_STATUS" == "healthy" ]]; then
            HEALTHY=true
            break
        elif [[ "$HEALTH_STATUS" == "unhealthy" ]]; then
            break
        fi
    fi
    sleep "$HEALTH_INTERVAL"
    ELAPSED=$((ELAPSED + HEALTH_INTERVAL))
    echo "  Waiting... (${ELAPSED}s elapsed, status: ${HEALTH_STATUS:-starting})"
done

if $HEALTHY; then
    echo "=== Deploy successful: ${AFTER_SHORT} ==="
    docker image prune -f 2>/dev/null || true
    exit 0
fi

echo "=== Health check FAILED! Rolling back to ${BEFORE_SHORT}... ==="
git checkout "$BEFORE_SHA"
docker compose build "$SERVICE"
docker compose up -d --no-deps --force-recreate "$SERVICE"
echo "=== Rollback complete: ${BEFORE_SHORT} ==="
exit 1
