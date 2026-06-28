# syntax=docker/dockerfile:1
#
# Многостадийная сборка с авто-прогоном юнит-тестов.
#
#   base    — прод-зависимости + исходники (общий слой).
#   tests   — добавляет dev-зависимости и ГОНЯЕТ юнит-тесты прямо во время сборки.
#             Если хоть один юнит-тест падает — стадия (и весь образ) не собирается.
#   runtime — финальный образ для прода: БЕЗ тестов и dev-зависимостей.
#
# Хитрость: runtime копирует «маркер успешных тестов» из стадии tests
# (COPY --from=tests). Поэтому обычный `docker build` / `docker compose build`
# ОБЯЗАН построить стадию tests => юнит-тесты выполняются на каждой сборке.

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# Прод-зависимости отдельным слоем для кэширования.
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ /app/src/
COPY alembic.ini /app/alembic.ini
COPY migrations/ /app/migrations/


FROM base AS tests

COPY requirements-dev.txt /app/requirements-dev.txt
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY pytest.ini /app/pytest.ini
COPY tests/ /app/tests/

# Конфигу нужны обязательные переменные даже для импорта приложения.
ENV DB_PASS=build JWT_SECRET=build-secret-build-secret-build

# Гоняем ТОЛЬКО юнит-тесты (без внешних сервисов). Падение = сборка падает.
RUN pytest -m unit && touch /app/.unit-tests-passed


FROM base AS runtime

COPY --from=tests /app/.unit-tests-passed /app/.unit-tests-passed

EXPOSE 8000

# host/port берутся из конфигурации; миграции запускаются в entrypoint compose.
CMD ["uvicorn", "app:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]
