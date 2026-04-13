#!/bin/bash

set -e

DB_HOST="${DB_HOST:-db}"

echo "Waiting for database..."
python -c "
import socket, time
while True:
    try:
        s = socket.create_connection(('$DB_HOST', 5432), timeout=2)
        s.close()
        break
    except OSError:
        time.sleep(1)
"

echo "Running migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting Gunicorn..."
exec gunicorn boardgameclub.wsgi:application --bind 0.0.0.0:8000
