#!/bin/bash

set -e

echo "Stopping staging-web..."
docker compose stop staging-web

echo "Resetting staging database..."
docker compose exec staging-db psql -U boardgameclub -d boardgameclub_staging -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

echo "Starting staging-web (will auto-run migrations)..."
docker compose start staging-web

echo "Waiting for migrations..."
sleep 5

if [ "$1" = "--seed" ]; then
    echo "Seeding test data..."
    docker compose exec staging-web python manage.py seed_staging
fi

echo "Staging environment reset complete."
