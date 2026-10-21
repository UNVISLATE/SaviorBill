# Руководство по развёртыванию SaviorBill (DEPLOY.md)

Это официальное практическое руководство по установке, настройке и эксплуатации биллинговой платформы **SaviorBill** в производственной среде.

Документ содержит следующие разделы:
1. **[Часть 1: Развёртывание на одном сервере (All-in-One)](#часть-1-развёртывание-на-одном-сервере-all-in-one)** — базовый вариант для запуска всех компонентов платформы на едином хосте с изоляцией сервисов в Docker.
2. **[Часть 2: Развёртывание на нескольких серверах (Multi-Node / High Availability)](#часть-2-развёртывание-на-нескольких-серверах-multi-node)** — распределённая архитектура для изоляции зон ответственности, горизонтального масштабирования вычислительных воркеров и повышенной надёжности.
3. **[Часть 3: Чек-лист безопасности перед запуском в продакшн](#часть-3-чек-лист-безопасности-перед-go-live)**.

---

## Архитектура компонентов SaviorBill

Перед развёртыванием важно понимать, как взаимодействуют сервисы:

```text
                           ┌───────────────────────────────┐
                           │      Интернет / Клиенты       │
                           └───────────────┬───────────────┘
                                           │ HTTPS (443)
                                           ▼
                           ┌───────────────────────────────┐
                           │  Reverse Proxy (Caddy/Nginx)  │
                           └───────┬───────────────┬───────┘
                     /api, /ws, UI │               │ /media, /uploads
                                   ▼               ▼
                       ┌────────────────┐    ┌─────────────────┐
                       │    billing     │    │   mediaworker   │
                       │ (FastAPI:8000) │    │  (FastAPI:8001) │
                       └───────┬────────┘    └────────┬────────┘
                               │                      │
        ┌──────────────────────┼──────────────────────┼──────────────────────┐
        │                      │                      │                      │
        ▼                      ▼                      ▼                      ▼
┌──────────────┐       ┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│  PostgreSQL  │       │    Valkey    │       │  luaworker   │       │   Хранилище  │
│  (БД: 5432)  │       │(Шина/Кэш:6379│◄─────►│ (Реплики xN) │       │   (FS / S3)  │
└──────────────┘       └──────────────┘       └──────────────┘       └──────────────┘
```

* **billing** (FastAPI): ядро системы, API, авторизация (JWT RS256), админ-панель (React SPA), планировщик жизненного цикла и списаний (`BillingLoop`), работа с PostgreSQL.
* **luaworker** (Lua 5.4 / LuaJIT): изолированная среда исполнения скриптов жизненного цикла услуг (`create`, `renew`, `freeze`, `unfreeze`, `delete`), обработки триггеров остатков, интеграций с внешними API и фоновых задач. Получает задания из шины `lua:tasks` в Valkey. **Масштабируется горизонтально.**
* **mediaworker** (Python/FastAPI): изолированный сервис загрузки и сжатия картинок (WebP/WebM) и аватарок. Получает задачи из `media:tasks`.
* **Valkey 8** (форк Redis): высокоскоростная шина сообщений (Redis Streams), распределённый кэш, блокировки и rate-limiting.
* **PostgreSQL 16**: надёжное реляционное хранилище всех транзакций, аккаунтов, услуг и системных логов.
* **Caddy / Nginx**: внешний шлюз с автоматическим выпуском SSL-сертификатов (Let's Encrypt).

---

# ЧАСТЬ 1: Развёртывание на одном сервере (All-in-One)

Данный вариант объединяет все компоненты в рамках одного сервера под управлением Docker Compose. Все внутренние порты (БД, шина, внутренние API) изолированы внутри приватной Docker-сети и не торчат наружу.

### 1.1. Системные требования

| Ресурс | Минимальная конфигурация (базовый запуск) | Рекомендуемая конфигурация для production |
| :--- | :--- | :--- |
| **ОС** | Ubuntu 22.04 / 24.04 LTS или Debian 12 | Ubuntu 24.04 LTS (x86_64 или aarch64) |
| **CPU** | 2 vCPU | 4+ vCPU |
| **RAM** | 2 GB | 4–8 GB (в зависимости от пула воркеров и нагрузки) |
| **Диск** | 20 GB NVMe/SSD | 50+ GB NVMe SSD |
| **Домены** | 2 поддомена одного домена (например, `bill.example.com` и `media.example.com`) |

> [!IMPORTANT]
> **Требование к доменам:** Основной домен (`DOMAIN`) и медиа-домен (`MEDIA_DOMAIN`) **обязаны быть поддоменами одного корневого домена** (например, `bill.example.com` и `media.example.com`). Это критично, так как защищённые `httpOnly` куки авторизации ставятся на родительский домен `.example.com`, чтобы MediaWorker мог валидировать сессию без лишних запросов к биллингу.

---

### 1.2. Базовая настройка сервера

Подключитесь к серверу по SSH:

```bash
# 1. Обновление пакетов
apt-get update && apt-get upgrade -y

# 2. Установка базовых утилит
apt-get install -y curl git ufw jq openssl ca-certificates gnupg lsb-release

# 3. Настройка Firewall (UFW)
# Открываем только SSH, HTTP и HTTPS. Порты БД (5432) и Valkey (6379) должны быть закрыты от внешнего мира.
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH'
ufw allow 80/tcp comment 'HTTP Let Encrypt'
ufw allow 443/tcp comment 'HTTPS'
ufw allow 443/udp comment 'HTTP/3 QUIC'
ufw --force enable

# 4. Установка официального Docker и Docker Compose
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

systemctl enable --now docker
```

---

### 1.3. Клонирование проекта и структура папок

```bash
# Клонируем проект в /opt/saviorbill
git clone https://github.com/unvislate/SaviorBill.git /opt/saviorbill
cd /opt/saviorbill

# Создаём необходимые директории хранения данных
mkdir -p data/email data/lua data/media data/uploads data/keys
mkdir -p data-private
mkdir -p backups

# Защищаем директорию с приватными секретами
chmod 700 data-private
```

---

### 1.4. Генерация секретов и настройка `.env`

Создайте рабочий файл `.env` на основе примера:

```bash
cp deploy/.env.example deploy/.env
```

Сгенерируйте криптографические ключи и пароли:

```bash
# Сгенерировать надёжный пароль для PostgreSQL
NEW_DB_PASS=$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9')
echo "Сгенерирован DB_PASS: $NEW_DB_PASS"

# Сгенерировать ключ подписи шины межсервисных сообщений (HMAC-SHA256)
NEW_BUS_KEY=$(openssl rand -hex 32)
echo "Сгенерирован BUS_SIGNING_KEY: $NEW_BUS_KEY"
```

Отредактируйте `deploy/.env`:

```ini
# ==============================================================================
# БАЗОВЫЕ НАСТРОЙКИ СЕТИ И ДОМЕНОВ
# ==============================================================================
DEBUG=false
PUBLIC_URL=https://bill.example.com
MEDIA_PUBLIC_URL=https://media.example.com

DOMAIN=bill.example.com
MEDIA_DOMAIN=media.example.com

# IP адрес или CIDR-подсеть Docker-сети для доверенного проксирования
# Внимание: НЕ ставить "*"! По умолчанию подсеть docker compose: 172.16.0.0/12
TRUSTED_PROXIES=172.16.0.0/12,127.0.0.1

# ==============================================================================
# БАЗА ДАННЫХ (PostgreSQL 16)
# ==============================================================================
DB_HOST=db
DB_PORT=5432
DB_USER=saviorbill
DB_PASS=ВСТАВЬТЕ_СЮДА_СГЕНЕРИРОВАННЫЙ_NEW_DB_PASS
DB_NAME=saviorbill

# ==============================================================================
# ШИНА СООБЩЕНИЙ И КЭШ (Valkey 8)
# ==============================================================================
VALKEY_HOST=valkey
VALKEY_PORT=6379
VALKEY_DB=0

# Общий HMAC-ключ шины (обязателен при DEBUG=false!)
BUS_SIGNING_KEY=ВСТАВЬТЕ_СЮДА_СГЕНЕРИРОВАННЫЙ_NEW_BUS_KEY

# ==============================================================================
# УПРАВЛЕНИЕ СЕКРЕТАМИ И КЛЮЧАМИ
# ==============================================================================
SECRETS_BACKEND=file
DATA_DIR=/app/data
PRIVATE_DATA_DIR=/app/private

# Ключи RS256 JWT и Fernet SECRETS_KEY НЕ нужно указывать вручную:
# Они автоматически сгенерируются в криптографически стойком виде при первом запуске
# и сохранятся в data-private/.

# ==============================================================================
# ПЕРВЫЙ СУПЕРАДМИНИСТРАТОР (SEED)
# ==============================================================================
OWNER_LOGIN=owner
OWNER_PASS=УкажитеСложныйПарольАдминистратора
OWNER_EMAIL=admin@example.com
```

---

### 1.5. Настройка Caddyfile (Reverse Proxy & Auto-SSL)

Файл `deploy/Caddyfile` уже преднастроен. Убедитесь, что он выглядит следующим образом:

```caddyfile
{$DOMAIN} {
    encode zstd gzip

    # Защита внутренних служебных эндпоинтов от внешнего доступа
    handle /metrics {
        respond "Not Found" 404
    }

    # Перенаправление всех остальных запросов на Billing
    handle {
        reverse_proxy billing:8000 {
            header_up X-Forwarded-Proto {scheme}
            header_up X-Real-IP {remote_host}
        }
    }
}

{$MEDIA_DOMAIN} {
    encode zstd gzip

    handle /metrics {
        respond "Not Found" 404
    }

    # Перенаправление запросов на обработчик медиа
    handle {
        reverse_proxy mediaworker:8001 {
            header_up X-Forwarded-Proto {scheme}
            header_up X-Real-IP {remote_host}
        }
    }
}
```

> [!TIP]
> Caddy автоматически свяжется с серверами Let's Encrypt и выпустит бесплатные TLS/SSL сертификаты для указанных доменов, как только вы направите A-записи доменов на IP вашего сервера.

---

### 1.6. Запуск инфраструктуры и масштабирование воркеров

Перейдите в директорию `deploy` и выполните запуск:

```bash
cd /opt/saviorbill/deploy

# Запуск контейнеров с масштабированием LuaWorker до нужного количества реплик
docker compose -f docker-compose.yml --env-file .env up -d --scale luaworker=4
```

Проверьте статус запущенных контейнеров:

```bash
docker compose ps
```

Вы должны увидеть:
* `saviorpg` (PostgreSQL 16) — status `healthy`
* `saviorvalkey` (Valkey 8) — status `healthy`
* `saviorbill` (Billing Engine) — status `healthy`
* `saviormedia` (MediaWorker) — status `healthy`
* `saviorlua` (реплики luaworker) — status `running`
* `saviorcaddy` (Caddy) — status `running`, порты 80, 443

Логи инициализации:

```bash
docker compose logs -f billing
```

После завершения инициализации откройте в браузере `https://bill.example.com` и авторизуйтесь под администратором.

---

### 1.7. Автоматизация резервного копирования (Backup Cron)

Создайте скрипт ежедневного резервного копирования `/opt/saviorbill/backup.sh`:

```bash
cat << 'EOF' > /opt/saviorbill/backup.sh
#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="/opt/saviorbill/backups"
DATE=$(date +%Y%m%d_%H%M%S)
TARGET_DIR="${BACKUP_DIR}/${DATE}"

mkdir -p "${TARGET_DIR}"

echo "[${DATE}] Запуск резервного копирования SaviorBill..."

# 1. Дамп базы данных PostgreSQL в сжатый архив
docker exec saviorpg pg_dump -U saviorbill saviorbill | gzip > "${TARGET_DIR}/database.sql.gz"

# 2. Бэкап приватных ключей и секретов (КРИТИЧЕСКИ ВАЖНО!)
tar -czf "${TARGET_DIR}/data-private.tar.gz" -C /opt/saviorbill data-private

# 3. Бэкап шаблонов писем и Lua-скриптов
tar -czf "${TARGET_DIR}/data-scripts.tar.gz" -C /opt/saviorbill/data email lua

# 4. Удаление бэкапов старше 14 дней
find "${BACKUP_DIR}" -maxdepth 1 -type d -mtime +14 -exec rm -rf {} +

echo "[$(date +%Y%m%d_%H%M%S)] Резервное копирование успешно завершено в ${TARGET_DIR}."
EOF

chmod +x /opt/saviorbill/backup.sh
```

Добавьте задание в `crontab` для выполнения каждую ночь в 03:00:

```bash
(crontab -l 2>/dev/null; echo "0 3 * * * /opt/saviorbill/backup.sh >> /var/log/saviorbill_backup.log 2>&1") | crontab -
```

---

# ЧАСТЬ 2: Развёртывание на нескольких серверах (Multi-Node)

Для распределённых систем, горизонтального масштабирования вычислительных ресурсов, изоляции сетевых контуров и отказоустойчивости рекомендуется многонодовая архитектура.

### 2.1. Топология распределённого кластера

Схема разделения по ролям серверов:

```text
               ┌────────────────────────────────────────────────────────┐
               │         СЕРВЕР 1: Web & Edge (API Gateway)             │
               │   Caddy + Billing (FastAPI) + AdminUI (Static)         │
               └───────────────────────────┬────────────────────────────┘
                                           │
                      Приватный зашифрованный WireGuard Mesh
                         (10.10.0.0/24 — Нет доступа извне)
                                           │
         ┌─────────────────────────────────┴─────────────────────────────────┐
         │                                                                   │
         ▼                                                                   ▼
┌──────────────────────────────────┐               ┌──────────────────────────────────┐
│   СЕРВЕР 2: Data & State Core    │               │  СЕРВЕР 3: Compute / Lua Cluster │
│  PostgreSQL 16 + Valkey 8 Engine │               │  Luaworker (Реплики процессов)   │
└──────────────────────────────────┘               └──────────────────────────────────┘
                                                                     │
                                                   ┌─────────────────┴────────────────┐
                                                   │   СЕРВЕР 4 (или S3 Хранилище)    │
                                                   │   MediaWorker + S3 Bucket        │
                                                   └──────────────────────────────────┘
```

1. **Сервер 1 (Web/API):** Публичный шлюз. Принимает внешние клиентские запросы, раздаёт веб-интерфейс, исполняет ядро биллинга.
2. **Сервер 2 (Data Core):** Изолированный сервер данных. **Не имеет публичных портов** (доступ только через защищённую приватную сеть). На нём работают PostgreSQL и Valkey.
3. **Сервер 3 (Compute):** Вычислительная нода. Не хранит персистентных данных БД. Подключается к Valkey на Сервере 2 и параллельно исполняет скрипты услуг, триггеры и внешние сетевые вызовы.
4. **Облачное хранилище S3:** Файлы картинок и медиа хранятся в совместимом S3-хранилище (Cloudflare R2, MinIO, AWS S3).

---

### 2.2. Настройка приватной сети WireGuard (Приватный оверлей)

Все ноды общаются через зашифрованную подсеть `10.10.0.0/24`. Установите WireGuard на каждом сервере:

```bash
apt-get install -y wireguard
```

Сгенерируйте ключи на каждом сервере:
```bash
wg genkey | tee privatekey | wg pubkey > publickey
```

Пример адресации:
* **Сервер 2 (Data Core):** `10.10.0.2`
* **Сервер 1 (Billing API):** `10.10.0.1`
* **Сервер 3 (Lua Workers):** `10.10.0.3`
* **Сервер 4 (Media Worker):** `10.10.0.4`

Конфиг WireGuard на **Сервере 2 (Data Core)** (`/etc/wireguard/wg0.conf`):
```ini
[Interface]
Address = 10.10.0.2/24
ListenPort = 51820
PrivateKey = <Приватный_ключ_Сервера_2>

# Клиент 1: Billing API
[Peer]
PublicKey = <Публичный_ключ_Сервера_1>
AllowedIPs = 10.10.0.1/32

# Клиент 2: Lua Worker
[Peer]
PublicKey = <Публичный_ключ_Сервера_3>
AllowedIPs = 10.10.0.3/32
```

Запуск WireGuard:
```bash
systemctl enable --now wg-quick@wg0
```

---

### 2.3. Настройка Сервера 2: Data Core (PostgreSQL + Valkey)

На Сервере 2 запускаются только сервисы хранения состояния. Создайте `/opt/saviorbill-data/docker-compose.yml`:

```yaml
services:
  db:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: saviorbill
      POSTGRES_PASSWORD: StrongClusterPassword123
      POSTGRES_DB: saviorbill
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      # Слушаем ТОЛЬКО на приватном IP WireGuard!
      - "10.10.0.2:5432:5432"

  valkey:
    image: valkey/valkey:8-alpine
    restart: unless-stopped
    command: [
      "valkey-server",
      "--save", "60", "1",
      "--appendonly", "yes",
      "--protected-mode", "no",
      "--bind", "10.10.0.2 127.0.0.1"
    ]
    volumes:
      - valkeydata:/data
    ports:
      # Слушаем ТОЛЬКО на приватном IP WireGuard!
      - "10.10.0.2:6379:6379"

volumes:
  pgdata:
  valkeydata:
```

Запуск:
```bash
docker compose up -d
```

---

### 2.4. Настройка Сервера 1: Billing Engine & Web Gateway

На Сервере 1 создайте `.env`:

```ini
DEBUG=false
PUBLIC_URL=https://bill.example.com
MEDIA_PUBLIC_URL=https://media.example.com
DOMAIN=bill.example.com
MEDIA_DOMAIN=media.example.com

# Подключение к Серверу 2 по приватному WireGuard IP:
DB_HOST=10.10.0.2
DB_PORT=5432
DB_USER=saviorbill
DB_PASS=StrongClusterPassword123
DB_NAME=saviorbill

VALKEY_HOST=10.10.0.2
VALKEY_PORT=6379

# Общий ключ кластера:
BUS_SIGNING_KEY=94c502b48455648e580e017688439df689e4975079a4059d0a649366d7adbc41

TRUSTED_PROXIES=127.0.0.1,172.16.0.0/12
SECRETS_BACKEND=file
PRIVATE_DATA_DIR=/app/private
```

В `docker-compose.yml` на Сервере 1 остаются только:
* `caddy` (порты 80, 443)
* `billing` (FastAPI)

Приватные ключи JWT (`data-private/`) хранятся **исключительно на Сервере 1**.

---

### 2.5. Настройка Сервера 3: Кластер LuaWorker

На вычислительной ноде создайте `docker-compose.yml`:

```yaml
services:
  luaworker:
    image: ghcr.io/unvislate/saviorbill/luaworker:latest
    restart: unless-stopped
    environment:
      # Подключение к Valkey на Сервере 2
      VALKEY_HOST: 10.10.0.2
      VALKEY_PORT: 6379
      VALKEY_DB: 0
      LUA_TASK_STREAM: lua:tasks
      LUA_RESP_STREAM: lua:results
      LUA_GROUP: luaworkers
      # Тот же самый ключ шины, что и на Billing!
      BUS_SIGNING_KEY: 94c502b48455648e580e017688439df689e4975079a4059d0a649366d7adbc41
      LUA_SCRIPTS_DIR: /app/data/lua
      LUA_HTTP_TIMEOUT: 15
    volumes:
      - ./data/lua:/app/data/lua:ro

    deploy:
      replicas: 8
```

Запуск параллельных воркеров:
```bash
docker compose up -d
```

> [!NOTE]
> **Автоматическая балансировка:** Благодаря механизму Consumer Groups в Redis Streams, Valkey сам равномерно раздаёт задачи между всеми запущенными воркерами Сервера 3. При добавлении дополнительных вычислительных нод пропускная способность очереди масштабируется линейно без необходимости перезагружать существующие сервисы.

---

### 2.6. Переключение медиа на S3 (Cloudflare R2 / AWS S3 / MinIO)

При распределённом развёртывании файловая система не разделяется между серверами, поэтому медиафайлы переводятся в объектное S3-хранилище.

В `.env` для `billing` и `mediaworker` пропишите:

```ini
STORAGE_BACKEND=s3
S3_ENDPOINT=https://<account-id>.r2.cloudflarestorage.com
S3_BUCKET=saviorbill-media
S3_REGION=auto
S3_KEY=ваш_access_key
S3_SECRET=ваш_secret_key
S3_PUBLIC_URL=https://cdn-media.example.com
```

* `mediaworker` сжимает загружаемые изображения в WebP и выгружает напрямую в S3 бакет.
* Ссылка на файл формируется через CDN или публичный URL хранилища.

---

# ЧАСТЬ 3: Чек-лист безопасности перед Go-Live

Перед запуском платформы в промышленную эксплуатацию убедитесь, что выполнены все пункты:

- [ ] **Режим Debug выключен:** в `.env` установлено `DEBUG=false` и `MEDIA_DEBUG=false`.
- [ ] **Шина защищена:** сгенерирован и установлен непустой `BUS_SIGNING_KEY` (длиной не менее 32 байт).
- [ ] **База данных защищена:** изменён стандартный пароль `DB_PASS`, порт 5432 закрыт от внешнего мира через UFW или слушает только приватный интерфейс.
- [ ] **Доверенные прокси настроены:** параметр `TRUSTED_PROXIES` задан строго (IP Caddy или подсеть Docker), значение `*` категорически запрещено.
- [ ] **Приватные ключи изолированы:** директория `data-private/` имеет права `chmod 700` и смонтирована только в контейнер `billing`.
- [ ] **Сменен дефолтный пароль:** пароль учетной записи `owner` изменён на надёжный.
- [ ] **Настроено резервное копирование:** проверена работа скрипта `backup.sh`, бэкап базы данных и каталога `data-private/` успешно протестирован на восстановление.
- [ ] **Включен системный мониторинг:** настроены алерты по месту на диске (`df -h`) и потреблению RAM.
