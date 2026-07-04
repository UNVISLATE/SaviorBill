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
- Триггеры `событие -> действие` (email/lua, подключаемые модули), правятся в рантайме
- Загрузка медиа (изображения/видео/аватары) через изолированный `mediaworker`:
  потоковый приём с защитой от OOM, конвертация в webp/webm, локальная отдача через
  Caddy или S3 (presigned); товарные вложения (`media_id` + тег). См. `docs/media.md`
- Рейт-лимитинг на Valkey

## Быстрый старт (прод, без клонирования репозитория)

Создайте рабочую директорию и запустите `setup.sh` одной командой:

```bash
mkdir ~/saviorbill && cd ~/saviorbill
bash <(curl -fsSL https://raw.githubusercontent.com/UNVISLATE/SaviorBill/master/deploy/setup.sh)
```

или через `wget`:

```bash
mkdir ~/saviorbill && cd ~/saviorbill
bash <(wget -qO- https://raw.githubusercontent.com/UNVISLATE/SaviorBill/master/deploy/setup.sh)
```

`setup.sh` автоматически:
1. Устанавливает Docker (если не установлен) — через скрипт `get.docker.com`.
2. Скачивает `docker-compose.yml`, `Caddyfile` и `.env` в текущую директорию.
3. Открывает редактор для правки `.env` (задайте `DB_PASS`, `DOMAIN`, `MEDIA_DOMAIN`, `OWNER_*` и другие необходимые под ваши нужды)

```bash
docker compose pull
docker compose up -d
```

После запуска доступно:
- API billing: `https://<DOMAIN>/api/v1/`
- Медиа: `https://<MEDIA_DOMAIN>/`
- Документация billing: `https://<DOMAIN>/docs` или `https://<DOMAIN>/redoc`
- Документация mediaworker: `https://<MEDIA_DOMAIN>/docs` или `https://<MEDIA_DOMAIN>/redoc`

> При необходимости можно настроить используя заместо Caddy иной reverse-proxy (Nginx, Traefik, HAProxy и т.д.)
> см. `deploy/Caddyfile` как пример.  
> Caddy выбран из-за простоты и автоматического получения сертификатов.

Для прода: `.env` создаётся `setup.sh` из `.env.example` в вашей рабочей директории.
Для dev: скопируйте `deploy/.env.example` → `deploy/dev/.env` и поправьте нужные поля.

## Секреты

Секреты — внешние ресурсы. В ENV указывается лишь путь/координаты,
сами значения хранятся в файлах или менеджере секретов. Генерируемые секреты
(`JWT_SECRET`, ключ шифрования `SECRETS_KEY`, `LUA_SERVICE_TOKEN`) создаются
один раз при отсутствии и далее переиспользуются.

> [!CAUTION]
> Настоятельно рекомендуем сделать резервную копию секретов, в случае потери ключа защищенные данные станут недоступны.

Бэкенд выбирается через `SECRETS_BACKEND`:

- `file` (по умолчанию) — каждый секрет в своём файле;
- `aws` — AWS Secrets Manager;
- `gcp` — Google Secret Manager;
- `azure` — Azure Key Vault;
- `vault` — HashiCorp Vault (KV v2).

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

