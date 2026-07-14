# syntax=docker/dockerfile:1
#
#   base    — прод-зависимости + исходники (общий слой).
#   tests   — добавляет dev-зависимости и ГОНЯЕТ юнит-тесты прямо во время сборки.
#             Если хоть один юнит-тест падает — стадия (и весь образ) не собирается.
#   runtime — финальный образ для прода: БЕЗ тестов и dev-зависимостей.

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# Прод-зависимости отдельным слоем для кэширования.
COPY src/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ /app/src/
COPY alembic.ini /app/alembic.ini
COPY migrations/ /app/migrations/
# Версия приложения (см. utils/version.py): по умолчанию — committed
# заглушка "0.0.0-dev"; CI перезаписывает файл вычисленной через
# setuptools_scm версией непосредственно перед `docker build` релиза
COPY VERSION /app/VERSION


FROM base AS tests

COPY src/requirements-dev.txt /app/requirements-dev.txt
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY deploy/test/pytest.ini /app/pytest.ini
COPY tests/ /app/tests/

ENV DB_PASS=build
ARG JWT_SECRET

# Гоняем ТОЛЬКО юнит-тесты (без внешних сервисов). Падение = сборка падает.
RUN JWT_SECRET=${JWT_SECRET:-$(head -c 32 /dev/urandom | base64)} \
    pytest -m unit && touch /app/.unit-tests-passed


FROM base AS runtime

COPY --from=tests /app/.unit-tests-passed /app/.unit-tests-passed

EXPOSE 8000

COPY src/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]
