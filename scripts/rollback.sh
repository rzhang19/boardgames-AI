#!/bin/bash
set -euo pipefail

TARGET="${1:-production}"
SHA="${2:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

if [[ "$TARGET" != "production" && "$TARGET" != "staging" ]]; then
    echo "Usage: $0 [production|staging] [SHA]"
    echo "       $0 [production|staging] list"
    exit 1
fi

if [[ "$TARGET" == "production" ]]; then
    SERVICE="web"
else
    SERVICE="staging-web"
fi

HISTORY_FILE="$SCRIPT_DIR/.deploy_history_${TARGET}"

if [[ "$SHA" == "list" || -z "$SHA" ]]; then
    echo "Recent ${TARGET} deploys:"
    if [[ ! -f "$HISTORY_FILE" ]]; then
        echo "  No deploy history found."
        exit 0
    fi
    while IFS='|' read -r date sha; do
        SHORT=$(git rev-parse --short "$sha" 2>/dev/null || echo "$sha")
        echo "  ${SHORT} (${date})"
    done < <(tail -n 5 "$HISTORY_FILE")
    echo ""
    echo "To rollback: $0 ${TARGET} <SHA>"
    exit 0
fi

if ! git rev-parse "$SHA" >/dev/null 2>&1; then
    echo "ERROR: Commit ${SHA} not found in repository."
    exit 1
fi

SHORT_SHA=$(git rev-parse --short "$SHA")

echo "=== Rolling back ${TARGET} to ${SHORT_SHA} ==="

echo "Checking out ${SHORT_SHA}..."
git checkout "$SHA"

echo "Building ${SERVICE}..."
docker compose build "$SERVICE"

echo "Starting ${SERVICE}..."
docker compose up -d --no-deps --force-recreate "$SERVICE"

echo "=== Rollback complete: ${SHORT_SHA} ==="
