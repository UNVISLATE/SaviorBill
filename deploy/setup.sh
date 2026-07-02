#!/usr/bin/env bash
# SaviorBill — подготовка к развёртыванию (прод).
#
# 1) создаёт deploy/.env из deploy/.env.example (если ещё нет);
# 2) открывает редактор для правки deploy/.env;
# 3) печатает команду запуска (и предлагает запустить сразу).
#
# Использование (из корня репозитория):
#   git clone https://github.com/UNVISLATE/SaviorBill.git && cd SaviorBill && bash deploy/setup.sh
set -euo pipefail

# Работаем из каталога deploy/ (где лежат .env.example и прод-compose).
cd "$(dirname "$0")"

if ! command -v docker >/dev/null 2>&1; then
  echo "!! Требуется Docker. Установка: https://docs.docker.com/engine/install/" >&2
  exit 1
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo ">> Создан deploy/.env из deploy/.env.example."
else
  echo ">> deploy/.env уже существует — оставляю как есть."
fi

# Выбираем редактор: $EDITOR/$VISUAL -> nano -> vim -> vi.
editor="${VISUAL:-${EDITOR:-}}"
if [ -z "$editor" ]; then
  for e in nano vim vi; do
    if command -v "$e" >/dev/null 2>&1; then editor="$e"; break; fi
  done
fi

if [ -n "$editor" ]; then
  echo ">> Открываю $editor для правки deploy/.env (обязательно задайте DB_PASS, OWNER_*, DOMAIN)."
  "$editor" .env
else
  echo "!! Редактор не найден — отредактируйте deploy/.env вручную перед запуском."
fi

# Мы уже в каталоге deploy/, поэтому плоский `docker compose` берёт прод-файл.
RUN_CMD="docker compose pull && docker compose up -d"

cat <<EOF

============================================================================
 Готово. Запуск в проде (образы из ghcr.io), из каталога deploy/:

     $RUN_CMD

 Из корня репозитория это эквивалентно:
     docker compose -f deploy/docker-compose.yml pull
     docker compose -f deploy/docker-compose.yml up -d

 Локальная разработка (сборка из исходников), из корня:
     docker compose -f deploy/dev/docker-compose.yml up --build       # или: make dev

 Тесты, из корня:
     docker compose -f deploy/dev/docker-compose.yml -f deploy/test/docker-compose.yml \\
         up --build --abort-on-container-exit --exit-code-from tests           # или: make test
============================================================================
EOF

read -r -p ">> Запустить прод сейчас? [y/N] " ans
case "${ans:-}" in
  [yY]|[yY][eE][sS])
    eval "$RUN_CMD"
    ;;
  *)
    echo ">> Ок. Запустите позже: $RUN_CMD"
    ;;
esac
