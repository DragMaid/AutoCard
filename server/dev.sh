#!/usr/bin/env bash
# Starts the two backend processes for local development.
#
# The engine must be up before the relay accepts a join, but the relay only
# connects to it lazily (on the first join), so the ordering here is a
# convenience rather than a requirement.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
[ -x "$PYTHON" ] || PYTHON="python3"

cleanup() {
    trap - INT TERM EXIT
    [ -n "${ENGINE_PID:-}" ] && kill "$ENGINE_PID" 2>/dev/null || true
    [ -n "${RELAY_PID:-}" ] && kill "$RELAY_PID" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

echo "[dev] engine  -> ws://localhost:${AUTOCARD_ENGINE_PORT:-9000}"
(cd "$ROOT" && "$PYTHON" -m engine) &
ENGINE_PID=$!

echo "[dev] relay   -> http://localhost:8080"
(cd "$ROOT/server/AutoCard.Server" && ASPNETCORE_ENVIRONMENT=Development dotnet run) &
RELAY_PID=$!

echo "[dev] frontend: cd web && npm run dev"
wait -n "$ENGINE_PID" "$RELAY_PID"
