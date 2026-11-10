#!/usr/bin/env bash
# SaviorBill — быстрый старт.
#
# 1) Устанавливает Docker (если ещё не установлен).
# 2) Скачивает docker-compose.yml, Caddyfile и .env (из .env.example) в текущую директорию.
# 3) Просит отредактировать .env.
# 4) Показывает команды для запуска, просмотра логов и остановки.
#
# Использование:
#   mkdir -p /opt/saviorbill && cd /opt/saviorbill
#   bash <(curl -fsSL https://raw.githubusercontent.com/UNVISLATE/SaviorBill/master/deploy/setup.sh)
# или:
#   bash <(wget -qO- https://raw.githubusercontent.com/UNVISLATE/SaviorBill/master/deploy/setup.sh)
set -euo pipefail

RAW="https://raw.githubusercontent.com/UNVISLATE/SaviorBill/master/deploy"

set_env_var() {
  local key="$1"
  local val="$2"
  if grep -q "^${key}=" .env 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${val}|" .env
  else
    printf '\n%s=%s\n' "$key" "$val" >> .env
  fi
}

# ── 1. Docker ────────────────────────────────────────────────────────────────
if ! command -v docker >/dev/null 2>&1; then
  echo ">> Docker не найден — устанавливаю..."
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL https://get.docker.com | sudo sh
  elif command -v wget >/dev/null 2>&1; then
    wget -qO- https://get.docker.com | sudo sh
  else
    echo "!! Требуется curl или wget для установки Docker." >&2
    exit 1
  fi
  echo ">> Docker установлен."
else
  echo ">> Docker уже установлен: $(docker --version)"
fi

# ── 2. Файлы конфигурации ────────────────────────────────────────────────────
echo ">> Скачиваю docker-compose.yml..."
curl -fsSL "$RAW/docker-compose.yml" -o docker-compose.yml

echo ">> Скачиваю Caddyfile..."
curl -fsSL "$RAW/Caddyfile" -o Caddyfile

if [ ! -f .env ]; then
  echo ">> Скачиваю .env из .env.example..."
  curl -fsSL "$RAW/.env.example" -o .env
  if command -v openssl >/dev/null 2>&1; then
    bus_key="$(openssl rand -hex 32)"
    set_env_var "BUS_SIGNING_KEY" "$bus_key"
  fi
  echo ">> Создан .env (BUS_SIGNING_KEY сгенерирован автоматически)."
else
  echo ">> .env уже существует — оставляю как есть."
fi

# ── 2.1. Клиентский фронтенд ─────────────────────────────────────────────────
mkdir -p caddy.d
echo ""
echo ">> Выберите клиентский фронтенд для установки:"
echo "   0) Не устанавливать (только API + Admin UI)"
echo "   1) Личный Кабинет (https://github.com/UNVISLATE/SBPersonalAccountClient)"
client_choice="0"
while true; do
  read -r -p ">> Выберите вариант [0/1] (по умолчанию 0): " raw_choice
  raw_choice="${raw_choice:-0}"
  case "$raw_choice" in
    0)
      client_choice="0"
      set_env_var "COMPOSE_PROFILES" ""
      rm -f caddy.d/client.caddy
      echo ">> Выбрано: 0 — клиентский фронтенд не устанавливается."
      break
      ;;
    1)
      client_choice="1"
      set_env_var "COMPOSE_PROFILES" "client"
      set_env_var "CLIENT_IMAGE" "ghcr.io/unvislate/sbpersonalaccountclient"
      set_env_var "CLIENT_TAG" "latest"
      curl -fsSL "$RAW/client.caddy.example" -o caddy.d/client.caddy
      echo ">> Выбрано: 1 — Личный Кабинет будет установлен вместе со стеком."
      break
      ;;
    *)
      echo "!! Пожалуйста, введите 0 или 1."
      ;;
  esac
done

# ── 3. Редактирование .env ───────────────────────────────────────────────────
editor="${VISUAL:-${EDITOR:-}}"
if [ -z "$editor" ]; then
  for e in nano vim vi; do
    if command -v "$e" >/dev/null 2>&1; then editor="$e"; break; fi
  done
fi

if [ -n "$editor" ]; then
  echo ""
  echo ">> Открываю $editor — ОБЯЗАТЕЛЬНО задайте:"
  if [ "$client_choice" = "1" ]; then
    echo "     DB_PASS, DOMAIN, MEDIA_DOMAIN, CLIENT_DOMAIN, OWNER_LOGIN, OWNER_PASS, OWNER_EMAIL"
  else
    echo "     DB_PASS, DOMAIN, MEDIA_DOMAIN, OWNER_LOGIN, OWNER_PASS, OWNER_EMAIL"
  fi
  echo ""
  "$editor" .env
else
  echo ""
  echo "!! Редактор не найден. Отредактируйте .env вручную перед запуском."
  if [ "$client_choice" = "1" ]; then
    echo "   Обязательные поля: DB_PASS, DOMAIN, MEDIA_DOMAIN, CLIENT_DOMAIN, OWNER_*"
  else
    echo "   Обязательные поля: DB_PASS, DOMAIN, MEDIA_DOMAIN, OWNER_*"
  fi
  echo ""
fi

# ── 4. Инструкции ────────────────────────────────────────────────────────────
cat <<EOF

============================================================================
 Запуск стека (из текущей директории):

   docker compose pull          # скачать образы
   docker compose up -d         # запустить в фоне

 Полезные команды:

   docker compose ps            # статус контейнеров
   docker compose logs -f       # все логи (Ctrl+C для выхода)
   docker compose logs -f billing mediaworker adminui # логи конкретных сервисов
   docker compose down          # остановить стек
   docker compose pull && docker compose up -d       # обновить образы

 После запуска:
   Панель управления (Admin UI):  https://<DOMAIN>/
EOF
if [ "$client_choice" = "1" ]; then
  echo "   Личный Кабинет (Client UI):    https://<CLIENT_DOMAIN>/"
fi
cat <<'EOF'
   REST API billing:             https://<DOMAIN>/api/v1/
   Swagger billing:              https://<DOMAIN>/api/docs
   Swagger media:                https://<MEDIA_DOMAIN>/docs
   Health:                       https://<DOMAIN>/api/health
============================================================================
EOF

read -r -p ">> Запустить стек сейчас? [y/N] " ans
case "${ans:-}" in
  [yY]|[yY][eE][sS])
    docker compose pull
    docker compose up -d
    echo ">> Стек запущен. Логи: docker compose logs -f"
    ;;
  *)
    echo ">> Запустите позже: docker compose pull && docker compose up -d"
    ;;
esac
