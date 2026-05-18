#!/bin/sh
# Whycron worker entrypoint.
#
# The API container is the only one that runs migrations — when several
# workers boot at once we don't want a thundering herd of alembic
# upgrade attempts. We just wait until Postgres is reachable, then
# start the worker.

set -e

echo "[whycron] worker waiting for postgres…"

attempt=0
max_attempts=30
until python -c "
import os, sys
import asyncio
import asyncpg

async def main():
    url = os.environ['DATABASE_URL']
    if url.startswith('postgresql+asyncpg://'):
        url = url.replace('postgresql+asyncpg://', 'postgresql://', 1)
    conn = await asyncpg.connect(url)
    await conn.close()

asyncio.run(main())
" 2>/dev/null; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge "$max_attempts" ]; then
        echo "[whycron] postgres still unreachable after ${max_attempts} tries; giving up." >&2
        exit 1
    fi
    sleep 2
done

echo "[whycron] postgres reachable; starting worker."
exec "$@"
