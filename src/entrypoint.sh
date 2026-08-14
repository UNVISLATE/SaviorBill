#!/bin/sh
set -e

# Примонтированные volume'ы (data/data-private) приходят с хоста и обычно
# принадлежат root — chown нужен один раз на старте, до того как уронить
# привилегии до непривилегированного пользователя (см. Dockerfile).
# best-effort: ro-примонтированные пути (если появятся) просто пропускаем.
chown -R app:app /app/data /app/private 2>/dev/null || true

echo "[entrypoint] running migrations (alembic upgrade head)..."
if ! gosu app alembic upgrade head; then
    echo "[entrypoint] FATAL: migration failed, see traceback above." >&2
    echo "[entrypoint] rollback: 'docker compose exec billing alembic downgrade -1'," >&2
    echo "[entrypoint] or redeploy the previous image (TAG=<previous_version>)." >&2
    exit 1
fi
echo "[entrypoint] migrations OK"

echo "[entrypoint] starting billing..."
exec gosu app python src/app.py
