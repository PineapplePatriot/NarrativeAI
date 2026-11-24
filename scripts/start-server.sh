#!/bin/sh
# One container/volume: the web app and free Pulse scheduler share the same SQLite database.
set -eu
python manage.py migrate --noinput
python manage.py seed_demo || true
python manage.py pulse_tick --watch &
pulse_pid=$!
gunicorn narrative.wsgi --bind "0.0.0.0:${PORT:-8000}" --workers 1 --threads 8 --timeout 300 &
web_pid=$!
shutdown() {
    trap - EXIT TERM INT
    kill -TERM "$web_pid" "$pulse_pid" 2>/dev/null || true
    wait "$web_pid" 2>/dev/null || true
    wait "$pulse_pid" 2>/dev/null || true
}
trap shutdown EXIT TERM INT
status=0
wait "$web_pid" || status=$?
exit "$status"
