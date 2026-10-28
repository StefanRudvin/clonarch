#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PIDFILE="$ROOT/var/server.pid"
if [ ! -f "$PIDFILE" ]; then echo "No Clonarch PID file"; exit 0; fi
PID=$(cat "$PIDFILE")
if kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  for _ in $(seq 1 20); do
    kill -0 "$PID" 2>/dev/null || break
    sleep 1
  done
fi
rm -f "$PIDFILE"
echo "Clonarch stopped"
