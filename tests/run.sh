#!/usr/bin/env bash
# Run the Money Tracker SQL tests against a throwaway local PostgreSQL.
# Requires PostgreSQL server binaries (initdb, pg_ctl) and psql.
set -euo pipefail

cd "$(dirname "$0")/.."                      # repo root (so \i migrations/... resolves)
HERE_MIGRATIONS="supabase"

# Find PostgreSQL server binaries (not always on PATH, e.g. Debian/Ubuntu).
BIN="$(dirname "$(command -v psql)")"
if [ ! -x "$BIN/initdb" ]; then
    BIN="$(ls -d /usr/lib/postgresql/*/bin 2>/dev/null | sort -V | tail -1 || true)"
fi
if [ -z "${BIN:-}" ] || [ ! -x "$BIN/initdb" ]; then
    echo "Could not find PostgreSQL server binaries (initdb). Install postgresql." >&2
    exit 1
fi

TMP="$(mktemp -d)"
DATA="$TMP/data"
PORT=55432
trap '"$BIN/pg_ctl" -D "$DATA" stop -m immediate >/dev/null 2>&1 || true; rm -rf "$TMP"' EXIT

"$BIN/initdb" -D "$DATA" -U postgres --auth=trust >/dev/null
"$BIN/pg_ctl" -D "$DATA" -o "-p $PORT -k $TMP -c listen_addresses=''" -l "$TMP/log" start >/dev/null
sleep 1
"$BIN/createdb" -h "$TMP" -p "$PORT" -U postgres app

# Run from the supabase/ dir so the test's \i migrations/... paths resolve.
"$BIN/psql" -h "$TMP" -p "$PORT" -U postgres -d app -q -v ON_ERROR_STOP=1 \
    -c "\\cd $PWD/$HERE_MIGRATIONS" \
    -f "$PWD/tests/rls_and_logic_test.sql"
