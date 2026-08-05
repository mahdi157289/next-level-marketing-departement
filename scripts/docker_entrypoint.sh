#!/bin/sh
set -e
cd /app
if [ -n "${DATABASE_URL}" ]; then
  echo "[entrypoint] alembic upgrade head..."
  alembic upgrade head
fi
exec "$@"
