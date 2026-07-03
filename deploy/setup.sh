#!/usr/bin/env bash
# SaviorBill — быстрый старт (прод, без клонирования репозитория).
#
# 1) Устанавливает Docker (если ещё не установлен).
# 2) Скачивает docker-compose.yml, Caddyfile и .env (из .env.example) в текущую директорию.
# 3) Просит отредактировать .env.
# 4) Показывает команды для запуска, просмотра логов и остановки.
#
# Использование (запускать ОТ КУДА ХОТИТЕ разместить стек, например ~/saviorbill/):
#   mkdir ~/saviorbill && cd ~/saviorbill
#   bash <(curl -fsSL https://raw.githubusercontent.com/UNVISLATE/SaviorBill/main/deploy/setup.sh)
# или:
#   bash <(wget -qO- https://raw.githubusercontent.com/UNVISLATE/SaviorBill/main/deploy/setup.sh)
set -euo pipefail

RAW="https://raw.githubusercontent.com/UNVISLATE/SaviorBill/main/deploy"

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
  echo ">> Создан .env."
else
  echo ">> .env уже существует — оставляю как есть."
fi

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
  echo "     DB_PASS, DOMAIN, MEDIA_DOMAIN, OWNER_LOGIN, OWNER_PASS, OWNER_EMAIL"
  echo ""
  "$editor" .env
else
  echo ""
  echo "!! Редактор не найден. Отредактируйте .env вручную перед запуском."
  echo "   Обязательные поля: DB_PASS, DOMAIN, MEDIA_DOMAIN, OWNER_*"
  echo ""
fi

# ── 4. Инструкции ────────────────────────────────────────────────────────────
cat <<'EOF'

============================================================================
 Запуск стека (из текущей директории):

   docker compose pull          # скачать образы
   docker compose up -d         # запустить в фоне

 Полезные команды:

   docker compose ps            # статус контейнеров
   docker compose logs -f       # все логи (Ctrl+C для выхода)
   docker compose logs -f billing mediaworker   # логи конкретных сервисов
   docker compose down          # остановить стек
   docker compose pull && docker compose up -d  # обновить образы

 После запуска:
   API billing:      https://<DOMAIN>/api/v1/
   Swagger billing:  https://<DOMAIN>/docs
   Swagger media:    https://<MEDIA_DOMAIN>/docs
   Health:           https://<DOMAIN>/health
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
