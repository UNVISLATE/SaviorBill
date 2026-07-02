# deploy/

Всё, что относится к развёртыванию: прод-compose, reverse-proxy, подготовка
окружения, а также отдельные оверлеи для разработки и тестов.

```
deploy/
  docker-compose.yml     # ПРОД: образы из ghcr.io (сборки нет)
  Caddyfile              # единый reverse-proxy (TLS/HTTP2/3)
  setup.sh               # подготовка deploy/.env и запуск прод-стека
  .env.example           # шаблон переменных окружения
  dev/docker-compose.yml   # DEV: сборка из исходников
  test/docker-compose.yml  # ТЕСТЫ: оверлей поверх dev + сервис `tests`
  test/pytest.ini          # конфигурация pytest (billing)
```

| Стек | Файл(ы) | Команда (из корня репозитория) |
|------|---------|-------------------------------|
| **Прод** | `deploy/docker-compose.yml` | `docker compose -f deploy/docker-compose.yml up -d` · `make prod` |
| **Dev** | `deploy/dev/docker-compose.yml` | `docker compose -f deploy/dev/docker-compose.yml up --build` · `make dev` |
| **Тесты** | `deploy/dev/docker-compose.yml` + `deploy/test/docker-compose.yml` | `docker compose -f deploy/dev/docker-compose.yml -f deploy/test/docker-compose.yml up --build --abort-on-container-exit --exit-code-from tests` · `make test` |

## Пути и project directory

Docker compose берёт project directory из каталога **первого** `-f` файла, а
относительные пути в compose разрешаются относительно него:

- **Прод** (`deploy/docker-compose.yml`) → project dir = `deploy/`. Пути: `../data`,
  `./Caddyfile`, `env_file: .env` (= `deploy/.env`). Реестр/тег — в `deploy/.env`
  (`IMAGE_PREFIX`, `TAG`).
- **Dev** (`deploy/dev/docker-compose.yml`) → project dir = `deploy/dev/`. Пути:
  `context: ../..` (корень репозитория), `dockerfile: src/Dockerfile`, `../../data`,
  `../Caddyfile` (= `deploy/Caddyfile`).
- **Тесты** — оверлей поверх dev, поэтому project dir остаётся `deploy/dev/`, и пути
  в `deploy/test/docker-compose.yml` (`context: ../..`) разрешаются относительно
  `deploy/dev/`, а НЕ относительно `deploy/test/`.

## Dockerfile billing

`src/Dockerfile` собирается с контекстом = корень репозитория (нужны `migrations/`,
`alembic.ini`, `tests/`, `deploy/test/pytest.ini`). Отдельно:
`docker build -f src/Dockerfile -t billing .`

Билд-образы `billing` и `mediaworker` прогоняют свои юнит-тесты прямо во время
сборки (multi-stage), поэтому `--build` заодно проверяет их.
