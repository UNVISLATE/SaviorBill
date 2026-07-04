# syntax=docker/dockerfile:1
#
# Многостадийная сборка mediaworker с авто-прогоном юнит-тестов (как у billing).
#
#   base    — ffmpeg + прод-зависимости + исходники.
#   tests   — dev-зависимости + ГОНЯЕТ юнит-тесты во время сборки (падение = провал).
#   runtime — финальный образ без dev-зависимостей и тестов.
#
# runtime копирует «маркер успешных тестов» из стадии tests => обычный build
# обязан пройти тесты.

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src

# ffmpeg для конвертации изображений (webp) и видео (webm).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ /app/src/


FROM base AS tests

COPY requirements-dev.txt /app/requirements-dev.txt
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY pytest.ini /app/pytest.ini
COPY tests/ /app/tests/

RUN pytest -q && touch /app/.tests-passed


FROM base AS runtime

COPY --from=tests /app/.tests-passed /app/.tests-passed

ENV VALKEY_HOST=valkey \
    VALKEY_PORT=6379 \
    VALKEY_DB=0 \
    DB_HOST=db \
    DB_PORT=5432 \
    DATA_DIR=/app/data \
    MEDIA_TASK_STREAM=media:tasks \
    MEDIA_RESULT_STREAM=media:results \
    MEDIA_GROUP=mediaworkers \
    STORAGE_BACKEND=fs

EXPOSE 8080

# host/port берутся из конфигурации (Config.HOST/PORT) через сам app.py.
CMD ["python", "src/app.py"]
