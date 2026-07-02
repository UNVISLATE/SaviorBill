# SaviorBill

**SaviorBill** — событийная биллинг-система: пользователи и баланс, каталог
услуг, заказы, платежи через внешних провайдеров, промокоды, OAuth-вход,
email-уведомления и загрузка медиа. Внешние интеграции (платёжки, выдача услуг)
исполняются изолированно через Lua.

## Технологический стек

- **Ядро:** Python 3.12 · FastAPI · SQLAlchemy 2 (async)
- **БД:** PostgreSQL · миграции Alembic
- **Кэш/события:** Valkey (форк Redis)
- **Интеграции:** Lua-движок в песочнице (отдельный процесс `luaworker/`)
- **Медиа:** отдельный сервис `mediaworker/` (Python + ffmpeg) — приём, конвертация
  (webp/webm), отдача; единый reverse-proxy Caddy (авто TLS, HTTP/2 и HTTP/3)
- **Архитектура:** Event-Driven, изоляция интеграций, `Decimal` для всех денег

## Возможности

- Регистрация/вход (JWT), refresh/logout, сброс пароля по email
- OAuth-вход и привязка внешних учёток (OIDC); верификация email
- Древовидный RBAC; bootstrap owner-пользователя при первом запуске
- Каталог услуг с подкаталогами; заказ с баланса или через платёжку
- Платёжные провайдеры с шифрованными секретами и Lua-скриптами
  (инициализация + обработка колбэка через server-to-server webhook)
- Промокоды: код-токен + каталог, описывающий действие (бонус/скидка/услуга)
- Email-шаблоны (правятся в рантайме) + прямые письма (верификация, сброс пароля)
- Триггеры `событие → действие` (email/lua, подключаемые модули), правятся в рантайме
- Загрузка медиа (изображения/видео/аватары) через изолированный `mediaworker`:
  потоковый приём с защитой от OOM, конвертация в webp/webm, локальная отдача через
  Caddy или S3 (presigned); товарные вложения (`media_id` + тег). См. `docs/media.md`
- Рейт-лимитинг на Valkey

## Быстрый старт (прод, одной командой)

```bash
git clone https://github.com/UNVISLATE/SaviorBill.git && cd SaviorBill && bash deploy/setup.sh
```

`deploy/setup.sh` создаёт `deploy/.env` из `deploy/.env.example`, открывает редактор
(`$EDITOR`/`nano`/`vi`) для правки, затем печатает команду запуска и предлагает поднять
стек. Образы тянутся из реестра (`ghcr.io`), сборка не требуется:

```bash
docker compose -f deploy/docker-compose.yml pull
docker compose -f deploy/docker-compose.yml up -d   # прод: billing, luaworker, mediaworker, Caddy, БД, Valkey
```

Через Caddy: `https://<DOMAIN>` (для `localhost` — самоподписанный сертификат) ·
Swagger: `/docs` · здоровье: `/health`.

## Развёртывания (compose-файлы)

| Назначение | Файл(ы) | Команда |
|------------|---------|---------|
| **Прод** — образы из реестра | `deploy/docker-compose.yml` | `make prod` |
| **Dev** — сборка из исходников | `deploy/dev/docker-compose.yml` | `make dev` |
| **Тесты** — полный стек + прогон | `deploy/dev/docker-compose.yml` + `deploy/test/docker-compose.yml` | `make test` |

Реестр и тег образов для прода настраиваются в `deploy/.env` (`IMAGE_PREFIX`, `TAG`).
Удобные цели — в `Makefile` (`make dev`, `make test`, `make prod`, `make unit`, …).

## Секреты

Политика: секреты — внешние ресурсы. В ENV указывается лишь путь/координаты,
сами значения хранятся в файлах или менеджере секретов. Генерируемые секреты
(`JWT_SECRET`, ключ шифрования `SECRETS_KEY`, `LUA_SERVICE_TOKEN`) создаются
один раз при отсутствии и далее переиспользуются.

Бэкенд выбирается через `SECRETS_BACKEND`:

- `file` (по умолчанию) — каждый секрет в своём файле под `DATA_DIR/keys`;
- `aws` — AWS Secrets Manager; `gcp` — Google Secret Manager;
- `azure` — Azure Key Vault; `vault` — HashiCorp Vault (KV v2).

Предоставляемые секреты (`DB_PASS`, `SMTP_PASS`, `S3_SECRET`) можно задать
напрямую, через файл `*_FILE` (Docker secret) или из менеджера секретов.

## Локальная разработка

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r src/requirements-dev.txt

export PYTHONPATH=src DB_PASS=test JWT_SECRET=test-secret-please-change
python -m pytest -c deploy/test/pytest.ini --rootdir=. -m unit   # юнит-тесты billing
python -m black src tests migrations mediaworker

# mediaworker (отдельный сервис): юнит-тесты
cd mediaworker && PYTHONPATH=src pytest -q
```

Полный стек со сборкой из исходников — `make dev` (или
`docker compose -f deploy/dev/docker-compose.yml up --build`); в dev порт billing
проброшен на `http://localhost:8000`. Прогон интеграционных тестов в докере —
`make test`.

## Структура репозитория

```
alembic.ini · Makefile · README.md · LICENSE.txt   # остаются в корне
src/                          # ядро billing (FastAPI)
  Dockerfile                  # образ billing (контекст сборки = корень)
  requirements*.txt           # зависимости billing
deploy/
  docker-compose.yml          # ПРОД: образы из ghcr.io (сборки нет)
  Caddyfile                   # единый reverse-proxy (TLS/HTTP2/3)
  setup.sh · .env.example     # подготовка окружения (deploy/.env)
  dev/docker-compose.yml      # DEV: сборка из исходников
  test/docker-compose.yml     # ТЕСТЫ: оверлей + сервис `tests`
  test/pytest.ini             # конфигурация pytest
luaworker/                    # изолированный Lua-движок (Redis Streams)
mediaworker/                  # приём/конвертация/отдача медиа (ffmpeg)
migrations/                   # Alembic
data/                         # монтируемые lua-скрипты, ключи, media (рантайм)
examples/lua/                 # примеры скриптов (в рантайм добавляются вручную)
docs/                         # документация
```

## Документация

- **`docs/lua_scripts.md`** — контракты Lua-скриптов (услуги, платежи, триггеры)
  и справочные примеры в `examples/lua/` (в т.ч. выдача VPN через Marzban).
- **`docs/payments_methods/`** — подключение платёжных провайдеров
  (ЮKassa, Platega) и что заполнять в `secrets`/`extra`.
- **`deploy/.env.example`** — все переменные окружения с пояснениями.

## Лицензия

Проект распространяется под лицензией **Apache License 2.0** — см.
[`LICENSE.txt`](./LICENSE.txt).

Copyright © 2026 UNVI &lt;unvidev@ya.ru&gt; · <https://unvi.xyz>

