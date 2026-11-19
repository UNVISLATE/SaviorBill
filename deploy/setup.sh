#!/usr/bin/env bash
# ==============================================================================
# SaviorBill — Интерактивный мастер развертывания и управления (Deploy Wizard)
# ==============================================================================
# Использование:
#   curl -fsSL https://get.saviorbill.com | bash
# или:
#   bash <(curl -fsSL https://raw.githubusercontent.com/UNVISLATE/SaviorBill/master/deploy/setup.sh)
# Скрипт автоматически гарантирует установку и работу стека в /opt/saviorbill
# ==============================================================================

set -euo pipefail

# Если запуск через пайп (curl ... | bash), перенаправляем stdin на tty (если tty доступен)
if [ ! -t 0 ] && (exec < /dev/tty) 2>/dev/null; then
  exec < /dev/tty
fi

# ── Цвета и стили ─────────────────────────────────────────────────────────────
if [ -t 1 ]; then
  BOLD='\033[1m'
  CYAN='\033[0;36m'
  GREEN='\033[0;32m'
  YELLOW='\033[1;33m'
  RED='\033[0;31m'
  MAGENTA='\033[0;35m'
  BLUE='\033[0;34m'
  DIM='\033[2m'
  RESET='\033[0m'
else
  BOLD='' CYAN='' GREEN='' YELLOW='' RED='' MAGENTA='' BLUE='' DIM='' RESET=''
fi

RAW_BASE="https://raw.githubusercontent.com/UNVISLATE/SaviorBill/master/deploy"
INSTALL_DIR="${SAVIORBILL_DIR:-/opt/saviorbill}"

info()    { printf "${CYAN}ℹ %s${RESET}\n" "$*"; }
success() { printf "${GREEN}✔ %s${RESET}\n" "$*"; }
warn()    { printf "${YELLOW}⚠ %s${RESET}\n" "$*"; }
err()     { printf "${RED}✖ %s${RESET}\n" "$*" >&2; }
step()    { printf "\n${BOLD}${MAGENTA}── %s ──${RESET}\n" "$*"; }

prompt_default() {
  local prompt="$1"
  local default="$2"
  local answer=""
  printf "${BOLD}%s${RESET} ${DIM}[%s]${RESET}: " "$prompt" "$default"
  read -r answer
  echo "${answer:-$default}"
}

prompt_secret_or_gen() {
  local prompt="$1"
  local generated="$2"
  local answer=""
  printf "${BOLD}%s${RESET} ${DIM}[Enter = использовать '%s']${RESET}: " "$prompt" "$generated"
  read -r answer
  echo "${answer:-$generated}"
}

generate_hex() {
  local bytes="${1:-32}"
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex "$bytes"
  elif command -v python3 >/dev/null 2>&1; then
    python3 -c "import secrets; print(secrets.token_hex($bytes))"
  elif command -v python >/dev/null 2>&1; then
    python -c "import secrets; print(secrets.token_hex($bytes))"
  else
    head -c "$bytes" /dev/urandom | od -An -tx1 | tr -d ' \n'
  fi
}

generate_pass() {
  local len="${1:-16}"
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -base64 32 | tr -dc 'a-zA-Z0-9' | head -c "$len"
  elif command -v python3 >/dev/null 2>&1; then
    python3 -c "import secrets, string; alphabet = string.ascii_letters + string.digits; print(''.join(secrets.choice(alphabet) for _ in range($len)))"
  elif command -v python >/dev/null 2>&1; then
    python -c "import secrets, string; alphabet = string.ascii_letters + string.digits; print(''.join(secrets.choice(alphabet) for _ in range($len)))"
  else
    tr -dc 'a-zA-Z0-9' < /dev/urandom | head -c "$len"
  fi
}

get_root_domain() {
  local dom="$1"
  dom="${dom%%:*}"
  dom="$(echo "$dom" | tr '[:upper:]' '[:lower:]' | xargs)"
  if [[ "$dom" == "localhost" || "$dom" == *.localhost ]]; then
    echo "localhost"
    return
  fi
  # Если это IP
  if [[ "$dom" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "$dom"
    return
  fi
  # Иначе последние 2 части
  local p1 p2
  p1=$(echo "$dom" | awk -F. '{if (NF>=2) print $(NF-1)"."$NF; else print $0}')
  echo "$p1"
}

set_env_var() {
  local key="$1"
  local val="$2"
  local file="${3:-.env}"
  if grep -q "^${key}=" "$file" 2>/dev/null; then
    # Используем sed с разделителем |
    local safe_val
    safe_val=$(printf '%s\n' "$val" | sed 's/[&/\]/\\&/g')
    sed -i "s|^${key}=.*|${key}=${safe_val}|" "$file"
  else
    printf '%s=%s\n' "$key" "$val" >> "$file"
  fi
}

get_env_var() {
  local key="$1"
  local file="${2:-.env}"
  if [ -f "$file" ]; then
    grep "^${key}=" "$file" 2>/dev/null | head -n1 | cut -d'=' -f2- || echo ""
  fi
}

docker_compose_cmd() {
  if docker compose version >/dev/null 2>&1; then
    docker compose "$@"
  elif command -v docker-compose >/dev/null 2>&1; then
    docker-compose "$@"
  else
    err "Команда 'docker compose' или 'docker-compose' не найдена."
    exit 1
  fi
}

print_banner() {
  clear 2>/dev/null || true
  printf "${BOLD}${CYAN}"
  cat <<'EOF'
  ____              _             ____  _ _ _ 
 / ___|  __ ___   _(_) ___  _ __ | __ )(_) | |
 \___ \ / _` \ \ / / |/ _ \| '__||  _ \| | | |
  ___) | (_| |\ V /| | (_) | |   | |_) | | | |
 |____/ \__,_| \_/ |_|\___/|_|   |____/|_|_|_|
EOF
  printf "${RESET}"
  printf "${DIM} Интерактивный мастер развертывания и управления стеком${RESET}\n\n"
}

# ── Проверка Docker ───────────────────────────────────────────────────────────
check_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    warn "Docker не обнаружен в системе."
    local ans
    ans=$(prompt_default "Установить Docker автоматически (get.docker.com)? [Y/n]" "Y")
    case "$ans" in
      [yY]|[yY][eE][sS])
        info "Установка Docker..."
        if command -v curl >/dev/null 2>&1; then
          curl -fsSL https://get.docker.com | sudo sh
        elif command -v wget >/dev/null 2>&1; then
          wget -qO- https://get.docker.com | sudo sh
        fi
        sudo usermod -aG docker "$USER" 2>/dev/null || true
        success "Docker успешно установлен!"
        ;;
      *)
        err "Для продолжения работы необходим Docker. Установите его и перезапустите скрипт."
        exit 1
        ;;
    esac
  else
    local d_ver
    d_ver=$(docker --version 2>/dev/null || echo "установлен")
    info "Docker: $d_ver"
  fi
}

# ── Гарантия установки строго в /opt/saviorbill ─────────────────────────────
ensure_install_dir() {
  local script_source=""
  if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
    script_source="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
  fi

  # Создаем целевой каталог /opt/saviorbill
  if [ ! -d "$INSTALL_DIR" ]; then
    info "Создание целевого каталога установки: $INSTALL_DIR..."
    if [ "${EUID:-$(id -u)}" -ne 0 ] && command -v sudo >/dev/null 2>&1; then
      sudo mkdir -p "$INSTALL_DIR"
      sudo chown -R "$(id -u):$(id -g)" "$INSTALL_DIR"
    else
      mkdir -p "$INSTALL_DIR"
    fi
  fi

  # Если вызов сделан из локального клона репозитория (deploy/)
  if [ -n "$script_source" ] && [ "$script_source" != "$INSTALL_DIR" ] && [ -f "$script_source/docker-compose.yml" ]; then
    info "Копирование файлов деплоя из $script_source в $INSTALL_DIR..."
    cp -n "$script_source/docker-compose.yml" "$INSTALL_DIR/" 2>/dev/null || true
    cp -n "$script_source/Caddyfile" "$INSTALL_DIR/" 2>/dev/null || true
    cp -n "$script_source/.env.example" "$INSTALL_DIR/" 2>/dev/null || true
    cp -n "$script_source/client.caddy.example" "$INSTALL_DIR/" 2>/dev/null || true
    cp -n "$script_source/media.caddy.example" "$INSTALL_DIR/" 2>/dev/null || true
    cp "$script_source/setup.sh" "$INSTALL_DIR/setup.sh" 2>/dev/null || true
    chmod +x "$INSTALL_DIR/setup.sh" 2>/dev/null || true
  fi

  # Переходим в рабочий каталог установки
  cd "$INSTALL_DIR" || {
    err "Не удалось перейти в каталог $INSTALL_DIR"
    exit 1
  }

  # Обеспечиваем наличие исполняемого setup.sh в самом каталоге установки
  if [ ! -f "$INSTALL_DIR/setup.sh" ]; then
    if [ -n "$script_source" ] && [ -f "$script_source/setup.sh" ]; then
      cp "$script_source/setup.sh" "$INSTALL_DIR/setup.sh" 2>/dev/null || true
    else
      curl -fsSL "$RAW_BASE/setup.sh" -o "$INSTALL_DIR/setup.sh" 2>/dev/null || true
    fi
    chmod +x "$INSTALL_DIR/setup.sh" 2>/dev/null || true
  fi
}

# ── Скачивание или подготовка базовых шаблонов ────────────────────────────────
prepare_base_files() {
  mkdir -p caddy.d data data-private
  chmod 700 data-private 2>/dev/null || true

  if [ ! -f "docker-compose.yml" ]; then
    info "Загрузка конфигурационных файлов из репозитория в $INSTALL_DIR..."
    curl -fsSL "$RAW_BASE/docker-compose.yml" -o docker-compose.yml
    curl -fsSL "$RAW_BASE/Caddyfile" -o Caddyfile
    curl -fsSL "$RAW_BASE/.env.example" -o .env.example
    curl -fsSL "$RAW_BASE/client.caddy.example" -o client.caddy.example 2>/dev/null || true
    curl -fsSL "$RAW_BASE/media.caddy.example" -o media.caddy.example 2>/dev/null || true
  fi

  if [ ! -f "media.caddy.example" ]; then
    cat <<'EOF' > media.caddy.example
{$MEDIA_DOMAIN:media.localhost} {
	encode zstd gzip

	handle /metrics {
		respond "not found" 404
	}

	handle {
		reverse_proxy mediaworker:8001
	}
}
EOF
  fi

  if [ ! -f "client.caddy.example" ]; then
    cat <<'EOF' > client.caddy.example
{$CLIENT_DOMAIN:shop.localhost} {
	encode zstd gzip

	handle /metrics {
		respond "not found" 404
	}

	handle /api/media/* {
		reverse_proxy mediaworker:8001
	}

	handle /api/* {
		reverse_proxy billing:8000
	}

	handle /ws/* {
		reverse_proxy billing:8000
	}

	handle {
		reverse_proxy clientui:80
	}
}
EOF
  fi
}

# ── Показ карточки доступа ────────────────────────────────────────────────────
show_summary_card() {
  local domain media_domain client_domain owner_login owner_pass owner_email client_profile http_port https_port debug_mode
  domain="$(get_env_var "DOMAIN")"
  media_domain="$(get_env_var "MEDIA_DOMAIN")"
  client_domain="$(get_env_var "CLIENT_DOMAIN")"
  owner_login="$(get_env_var "OWNER_LOGIN")"
  owner_pass="$(get_env_var "OWNER_PASS")"
  owner_email="$(get_env_var "OWNER_EMAIL")"
  client_profile="$(get_env_var "COMPOSE_PROFILES")"
  http_port="$(get_env_var "HTTP_PORT")"
  https_port="$(get_env_var "HTTPS_PORT")"
  debug_mode="$(get_env_var "DEBUG")"

  http_port="${http_port:-80}"
  https_port="${https_port:-443}"
  debug_mode="${debug_mode:-false}"

  local proto="https"
  local port_suffix=""
  if [ "$debug_mode" = "true" ] || [[ "$domain" == "localhost" || "$domain" == 127.0.0.1* || "$domain" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    proto="http"
    if [ "$http_port" != "80" ]; then
      port_suffix=":$http_port"
    fi
  fi

  printf "\n${BOLD}${GREEN}┌────────────────────────────────────────────────────────────────────────┐${RESET}\n"
  printf "${BOLD}${GREEN}│                 ✓ SaviorBill настроен и готов к работе!               │${RESET}\n"
  printf "${BOLD}${GREEN}├────────────────────────────────────────────────────────────────────────┤${RESET}\n"
  printf "│  ${BOLD}Панель управления (Admin UI):${RESET} %-40s│\n" "${proto}://${domain}${port_suffix}/"
  if [[ "$client_profile" == *"client"* ]]; then
    local client_proto="$proto"
    local client_url=""
    if [[ "$client_domain" == :* ]]; then
      client_url="${proto}://${domain}${client_domain}/"
    else
      client_url="${proto}://${client_domain}${port_suffix}/"
    fi
    printf "│  ${BOLD}Личный Кабинет (Client UI):${RESET}   %-40s│\n" "$client_url"
  fi
  printf "│  ${BOLD}REST API Swagger Docs:${RESET}        %-40s│\n" "${proto}://${domain}${port_suffix}/api/docs"
  printf "│  ${BOLD}API Health Check:${RESET}             %-40s│\n" "${proto}://${domain}${port_suffix}/api/health"
  printf "${BOLD}${GREEN}├────────────────────────────────────────────────────────────────────────┤${RESET}\n"
  printf "│  ${BOLD}Логин владельца (Owner):${RESET}      %-40s│\n" "${owner_login:-owner}"
  printf "│  ${BOLD}Пароль владельца:${RESET}             %-40s│\n" "${owner_pass:-[задан в .env]}"
  printf "│  ${BOLD}Email владельца:${RESET}              %-40s│\n" "${owner_email:-owner@example.com}"
  printf "${BOLD}${GREEN}├────────────────────────────────────────────────────────────────────────┤${RESET}\n"
  printf "│  ${BOLD}Каталог установки:${RESET}            %-40s│\n" "$INSTALL_DIR"
  printf "│  ${BOLD}Управление стеком:${RESET}            %-40s│\n" "cd $INSTALL_DIR && ./setup.sh"
  printf "${BOLD}${GREEN}└────────────────────────────────────────────────────────────────────────┘${RESET}\n"
}

# ── Мастер настройки (Wizard) ────────────────────────────────────────────────
run_wizard() {
  print_banner
  check_docker
  prepare_base_files

  step "1. Выбор режима окружения"
  echo "   [1] Production — Боевой сервер со своими доменами и автоматическим HTTPS (SSL)"
  echo "   [2] Local / IP — Локальный или тестовый запуск (localhost, 127.0.0.1 или IP без SSL)"
  
  local env_choice
  env_choice=$(prompt_default "Выберите вариант [1/2]" "1")

  local domain=""
  local media_domain=""
  local client_domain=""
  local owner_email=""
  local http_port="80"
  local https_port="443"
  local is_debug="false"

  case "$env_choice" in
    2)
      # Local / IP
      step "2. Настройка адреса (Local / IP)"
      local host_input
      host_input=$(prompt_default "Адрес хоста (localhost, 127.0.0.1 или IP)" "localhost")
      domain="$host_input"
      is_debug="true"

      if [[ "$domain" == "localhost" || "$domain" == *.localhost ]]; then
        media_domain="media.localhost"
        owner_email=$(prompt_default "Email администратора" "owner@localhost.test")
      else
        media_domain="$domain"
        owner_email=$(prompt_default "Email администратора" "owner@${domain}.test")
      fi

      http_port=$(prompt_default "HTTP порт для веб-сервера (Caddy)" "80")
      ;;
    *)
      # Production
      step "2. Настройка доменных имён (Production)"
      info "Для боевого сервера требуются привязанные домены, смотрящие на этот сервер."
      while true; do
        domain=$(prompt_default "Основной домен (Admin UI + API, напр. admin.myshop.com или panel.myshop.ru)" "")
        if [ -n "$domain" ]; then break; fi
        err "Основной домен не может быть пустым!"
      done

      local root_d
      root_d="$(get_root_domain "$domain")"

      local default_media="media.${root_d}"
      media_domain=$(prompt_default "Домен для медиа (Mediaworker)" "$default_media")

      while true; do
        owner_email=$(prompt_default "Email владельца (используется для Let's Encrypt SSL)" "admin@${root_d}")
        if [[ "$owner_email" == *"@"* ]]; then break; fi
        err "Пожалуйста, введите корректный адрес email."
      done

      http_port=$(prompt_default "Внешний HTTP порт Caddy" "80")
      https_port=$(prompt_default "Внешний HTTPS порт Caddy" "443")
      is_debug="false"
      ;;
  esac

  # ── Клиентский фронтенд ─────────────────────────────────────────────────────
  step "3. Клиентский фронтенд (Личный Кабинет)"
  echo "Личный Кабинет (SBPersonalAccountClient) позволяет покупателям просматривать каталог,"
  echo "делать заказы, пополнять баланс и управлять своими услугами."
  local want_client
  want_client=$(prompt_default "Установить клиентский фронтенд? [Y/n]" "Y")

  local enable_client=0
  local client_override_port=""
  case "$want_client" in
    [yY]|[yY][eE][sS])
      enable_client=1
      if [ "$env_choice" = "1" ]; then
        # Production
        local root_d
        root_d="$(get_root_domain "$domain")"
        client_domain=$(prompt_default "Домен клиентского кабинета" "shop.${root_d}")
      else
        # Local / IP
        if [[ "$domain" == "localhost" || "$domain" == *.localhost ]]; then
          echo "   [1] Поддомен http://shop.localhost:${http_port} (браузеры открывают без правок hosts)"
          echo "   [2] Отдельный порт http://localhost:3000"
          local cl_mode
          cl_mode=$(prompt_default "Выберите вариант доступа для клиента [1/2]" "1")
          if [ "$cl_mode" = "2" ]; then
            client_domain=":3000"
            client_override_port="3000"
          else
            client_domain="shop.localhost"
          fi
        else
          info "Для доступа по IP клиент будет доступен на порту :3000."
          client_domain=":3000"
          client_override_port="3000"
        fi
      fi
      ;;
    *)
      enable_client=0
      info "Клиентский фронтенд устанавливаться не будет (только API и Admin UI)."
      ;;
  esac

  # ── Учётные данные и безопасность ───────────────────────────────────────────
  step "4. Безопасность и пароли"
  
  local gen_db_pass
  gen_db_pass="$(generate_pass 24)"
  local db_pass
  db_pass=$(prompt_secret_or_gen "Пароль базы данных PostgreSQL" "$gen_db_pass")

  local bus_key
  bus_key="$(generate_hex 32)"

  local owner_login
  owner_login=$(prompt_default "Логин администратора" "owner")

  local gen_owner_pass
  gen_owner_pass="$(generate_pass 14)"
  local owner_pass
  owner_pass=$(prompt_secret_or_gen "Пароль администратора" "$gen_owner_pass")

  # ── Формирование .env ───────────────────────────────────────────────────────
  step "5. Запись конфигурации"

  if [ ! -f .env ]; then
    cp .env.example .env
  fi

  set_env_var "DEBUG" "$is_debug"
  set_env_var "DOMAIN" "$domain"
  set_env_var "MEDIA_DOMAIN" "$media_domain"
  set_env_var "HTTP_PORT" "$http_port"
  set_env_var "HTTPS_PORT" "$https_port"

  local proto_scheme="https"
  if [ "$is_debug" = "true" ] || [[ "$domain" == "localhost" || "$domain" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    proto_scheme="http"
  fi

  local pub_port=""
  if [ "$http_port" != "80" ] && [ "$proto_scheme" = "http" ]; then
    pub_port=":$http_port"
  fi

  set_env_var "PUBLIC_URL" "${proto_scheme}://${domain}${pub_port}"
  if [ "$media_domain" = "$domain" ]; then
    set_env_var "MEDIA_PUBLIC_URL" "${proto_scheme}://${domain}${pub_port}/api/media"
  else
    set_env_var "MEDIA_PUBLIC_URL" "${proto_scheme}://${media_domain}${pub_port}"
  fi

  set_env_var "DB_PASS" "$db_pass"
  set_env_var "BUS_SIGNING_KEY" "$bus_key"
  set_env_var "OWNER_LOGIN" "$owner_login"
  set_env_var "OWNER_PASS" "$owner_pass"
  set_env_var "OWNER_EMAIL" "$owner_email"
  set_env_var "TRUSTED_PROXIES" "172.16.0.0/12,10.0.0.0/8,192.168.0.0/16,127.0.0.1"
  set_env_var "DATA_HOST_DIR" "./data"
  set_env_var "PRIVATE_DATA_HOST_DIR" "./data-private"

  # Настройка Caddy для Media
  mkdir -p caddy.d
  if [ "$media_domain" != "$domain" ]; then
    cp -f media.caddy.example caddy.d/media.caddy
    info "Включён отдельный домен медиа: caddy.d/media.caddy"
  else
    rm -f caddy.d/media.caddy
    info "Медиа маршрутизируется через общий домен (/api/media/*)"
  fi

  # Настройка Caddy и Compose для Client UI
  if [ "$enable_client" -eq 1 ]; then
    set_env_var "COMPOSE_PROFILES" "client"
    set_env_var "CLIENT_DOMAIN" "$client_domain"
    cp -f client.caddy.example caddy.d/client.caddy
    if [ -n "$client_override_port" ]; then
      cat <<EOF > docker-compose.override.yml
services:
  caddy:
    ports:
      - "${client_override_port}:${client_override_port}"
EOF
      info "Создан docker-compose.override.yml для проброса порта :${client_override_port}"
    else
      rm -f docker-compose.override.yml
    fi
    info "Клиентский фронтенд включён (${client_domain})"
  else
    set_env_var "COMPOSE_PROFILES" ""
    rm -f caddy.d/client.caddy docker-compose.override.yml
  fi

  chmod 600 .env 2>/dev/null || true
  success "Конфигурация .env успешно сгенерирована!"

  show_summary_card

  step "6. Запуск стека"
  local run_now
  run_now=$(prompt_default "Запустить стек прямо сейчас? [Y/n]" "Y")
  case "$run_now" in
    [yY]|[yY][eE][sS])
      info "Скачивание последних Docker-образов..."
      docker_compose_cmd pull
      info "Запуск контейнеров..."
      docker_compose_cmd up -d
      success "Стек запущен!"
      echo ""
      docker_compose_cmd ps
      echo ""
      info "Для просмотра логов в реальном времени используйте: docker compose logs -f"
      ;;
    *)
      info "Для запуска стека вручную выполните: docker compose up -d"
      ;;
  esac
}

# ── Главное меню (если .env уже существует) ──────────────────────────────────
main_menu() {
  print_banner
  local domain
  domain="$(get_env_var "DOMAIN")"
  if [ -n "$domain" ]; then
    printf "${DIM}Текущий домен в .env: ${BOLD}%s${RESET}\n\n" "$domain"
  fi

  echo "   [1] Запустить стек (docker compose up -d)"
  echo "   [2] Остановить стек (docker compose down)"
  echo "   [3] Перезапустить стек (docker compose restart)"
  echo "   [4] Просмотреть логи (docker compose logs -f)"
  echo "   [5] Обновить образы до последней версии (pull & restart)"
  echo "   [6] Показать учетные данные и ссылки"
  echo "   [7] Перенастроить стек (запустить мастер настройки заново)"
  echo "   [0] Выход"
  echo ""

  local choice
  choice=$(prompt_default "Выберите действие [1-7, 0]" "1")

  case "$choice" in
    1)
      info "Запуск контейнеров..."
      docker_compose_cmd up -d
      success "Готово!"
      docker_compose_cmd ps
      ;;
    2)
      info "Остановка контейнеров..."
      docker_compose_cmd down
      success "Стек остановлен."
      ;;
    3)
      info "Перезапуск..."
      docker_compose_cmd restart
      success "Стек перезапущен."
      docker_compose_cmd ps
      ;;
    4)
      info "Открытие логов (Ctrl+C для выхода)..."
      docker_compose_cmd logs -f
      ;;
    5)
      info "Скачивание обновлений..."
      docker_compose_cmd pull
      info "Применение обновлений..."
      docker_compose_cmd up -d
      success "Стек обновлён до актуальных версий!"
      docker_compose_cmd ps
      ;;
    6)
      show_summary_card
      ;;
    7)
      run_wizard
      ;;
    0)
      exit 0
      ;;
    *)
      warn "Неизвестный вариант."
      ;;
  esac
}

# ── Точка входа ───────────────────────────────────────────────────────────────
ensure_install_dir

if [ -f .env ] && [ -s .env ] && [ "${1:-}" != "--reconfigure" ] && [ "${1:-}" != "-r" ]; then
  main_menu
else
  run_wizard
fi
