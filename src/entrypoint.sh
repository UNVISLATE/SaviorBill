#!/bin/sh
set -e

echo "[entrypoint] running migrations (alembic upgrade head)..."
if ! alembic upgrade head; then
    echo "[entrypoint] FATAL: migration failed, see traceback above." >&2
    echo "[entrypoint] rollback: 'docker compose exec billing alembic downgrade -1'," >&2
    echo "[entrypoint] or redeploy the previous image (TAG=<previous_version>)." >&2
    exit 1
fi
echo "[entrypoint] migrations OK"

echo "[entrypoint] starting billing..."
exec python src/app.py
