#!/bin/sh
set -eu
umask 077
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
HOST=${CLONARCH_HOST:-192.168.105.10}
PORT=${CLONARCH_PORT:-8787}
PIDFILE="$ROOT/var/server.pid"
LOGFILE="$ROOT/var/server.log"
mkdir -p "$ROOT/var"
chmod 700 "$ROOT/var"
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "Clonarch already running (PID $(cat "$PIDFILE")) at http://$HOST:$PORT"
  exit 0
fi
if ss -ltn 2>/dev/null | grep -Fq "$HOST:$PORT"; then
  echo "Refusing to start: $HOST:$PORT is already in use" >&2
  exit 1
fi
CLONARCH_HOST="$HOST" CLONARCH_PORT="$PORT" CLONARCH_TIMEZONE=${CLONARCH_TIMEZONE:-America/New_York} \
  nohup "$ROOT/backend/.venv/bin/uvicorn" clonarch.main:app \
  --app-dir "$ROOT/backend/src" --host "$HOST" --port "$PORT" --workers 1 \
  >>"$LOGFILE" 2>&1 &
echo $! > "$PIDFILE"
for _ in $(seq 1 30); do
  if curl -fsS "http://$HOST:$PORT/api/v1/health/ready"; then
    echo "\nClonarch is available at http://$HOST:$PORT"
    exit 0
  fi
  sleep 1
done
echo "Startup failed; see $LOGFILE" >&2
exit 1
