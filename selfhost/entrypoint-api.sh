#!/bin/sh
# Whycron API entrypoint.
#
# Runs Alembic migrations once before launching the API process. Postgres
# may take a few seconds to accept connections in cold starts; we retry
# the migration step up to 30 times (~60s) before giving up.

set -e

echo "[whycron] waiting for postgres + applying migrations…"

attempt=0
max_attempts=30
until alembic upgrade head; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge "$max_attempts" ]; then
        echo "[whycron] alembic upgrade head failed after ${max_attempts} attempts; giving up." >&2
        exit 1
    fi
    echo "[whycron] migration attempt ${attempt} failed; retrying in 2s…"
    sleep 2
done

echo "[whycron] migrations applied; starting API."
exec "$@"
