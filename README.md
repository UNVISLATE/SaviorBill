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
- Загрузка медиа в файловую систему или S3
- Рейт-лимитинг на Valkey

## Быстрый старт

```bash
cp .env.example .env        # DB_PASS, OWNER_*; секреты сгенерируются сами
docker compose up --build   # БД, Valkey, миграции, API, luaworker
```

API: `http://localhost:8000` · Swagger: `/docs` · здоровье: `/health`.

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
pip install -r requirements-dev.txt

export PYTHONPATH=src DB_PASS=test JWT_SECRET=test-secret-please-change
python -m pytest -m unit          # юнит-тесты
python -m black src tests migrations
```

## Документация

- **`docs/lua_scripts.md`** — контракты Lua-скриптов (услуги и платежи) и
  пример-шаблоны в `data/lua/`.
- **`docs/payments_methods/`** — подключение платёжных провайдеров
  (ЮKassa, Platega) и что заполнять в `secrets`/`extra`.
- **`.env.example`** — все переменные окружения с пояснениями.

## Лицензия

Проект распространяется под лицензией **Apache License 2.0** — см.
[`LICENSE.txt`](./LICENSE.txt).

Copyright © 2026 UNVI &lt;unvidev@ya.ru&gt; · <https://unvi.xyz>

