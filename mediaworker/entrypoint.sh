#!/bin/sh
set -e

# /app/data приходит с хоста и обычно принадлежит root — chown нужен один
# раз на старте, до того как уронить привилегии до непривилегированного
# пользователя (см. Dockerfile).
chown -R app:app /app/data 2>/dev/null || true

# host/port берутся из конфигурации (Config.HOST/PORT) через сам app.py.
exec gosu app python src/app.py
