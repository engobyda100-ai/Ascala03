#!/usr/bin/env bash
# Local dev launcher — see WIRING_PLAN.md and README.md.
set -e
cd "$(dirname "$0")"

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "warn: ANTHROPIC_API_KEY not set — real (non-mock) calls will fail."
fi

uvicorn server.main:app --host 127.0.0.1 --port 8000 --reload &
SERVER_PID=$!

( cd project && python3 -m http.server 5173 ) &
FRONT_PID=$!

cleanup() {
  echo
  echo "shutting down..."
  kill $SERVER_PID $FRONT_PID 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

cat <<EOF

  server:   http://localhost:8000      (docs at /docs)
  frontend: http://localhost:5173/Ascala%20Prototype.html

  Press Ctrl+C to stop.
EOF
wait
