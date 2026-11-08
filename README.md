# SaviorBill | Проект в разработке

**SaviorBill** — событийно-ориентированная платформа биллинга и движок магазина цифровых товаров и услуг: мультивалютный баланс, каталоги услуг, корзина и заказы, пулы цифровых ключей, промокоды, платежи через внешних провайдеров, OAuth-авторизация (OIDC), email-рассылки и изолированный медиа-конвейер. Вся бизнес-логика жизненного цикла услуг и платёжных шлюзов исполняется в безопасной песочнице Lua.

## Технологический стек

- **Backend:** Python 3.12 · FastAPI · SQLAlchemy 2 (asyncpg)
- **Frontend (Admin UI):** React 19 · TypeScript · Vite · Tailwind CSS · Monaco Editor · Radix UI
- **База данных:** PostgreSQL 16 · миграции Alembic
- **Шина событий и кэш:** Valkey 8 (Redis API) · Redis Streams (`lua:*`, `media:*`, `tasklog:*`)
- **Исполнитель логики:** Изолированный Lua-движок в песочнице (`luaworker/`)
- **Медиа-сервис:** Выделенный микросервис `mediaworker/` (FastAPI + ffmpeg) — приём, сжатие (WebP/WebM), локальное хранилище или S3
- **Безопасность:** RS256 JWT, Argon2id, криптобокс Fernet, HMAC-SHA256 подпись шины сообщений (`BUS_SIGNING_KEY`), Cookie CSRF защита

## Возможности

- **Аутентификация и безопасность:** Регистрация/вход, refresh-сессии, сброс пароля, OAuth2/OIDC, древовидный RBAC, защита от брутфорса (`LoginGuard`), App Tokens (машинные API-токены с Scoped RBAC, IP Allowlist и CIDR-фильтрацией).
- **Каталог и цифровые товары (Service Engine 2.0):** Иерархические каталоги, гибкие модели ценообразования (`fixed`, `custom` с валидацией диапазонов, `tiered` тарифные сетки, `configurable` конфигуратор ресурсов), пулы ключей (выдача `SKIP LOCKED`, триггеры стока).
- **Песочница Lua:** Monaco Editor прямо в панели управления, подсветка синтаксиса, линтинг, выполнение действий жизненного цикла (`create`, `renew`, `freeze`, `unfreeze`, `delete`).
- **Платежи и баланс:** Платёжные провайдеры с шифрованными секретами и Lua-скриптами (инициализация, редиректы, вебхуки, авто-перепроверка зависших оплат через `BillingLoop`). Мультивалютный биллинг и мультиисточниковый FX Engine (CBR, MOEX, Crypto).
- **Промокоды:** Промо-каталоги, гибкие условия применения (скидки, бонусы к балансу, выдача услуг).
- **Событийные триггеры:** Модули `событие -> действие` (email-уведомления, запуск Lua, системные триггеры остатков).
- **Медиа-конвейер:** Двухшаговая загрузка с защитой от OOM, генерация превью, хранение в локальной ФС или S3 (Cloudflare R2, AWS S3, MinIO).
- **Безопасность, кэш и SecOps:** 32-hex Trace ID, 404 автобан сканеров, двухуровневый Valkey-кэш каталога (L1/L2), журнал системных ошибок и дашборд безопасности.

## Развёртывание

Подробное руководство по установке и продакшн-настройке доступно в [**DEPLOY.md**](./DEPLOY.md):
- **All-in-One:** Полный стек на одном сервере через Docker Compose и Caddy (авто-выпуск Let's Encrypt SSL).
- **Multi-Node:** Распределённый кластер (изолированное ядро БД/Valkey в WireGuard-оверлее, масштабируемый пул вычислительных нод `luaworker`, медиа в S3).

### Быстрый старт (прод, без клонирования репозитория)

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
3. Открывает редактор для правки `.env` (задайте `DB_PASS`, `DOMAIN`, `MEDIA_DOMAIN`, `OWNER_*` и другие параметры под ваши нужды).

```bash
docker compose pull
docker compose up -d
```

После запуска доступно:
- **Admin UI / Web:** `https://<DOMAIN>/`
- **REST API:** `https://<DOMAIN>/api/v1/`
- **Медиа-сервер:** `https://<MEDIA_DOMAIN>/`
- **OpenAPI Документация billing:** `https://<DOMAIN>/docs` или `https://<DOMAIN>/redoc`
- **OpenAPI Документация mediaworker:** `https://<MEDIA_DOMAIN>/docs`

## Секреты

Секреты разрешаются через подсистему `src/security/sec/secrets/`. В `.env` указываются координаты и пути, сами значения хранятся в защищённых файлах или менеджере секретов. 

Генерируемые секреты (ключевая пара JWT RS256 `JWT_PRIVATE_KEY`/`JWT_PUBLIC_KEY`, ключ шифрования `SECRETS_KEY`) генерируются автоматически при первом запуске в каталоге `data-private/` (права `chmod 700`, монтируется только в `billing`).

Поддерживаемые бэкенды (`SECRETS_BACKEND`):
- `file` (по умолчанию) — локальные файлы в защищённой директории;
- `vault` — HashiCorp Vault (KV v2);
- `aws` — AWS Secrets Manager;
- `gcp` — Google Secret Manager;
- `azure` — Azure Key Vault.

## Лицензия

Проект распространяется под лицензией **PolyForm Shield License 1.0.0** (Source-Available) — см. [`LICENSE.txt`](./LICENSE.txt).

- **Бесплатно для собственного использования (Self-Hosted):** Вы можете бесплатно запускать SaviorBill на своих серверах для приёма платежей и ведения бизнеса своих проектов без скрытых комиссий и роялти.
- **Защита от конкуренции (Noncompete):** Запрещается использовать исходный код платформы для запуска сторонних коммерческих SaaS-сервисов биллинга, напрямую конкурирующих с SaviorBill и облачными сервисами правообладателя (Savior Cloud).

Copyright © 2026 UNVI &lt;unvidev@ya.ru&gt; · <https://unvi.xyz>
