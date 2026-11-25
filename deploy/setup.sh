#!/usr/bin/env bash
# ==============================================================================
# SaviorBill — Interactive Deployment & Stack Manager
# ==============================================================================
# Usage:
#   curl -fsSL https://get.saviorbill.com | bash
# or:
#   bash <(curl -fsSL https://raw.githubusercontent.com/UNVISLATE/SaviorBill/master/deploy/setup.sh)
#
# This script manages installation, configuration, and lifecycle of the
# SaviorBill billing and micro-services stack under /opt/saviorbill.
# ==============================================================================

set -euo pipefail

# Note: When run via pipe (curl ... | bash), we intentionally preserve stdin for bash
# so curl finishes streaming. Interactive prompts read directly from /dev/tty.

# ── Colors and Typography ─────────────────────────────────────────────────────
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
  local default="${2:-}"
  local answer=""
  if [ -n "$default" ]; then
    printf "${BOLD}%s${RESET} ${DIM}[%s]${RESET}: " "$prompt" "$default" >&2
  else
    printf "${BOLD}%s${RESET}: " "$prompt" >&2
  fi
  if [ -r /dev/tty ] && (true < /dev/tty) 2>/dev/null; then
    if ! IFS= read -r answer < /dev/tty; then
      echo "${default}"
      return 0
    fi
  else
    if ! IFS= read -r answer; then
      echo "${default}"
      return 0
    fi
  fi
  echo "${answer:-$default}"
}

prompt_secret_or_gen() {
  local prompt="$1"
  local generated="$2"
  local answer=""
  printf "${BOLD}%s${RESET} ${DIM}[Enter to use '%s']${RESET}: " "$prompt" "$generated" >&2
  if [ -r /dev/tty ] && (true < /dev/tty) 2>/dev/null; then
    if ! IFS= read -r answer < /dev/tty; then
      echo "${generated}"
      return 0
    fi
  else
    if ! IFS= read -r answer; then
      echo "${generated}"
      return 0
    fi
  fi
  echo "${answer:-$generated}"
}

clean_and_validate_domain() {
  local raw="$1"
  local clean=""

  # Strip leading/trailing whitespaces, tabs, carriage returns
  clean="$(echo "$raw" | tr -d '\r\n\t ')"

  # Strip schemes (http://, https://) and paths/ports
  clean="${clean#http://}"
  clean="${clean#https://}"
  clean="${clean%%/*}"
  clean="${clean%%:*}"

  # Strip any non-printable ASCII control characters (bytes 0-31 and 127)
  clean="$(echo "$clean" | tr -d '\000-\037\177')"

  # Check if contains Cyrillic or non-ASCII characters
  if LC_ALL=C echo "$clean" | grep -q '[^a-zA-Z0-9.-]'; then
    err "Invalid characters in domain: '$clean'."
    err "Only English Latin letters (a-z), numbers, dots (.), and hyphens (-) are allowed."
    if echo "$raw" | grep -q '[а-яА-ЯёЁ]'; then
      warn "Tip: Detected Cyrillic characters (e.g. 'ю' instead of '.'). Please switch to English keyboard layout."
    fi
    return 1
  fi

  # Basic syntax: at least one dot, valid hostname parts
  if [[ ! "$clean" =~ ^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$ ]]; then
    err "Invalid domain format: '$clean'. Expected format like: panel.example.com"
    return 1
  fi

  echo "$clean"
  return 0
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

detect_public_ip() {
  local ip=""
  ip="$(curl -s4 --connect-timeout 2 https://api.ipify.org 2>/dev/null || curl -s4 --connect-timeout 2 https://ifconfig.me 2>/dev/null || true)"
  if [[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+.[0-9]+$ ]]; then
    echo "$ip"
    return
  fi
  ip="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
  if [[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "$ip"
    return
  fi
  echo "localhost"
}

get_root_domain() {
  local dom="$1"
  dom="${dom%%:*}"
  dom="$(echo "$dom" | tr '[:upper:]' '[:lower:]' | xargs)"
  if [[ "$dom" == "localhost" || "$dom" == *.localhost ]]; then
    echo "localhost"
    return
  fi
  if [[ "$dom" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "$dom"
    return
  fi
  local p1
  p1=$(echo "$dom" | awk -F. '{if (NF>=2) print $(NF-1)"."$NF; else print $0}')
  echo "$p1"
}

set_env_var() {
  local key="$1"
  local val="$2"
  local file="${3:-.env}"
  if grep -q "^${key}=" "$file" 2>/dev/null; then
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
    err "Command 'docker compose' or 'docker-compose' not found."
    exit 1
  fi
}

print_banner() {
  printf "${BOLD}${CYAN}"
  cat <<'EOF'
  ____              _             ____  _ _ _ 
 / ___|  __ ___   _(_) ___  _ __ | __ )(_) | |
 \___ \ / _` \ \ / / |/ _ \| '__||  _ \| | | |
  ___) | (_| |\ V /| | (_) | |   | |_) | | | |
 |____/ \__,_| \_/ |_|\___/|_|   |____/|_|_|_|
EOF
  printf "${RESET}"
  printf "${DIM} Interactive Deployment & Production Stack Manager${RESET}\n\n"
}

# ── DPKG Lock Wait (Unattended Upgrades) ──────────────────────────────────────
wait_for_dpkg_lock() {
  local waited=0
  local max_wait=30

  while true; do
    local is_locked=0

    # Check exact process names with -x (NEVER -f, to avoid matching tail, grep or log paths)
    if command -v pgrep >/dev/null 2>&1; then
      if pgrep -x "dpkg" >/dev/null 2>&1 || \
         pgrep -x "apt-get" >/dev/null 2>&1 || \
         pgrep -x "unattended-upgr" >/dev/null 2>&1; then
        is_locked=1
      fi
    fi

    # Verify if fuser confirms the lock is actually held
    if [ "$is_locked" -eq 1 ] && command -v fuser >/dev/null 2>&1; then
      if ! fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1 && \
         ! fuser /var/lib/dpkg/lock >/dev/null 2>&1; then
        is_locked=0
      fi
    fi

    if [ "$is_locked" -eq 1 ]; then
      if [ "$waited" -eq 0 ]; then
        info "Waiting for background package manager (unattended-upgrades) to release lock..."
      fi
      sleep 2
      waited=$((waited + 2))
      if [ "$waited" -ge "$max_wait" ]; then
        warn "Proceeding with Docker installation..."
        break
      fi
    else
      if [ "$waited" -gt 0 ]; then
        success "Package manager lock released!"
      fi
      break
    fi
  done
}

# ── Docker Check ──────────────────────────────────────────────────────────────
check_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    info "Docker is not installed on this system. Installing Docker automatically..."
    wait_for_dpkg_lock
    info "Installing Docker (via get.docker.com)..."
    if command -v curl >/dev/null 2>&1; then
      curl -fsSL https://get.docker.com | sudo sh
    elif command -v wget >/dev/null 2>&1; then
      wget -qO- https://get.docker.com | sudo sh
    else
      err "Neither curl nor wget found. Please install curl or Docker manually."
      exit 1
    fi
    sudo usermod -aG docker "$USER" 2>/dev/null || true
    success "Docker installed successfully!"
  else
    local d_ver
    d_ver=$(docker --version 2>/dev/null || echo "installed")
    info "Docker detected: $d_ver"
  fi
}

# ── Target Directory Guarantee (/opt/saviorbill) ──────────────────────────────
ensure_install_dir() {
  local script_source=""
  if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
    script_source="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
  fi

  if [ ! -d "$INSTALL_DIR" ]; then
    info "Creating target deployment directory: $INSTALL_DIR..."
    if [ "${EUID:-$(id -u)}" -ne 0 ] && command -v sudo >/dev/null 2>&1; then
      sudo mkdir -p "$INSTALL_DIR"
      sudo chown -R "$(id -u):$(id -g)" "$INSTALL_DIR"
    else
      mkdir -p "$INSTALL_DIR"
    fi
  fi

  # Copy files if running from a local git clone
  if [ -n "$script_source" ] && [ "$script_source" != "$INSTALL_DIR" ] && [ -f "$script_source/docker-compose.yml" ]; then
    info "Copying deployment files from $script_source to $INSTALL_DIR..."
    cp -n "$script_source/docker-compose.yml" "$INSTALL_DIR/" 2>/dev/null || true
    cp -n "$script_source/Caddyfile" "$INSTALL_DIR/" 2>/dev/null || true
    cp -n "$script_source/.env.example" "$INSTALL_DIR/" 2>/dev/null || true
    cp -n "$script_source/client.caddy.example" "$INSTALL_DIR/" 2>/dev/null || true
    cp -n "$script_source/media.caddy.example" "$INSTALL_DIR/" 2>/dev/null || true
    cp -n "$script_source/api.caddy.example" "$INSTALL_DIR/" 2>/dev/null || true
    cp "$script_source/setup.sh" "$INSTALL_DIR/setup.sh" 2>/dev/null || true
    chmod +x "$INSTALL_DIR/setup.sh" 2>/dev/null || true
  fi

  cd "$INSTALL_DIR" || {
    err "Failed to access directory $INSTALL_DIR"
    exit 1
  }

  if [ ! -f "$INSTALL_DIR/setup.sh" ]; then
    if [ -n "$script_source" ] && [ -f "$script_source/setup.sh" ]; then
      cp "$script_source/setup.sh" "$INSTALL_DIR/setup.sh" 2>/dev/null || true
    else
      curl -fsSL "$RAW_BASE/setup.sh" -o "$INSTALL_DIR/setup.sh" 2>/dev/null || true
    fi
    chmod +x "$INSTALL_DIR/setup.sh" 2>/dev/null || true
  fi
}

# ── Base Templates Download & Preparation ─────────────────────────────────────
prepare_base_files() {
  mkdir -p caddy.d data data-private
  chmod 700 data-private 2>/dev/null || true

  if [ ! -f "docker-compose.yml" ]; then
    info "Downloading stack configuration files into $INSTALL_DIR..."
    curl -fsSL "$RAW_BASE/docker-compose.yml" -o docker-compose.yml
    curl -fsSL "$RAW_BASE/Caddyfile" -o Caddyfile
    curl -fsSL "$RAW_BASE/.env.example" -o .env.example
    curl -fsSL "$RAW_BASE/client.caddy.example" -o client.caddy.example 2>/dev/null || true
    curl -fsSL "$RAW_BASE/media.caddy.example" -o media.caddy.example 2>/dev/null || true
    curl -fsSL "$RAW_BASE/api.caddy.example" -o api.caddy.example 2>/dev/null || true
  fi

  if [ ! -f "api.caddy.example" ]; then
    cat <<'EOF' > api.caddy.example
{$API_DOMAIN:api.localhost} {
	encode zstd gzip

	handle /metrics {
		respond "not found" 404
	}

	handle /api/v1/internal/* {
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
		redir / /api/docs 302
	}
}
EOF
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

	handle /api/v1/internal/* {
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

# ── Summary Access Card ───────────────────────────────────────────────────────
show_summary_card() {
  local domain api_domain media_domain client_domain owner_login owner_pass owner_email client_profile http_port https_port debug_mode
  domain="$(get_env_var "DOMAIN")"
  api_domain="$(get_env_var "API_DOMAIN")"
  api_domain="${api_domain:-$domain}"
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
  if [ "$debug_mode" = "true" ] || [[ "$domain" == "localhost" || "$domain" == 127.0.0.1* || "$domain" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ || "$domain" == http://* ]]; then
    proto="http"
    if [ "$http_port" != "80" ]; then
      port_suffix=":$http_port"
    fi
  elif [ "$https_port" != "443" ]; then
    port_suffix=":$https_port"
  fi

  local clean_domain="${domain#http://}"
  clean_domain="${clean_domain#https://}"
  local clean_api="${api_domain#http://}"
  clean_api="${clean_api#https://}"
  local clean_media="${media_domain#http://}"
  clean_media="${clean_media#https://}"
  local clean_client="${client_domain#http://}"
  clean_client="${clean_client#https://}"

  printf "\n${BOLD}${GREEN}┌────────────────────────────────────────────────────────────────────────┐${RESET}\n"
  printf "${BOLD}${GREEN}│                 ✔ SaviorBill is deployed and operational!              │${RESET}\n"
  printf "${BOLD}${GREEN}├────────────────────────────────────────────────────────────────────────┤${RESET}\n"
  printf "│  ${BOLD}Admin Dashboard (Admin UI):${RESET}   %-39s│\n" "${proto}://${clean_domain}${port_suffix}/"
  if [ "$clean_api" != "$clean_domain" ]; then
    printf "│  ${BOLD}REST API Gateway & Webhooks:${RESET}  %-39s│\n" "${proto}://${clean_api}${port_suffix}/api/"
    printf "│  ${BOLD}REST API Swagger Docs:${RESET}        %-39s│\n" "${proto}://${clean_api}${port_suffix}/api/docs"
  else
    printf "│  ${BOLD}REST API Swagger Docs:${RESET}        %-39s│\n" "${proto}://${clean_domain}${port_suffix}/api/docs"
    printf "│  ${BOLD}API Health Check:${RESET}             %-39s│\n" "${proto}://${clean_domain}${port_suffix}/api/health"
  fi
  if [[ "$client_profile" == *"client"* ]]; then
    local client_url=""
    if [[ "$clean_client" == :* ]]; then
      client_url="${proto}://${clean_domain}${clean_client}/"
    else
      client_url="${proto}://${clean_client}${port_suffix}/"
    fi
    printf "│  ${BOLD}Customer Portal (Client UI):${RESET}  %-39s│\n" "$client_url"
  fi
  if [ "$clean_media" != "$clean_domain" ] && [ "$clean_media" != "$clean_api" ]; then
    printf "│  ${BOLD}Media Server (Mediaworker):${RESET}   %-39s│\n" "${proto}://${clean_media}${port_suffix}/"
  fi
  printf "${BOLD}${GREEN}├────────────────────────────────────────────────────────────────────────┤${RESET}\n"
  printf "│  ${BOLD}Admin Login (Owner):${RESET}          %-39s│\n" "${owner_login:-owner}"
  printf "│  ${BOLD}Admin Password:${RESET}               %-39s│\n" "${owner_pass:-[configured in .env]}"
  printf "│  ${BOLD}Admin Email:${RESET}                  %-39s│\n" "${owner_email:-owner@example.com}"
  printf "${BOLD}${GREEN}├────────────────────────────────────────────────────────────────────────┤${RESET}\n"
  printf "│  ${BOLD}Installation Directory:${RESET}       %-39s│\n" "$INSTALL_DIR"
  printf "│  ${BOLD}Stack Management CLI:${RESET}         %-39s│\n" "cd $INSTALL_DIR && ./setup.sh"
  printf "${BOLD}${GREEN}└────────────────────────────────────────────────────────────────────────┘${RESET}\n\n"
}

# ── Release Channel & Safe Update Helpers ─────────────────────────────────────
choose_release_channel() {
  local current="${1:-latest}"
  local def_choice="1"
  if [ "$current" = "nightly" ]; then
    def_choice="2"
  fi
  echo "" >&2
  echo "   [1] latest  — Stable release (recommended for production)" >&2
  echo "   [2] nightly — Pre-release / nightly build (newest features)" >&2
  local ch
  ch=$(prompt_default "Release channel [1=latest, 2=nightly]" "$def_choice")
  case "$ch" in
    2|nightly|NIGHTLY)
      echo "nightly"
      ;;
    1|latest|LATEST)
      echo "latest"
      ;;
    *)
      echo "$current"
      ;;
  esac
}

file_sha256() {
  local f="$1"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$f" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$f" | awk '{print $1}'
  else
    cksum "$f" | awk '{print $1}'
  fi
}

record_caddy_checksum() {
  local name="$1"
  local target="caddy.d/${name}.caddy"
  if [ -f "$target" ]; then
    file_sha256 "$target" > ".caddy.d.${name}.sha256" 2>/dev/null || true
  fi
}

sync_caddy_fragment() {
  local name="$1"
  local example="${name}.caddy.example"
  local target="caddy.d/${name}.caddy"
  local sum_file=".caddy.d.${name}.sha256"

  [ -f "$target" ] && [ -f "$example" ] || return 0

  if cmp -s "$target" "$example"; then
    record_caddy_checksum "$name"
    return 0
  fi

  local cur_sum old_sum=""
  cur_sum="$(file_sha256 "$target")"
  if [ -f "$sum_file" ]; then
    old_sum="$(cat "$sum_file" 2>/dev/null || true)"
  fi

  if [ -n "$old_sum" ] && [ "$cur_sum" = "$old_sum" ]; then
    cp -f "$example" "$target"
    record_caddy_checksum "$name"
    info "Updated $target from $example"
  else
    warn "Preserved customized $target (differs from template). Review $example if new routing rules are needed."
  fi
}

sync_missing_env_vars() {
  local example_file="${1:-.env.example}"
  local env_file="${2:-.env}"
  [ -f "$example_file" ] && [ -f "$env_file" ] || return 0

  local added=0
  local line key
  while IFS= read -r line || [ -n "$line" ]; do
    [[ -z "$line" || "$line" == \#* ]] && continue
    [[ "$line" != *=* ]] && continue
    key="${line%%=*}"
    [[ ! "$key" =~ ^[A-Z0-9_]+$ ]] && continue
    if ! grep -q "^${key}=" "$env_file" 2>/dev/null; then
      printf '%s\n' "$line" >> "$env_file"
      added=$((added + 1))
    fi
  done < "$example_file"

  if [ "$added" -gt 0 ]; then
    info "Added $added new default variable(s) from $example_file to $env_file"
  fi
}

backup_stack_configs() {
  local ts backup_dir
  ts="$(date +%Y%m%d-%H%M%S 2>/dev/null || echo 'latest')"
  backup_dir=".backups/update-${ts}"
  mkdir -p "$backup_dir"
  local f
  for f in docker-compose.yml Caddyfile .env .env.example api.caddy.example media.caddy.example client.caddy.example; do
    [ -f "$f" ] && cp -f "$f" "$backup_dir/" 2>/dev/null || true
  done
  if [ -d caddy.d ]; then
    cp -r caddy.d "$backup_dir/" 2>/dev/null || true
  fi
  info "Saved config backup to $backup_dir"
}

download_checked() {
  local url="$1"
  local dest="$2"
  local tmp="${dest}.tmp.$$"
  if curl -fsSL "$url" -o "$tmp" && [ -s "$tmp" ]; then
    mv -f "$tmp" "$dest"
    return 0
  fi
  rm -f "$tmp"
  return 1
}

update_stack() {
  local self_updated=0
  local auto_yes=0
  local arg_tag=""
  local arg
  for arg in "$@"; do
    case "$arg" in
      --self-updated) self_updated=1 ;;
      -y|--yes) auto_yes=1 ;;
      --latest) arg_tag="latest" ;;
      --nightly) arg_tag="nightly" ;;
    esac
  done

  if [ "$self_updated" -eq 0 ]; then
    local tmp_script=".setup.sh.new.$$"
    if curl -fsSL "$RAW_BASE/setup.sh" -o "$tmp_script" 2>/dev/null && [ -s "$tmp_script" ]; then
      if ! cmp -s "$tmp_script" "$INSTALL_DIR/setup.sh" 2>/dev/null; then
        info "Updating setup.sh to latest version..."
        chmod +x "$tmp_script"
        mv -f "$tmp_script" "$INSTALL_DIR/setup.sh"
        local pass_args=()
        [ "$auto_yes" -eq 1 ] && pass_args+=("--yes")
        [ -n "$arg_tag" ] && pass_args+=("--${arg_tag}")
        exec "$INSTALL_DIR/setup.sh" update --self-updated "${pass_args[@]}"
      fi
    fi
    rm -f "$tmp_script"
  fi

  step "Updating SaviorBill Stack"

  if [ "$auto_yes" -eq 0 ]; then
    echo "The following system files will be updated from GitHub:"
    echo "  • docker-compose.yml"
    echo "  • Caddyfile & *.caddy.example"
    echo "  • caddy.d/*.caddy (only if unmodified; custom rules are preserved)"
    echo "  • .env.example (new missing keys will be appended to .env)"
    echo ""
    echo "Preserved untouched: .env (existing values), docker-compose.override.yml, data/, data-private/"
    echo ""
    local confirm_upd
    confirm_upd=$(prompt_default "Proceed with update? [Y/n]" "Y")
    case "$confirm_upd" in
      [yY]|[yY][eE][sS]) ;;
      *)
        info "Update cancelled."
        return 0
        ;;
    esac
  fi

  local cur_tag target_tag
  cur_tag="$(get_env_var "TAG")"
  cur_tag="${cur_tag:-latest}"
  if [ -n "$arg_tag" ]; then
    target_tag="$arg_tag"
  elif [ "$auto_yes" -eq 0 ]; then
    info "Current release channel: $cur_tag"
    target_tag=$(choose_release_channel "$cur_tag")
  else
    target_tag="$cur_tag"
  fi

  set_env_var "TAG" "$target_tag"
  set_env_var "CLIENT_TAG" "$target_tag"
  info "Using release channel: $target_tag"

  backup_stack_configs

  local new_compose="docker-compose.yml.new.$$"
  info "Downloading latest docker-compose.yml..."
  if ! curl -fsSL "$RAW_BASE/docker-compose.yml" -o "$new_compose" || [ ! -s "$new_compose" ]; then
    rm -f "$new_compose"
    err "Failed to download docker-compose.yml. Aborting without changes."
    return 1
  fi

  if ! docker_compose_cmd -f "$new_compose" config -q; then
    rm -f "$new_compose"
    err "Downloaded docker-compose.yml failed validation. Aborting without changes."
    return 1
  fi

  info "Pulling container images for channel '$target_tag'..."
  if ! docker_compose_cmd -f "$new_compose" pull; then
    rm -f "$new_compose"
    set_env_var "TAG" "$cur_tag"
    set_env_var "CLIENT_TAG" "$cur_tag"
    err "Failed to pull images (release '$target_tag' may not be published yet). Working stack left untouched."
    return 1
  fi

  mv -f "$new_compose" docker-compose.yml

  download_checked "$RAW_BASE/Caddyfile" "Caddyfile" || warn "Could not update Caddyfile"
  download_checked "$RAW_BASE/.env.example" ".env.example" || warn "Could not update .env.example"
  download_checked "$RAW_BASE/api.caddy.example" "api.caddy.example" || true
  download_checked "$RAW_BASE/media.caddy.example" "media.caddy.example" || true
  download_checked "$RAW_BASE/client.caddy.example" "client.caddy.example" || true

  sync_caddy_fragment "api"
  sync_caddy_fragment "media"
  sync_caddy_fragment "client"

  sync_missing_env_vars ".env.example" ".env"

  info "Applying updates (creating new services & removing obsolete containers)..."
  docker_compose_cmd up -d --remove-orphans
  docker_compose_cmd exec -T caddy caddy reload --config /etc/caddy/Caddyfile 2>/dev/null || true

  success "Stack updated to '$target_tag'!"
  docker_compose_cmd ps
}

# ── Interactive Setup Wizard ──────────────────────────────────────────────────
run_wizard() {
  print_banner
  check_docker
  prepare_base_files

  step "1. Environment Deployment Mode"
  echo "   [1] Production — Live server with custom domain names and automated HTTPS (Let's Encrypt)"
  echo "   [2] Local / IP Demo — Standalone demo / test stand (server IP address or localhost without SSL)"
  
  local env_choice
  env_choice=$(prompt_default "Choose mode [1/2]" "1")

  local domain=""
  local api_domain=""
  local media_domain=""
  local client_domain=""
  local owner_email=""
  local http_port="80"
  local https_port="443"
  local is_debug="false"
  local eof_count=0

  case "$env_choice" in
    2)
      # Local / IP Demo Stand
      step "2. Host & Network Setup (Local / IP)"
      local detected_ip
      detected_ip="$(detect_public_ip)"
      local host_input
      host_input=$(prompt_default "Server host address or IP" "$detected_ip")
      domain="$host_input"
      is_debug="true"

      if [[ "$domain" == "localhost" || "$domain" == *.localhost ]]; then
        echo ""
        echo "   [1] Unified address for Admin UI and API: http://${domain}"
        echo "   [2] Dedicated subdomain for API: http://api.${domain}"
        local loc_api_ch
        loc_api_ch=$(prompt_default "API endpoint routing [1/2]" "1")
        if [ "$loc_api_ch" = "2" ]; then
          api_domain="api.${domain}"
        else
          api_domain="$domain"
        fi
        media_domain="media.${domain}"
        owner_email=$(prompt_default "Administrator email" "admin@localhost.test")
      else
        api_domain="$domain"
        media_domain="$domain"
        owner_email=$(prompt_default "Administrator email" "admin@example.com")
      fi

      http_port=$(prompt_default "HTTP external port for Caddy" "80")
      ;;
    *)
      # Production with Custom Domains & Automated HTTPS
      step "2. Domain & Routing Configuration (Production)"
      info "Configure registered domain names pointed to this server's public IP."
      echo ""

      while true; do
        local raw_domain
        raw_domain=$(prompt_default "1. Admin Dashboard domain (e.g. panel.example.com or billing.example.com)" "")
        if [ -z "$raw_domain" ]; then
          eof_count=$((eof_count + 1))
          if [ "$eof_count" -ge 3 ]; then
            err "Input stream ended (EOF). Please run interactively."
            exit 1
          fi
          err "Admin Dashboard domain cannot be empty!"
          continue
        fi
        if domain=$(clean_and_validate_domain "$raw_domain"); then
          break
        fi
      done

      # 2. REST API & Webhooks
      echo ""
      echo "   [1] Shared domain with Admin UI: https://${domain}"
      echo "       (REST API and webhooks available under /api/* on the same domain)"
      echo "   [2] Dedicated subdomain for API"
      local api_choice
      api_choice=$(prompt_default "REST API & payment webhooks routing [1/2]" "1")
      if [ "$api_choice" = "2" ]; then
        while true; do
          local raw_api
          raw_api=$(prompt_default "Domain for REST API (e.g. api.example.com)" "")
          if [ -z "$raw_api" ]; then
            err "REST API domain cannot be empty!"
            continue
          fi
          if api_domain=$(clean_and_validate_domain "$raw_api"); then
            break
          fi
        done
      else
        api_domain="$domain"
      fi

      # 3. Media Server
      echo ""
      echo "   [1] Shared domain for images and files (under /api/media/*)"
      echo "   [2] Dedicated subdomain for Mediaworker"
      local media_choice
      media_choice=$(prompt_default "Media storage endpoint routing [1/2]" "1")
      if [ "$media_choice" = "2" ]; then
        while true; do
          local raw_media
          raw_media=$(prompt_default "Domain for Mediaworker (e.g. media.example.com)" "")
          if [ -z "$raw_media" ]; then
            err "Mediaworker domain cannot be empty!"
            continue
          fi
          if media_domain=$(clean_and_validate_domain "$raw_media"); then
            break
          fi
        done
      else
        media_domain="$api_domain"
      fi

      echo ""
      local email_attempts=0
      while true; do
        owner_email=$(prompt_default "Administrator email (used for Let's Encrypt SSL certificates, e.g. admin@example.com)" "")
        if [[ "$owner_email" == *"@"* ]]; then break; fi
        email_attempts=$((email_attempts + 1))
        if [ "$email_attempts" -ge 3 ]; then
          err "Please enter a valid email address."
          exit 1
        fi
        err "Please enter a valid email address with '@'."
      done

      http_port=$(prompt_default "External HTTP port for Caddy" "80")
      https_port=$(prompt_default "External HTTPS port for Caddy" "443")
      is_debug="false"
      ;;
  esac

  # ── Customer Portal (Client Storefront) ─────────────────────────────────────
  step "3. Customer Portal (SBPersonalAccountClient Storefront)"
  echo "The Customer Portal provides users with a modern self-service dashboard:"
  echo "browsing the catalog, placing orders, balance top-ups, and subscription management."
  echo ""
  local want_client
  want_client=$(prompt_default "Install Customer Portal? [Y/n]" "Y")

  local enable_client=0
  local client_override_port=""
  case "$want_client" in
    [yY]|[yY][eE][sS])
      enable_client=1
      if [ "$env_choice" = "1" ]; then
        # Production
        echo ""
        info "Customer Portal runs on a separate domain from the Admin Dashboard."
        while true; do
          local raw_client
          raw_client=$(prompt_default "Customer Portal domain (e.g. client.example.com or shop.example.com)" "")
          if [ -z "$raw_client" ]; then
            err "Customer Portal domain cannot be empty!"
            continue
          fi
          if client_domain=$(clean_and_validate_domain "$raw_client"); then
            if [ "$client_domain" = "$domain" ]; then
              warn "Customer Portal cannot use the exact same domain as Admin Dashboard ($domain)!"
              warn "Please provide a different subdomain or domain."
            else
              break
            fi
          fi
        done
      else
        # Local / IP
        if [[ "$domain" == "localhost" || "$domain" == *.localhost ]]; then
          echo ""
          echo "   [1] Dedicated subdomain: http://client.${domain}"
          echo "   [2] Dedicated port on host: http://${domain}:3000"
          local cl_mode
          cl_mode=$(prompt_default "Choose access mode for Customer Portal [1/2]" "1")
          if [ "$cl_mode" = "2" ]; then
            client_override_port=$(prompt_default "Port for Customer Portal" "3000")
            client_domain=":${client_override_port}"
          else
            client_domain=$(prompt_default "Subdomain for Customer Portal" "client.${domain}")
          fi
        else
          echo ""
          local custom_cl_port
          custom_cl_port=$(prompt_default "Port for Customer Portal on IP http://${domain}" "3000")
          client_domain=":${custom_cl_port}"
          client_override_port="$custom_cl_port"
        fi
      fi
      ;;
    *)
      enable_client=0
      info "Customer Portal skipped (Admin Dashboard & REST API only)."
      ;;
  esac

  # ── Security & Credentials ──────────────────────────────────────────────────
  step "4. Security & Administrator Credentials"
  
  local gen_db_pass
  gen_db_pass="$(generate_pass 24)"
  local db_pass
  db_pass=$(prompt_secret_or_gen "PostgreSQL Database Password" "$gen_db_pass")

  local bus_key
  bus_key="$(generate_hex 32)"

  local owner_login
  owner_login=$(prompt_default "Administrator (Owner) login" "owner")

  local gen_owner_pass
  gen_owner_pass="$(generate_pass 16)"
  local owner_pass
  owner_pass=$(prompt_secret_or_gen "Administrator (Owner) password" "$gen_owner_pass")

  # ── Write Configuration (.env) ──────────────────────────────────────────────
  step "5. Release Channel & Writing Configuration"

  local selected_tag
  selected_tag=$(choose_release_channel "latest")

  if [ ! -f .env ]; then
    cp .env.example .env
  fi

  set_env_var "TAG" "$selected_tag"
  set_env_var "CLIENT_TAG" "$selected_tag"
  set_env_var "DEBUG" "$is_debug"
  set_env_var "DOMAIN" "$domain"
  set_env_var "API_DOMAIN" "$api_domain"
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
  elif [ "$https_port" != "443" ] && [ "$proto_scheme" = "https" ]; then
    pub_port=":$https_port"
  fi

  set_env_var "PUBLIC_URL" "${proto_scheme}://${domain}${pub_port}"
  if [ "$media_domain" = "$domain" ] || [ "$media_domain" = "$api_domain" ]; then
    set_env_var "MEDIA_PUBLIC_URL" "${proto_scheme}://${api_domain}${pub_port}/api/media"
  else
    set_env_var "MEDIA_PUBLIC_URL" "${proto_scheme}://${media_domain}${pub_port}"
  fi

  # Automated CORS origins configuration
  local cors_list="${proto_scheme}://${domain}${pub_port}"
  if [ "$api_domain" != "$domain" ]; then
    cors_list="${cors_list},${proto_scheme}://${api_domain}${pub_port}"
  fi
  if [ "$enable_client" -eq 1 ]; then
    if [[ "$client_domain" == :* ]]; then
      cors_list="${cors_list},${proto_scheme}://${domain}${client_domain}"
    else
      cors_list="${cors_list},${proto_scheme}://${client_domain}${pub_port}"
    fi
  fi
  set_env_var "CORS_ORIGINS" "$cors_list"
  info "Configured CORS_ORIGINS: $cors_list"

  set_env_var "DB_PASS" "$db_pass"
  set_env_var "BUS_SIGNING_KEY" "$bus_key"
  set_env_var "OWNER_LOGIN" "$owner_login"
  set_env_var "OWNER_PASS" "$owner_pass"
  set_env_var "OWNER_EMAIL" "$owner_email"
  set_env_var "TRUSTED_PROXIES" "172.16.0.0/12,10.0.0.0/8,192.168.0.0/16,127.0.0.1"
  set_env_var "DATA_HOST_DIR" "./data"
  set_env_var "PRIVATE_DATA_HOST_DIR" "./data-private"

  mkdir -p caddy.d

  # API Subdomain Caddy config
  if [ "$api_domain" != "$domain" ]; then
    cp -f api.caddy.example caddy.d/api.caddy 2>/dev/null || true
    record_caddy_checksum "api"
    info "Dedicated API routing enabled: caddy.d/api.caddy ($api_domain)"
  else
    rm -f caddy.d/api.caddy .caddy.d.api.sha256
    info "REST API routed via shared domain (${domain}/api/*)"
  fi

  # Mediaworker Caddy config
  if [ "$media_domain" != "$domain" ] && [ "$media_domain" != "$api_domain" ]; then
    cp -f media.caddy.example caddy.d/media.caddy 2>/dev/null || true
    record_caddy_checksum "media"
    info "Dedicated Mediaworker routing enabled: caddy.d/media.caddy ($media_domain)"
  else
    rm -f caddy.d/media.caddy .caddy.d.media.sha256
    info "Media routed via API domain (/api/media/*)"
  fi

  # Client Storefront Caddy config & profiles
  if [ "$enable_client" -eq 1 ]; then
    set_env_var "COMPOSE_PROFILES" "client"
    set_env_var "CLIENT_DOMAIN" "$client_domain"
    cp -f client.caddy.example caddy.d/client.caddy
    record_caddy_checksum "client"
    if [ -n "$client_override_port" ]; then
      cat <<EOF > docker-compose.override.yml
services:
  caddy:
    ports:
      - "${client_override_port}:${client_override_port}"
EOF
      info "Created docker-compose.override.yml exposing Customer Portal port :${client_override_port}"
    else
      rm -f docker-compose.override.yml
    fi
    info "Customer Portal enabled (${client_domain})"
  else
    set_env_var "COMPOSE_PROFILES" ""
    rm -f caddy.d/client.caddy docker-compose.override.yml
  fi

  chmod 600 .env 2>/dev/null || true
  success "Configuration successfully generated in .env!"

  show_summary_card

  step "6. Launching SaviorBill Stack"
  local run_now
  run_now=$(prompt_default "Start SaviorBill stack now? [Y/n]" "Y")
  case "$run_now" in
    [yY]|[yY][eE][sS])
      info "Pulling latest container images..."
      if ! docker_compose_cmd pull; then
        warn "Initial pull encountered an issue. Retrying in 3 seconds..."
        sleep 3
        docker_compose_cmd pull || true
      fi
      info "Starting containers in background..."
      docker_compose_cmd up -d
      success "SaviorBill stack started successfully!"
      echo ""
      docker_compose_cmd ps
      echo ""
      info "To stream live container logs: cd $INSTALL_DIR && ./setup.sh logs"
      ;;
    *)
      info "To start the stack manually later: cd $INSTALL_DIR && ./setup.sh up"
      ;;
  esac
}

# ── Main CLI Menu (when .env already exists) ──────────────────────────────────
main_menu() {
  print_banner
  local domain api_domain client_domain
  domain="$(get_env_var "DOMAIN")"
  api_domain="$(get_env_var "API_DOMAIN")"
  client_domain="$(get_env_var "CLIENT_DOMAIN")"
  if [ -n "$domain" ]; then
    printf "${DIM}Admin Dashboard: ${BOLD}%s${RESET}\n" "$domain"
    if [ -n "$api_domain" ] && [ "$api_domain" != "$domain" ]; then
      printf "${DIM}REST API & Docs: ${BOLD}%s${RESET}\n" "$api_domain"
    fi
    if [ -n "$client_domain" ]; then
      printf "${DIM}Customer Portal: ${BOLD}%s${RESET}\n" "$client_domain"
    fi
    echo ""
  fi

  echo "   [1] Start stack (docker compose up -d)"
  echo "   [2] Stop stack (docker compose down)"
  echo "   [3] Restart stack (docker compose restart)"
  echo "   [4] Stream live logs (docker compose logs -f)"
  echo "   [5] Pull latest updates & restart"
  echo "   [6] Show credentials & endpoints summary"
  echo "   [7] Reconfigure stack (run setup wizard)"
  echo "   [0] Exit"
  echo ""

  local choice
  choice=$(prompt_default "Select option [1-7, 0]" "1")

  case "$choice" in
    1)
      info "Starting stack..."
      docker_compose_cmd up -d
      success "Stack started!"
      docker_compose_cmd ps
      ;;
    2)
      info "Stopping stack..."
      docker_compose_cmd down
      success "Stack stopped."
      ;;
    3)
      info "Restarting stack..."
      docker_compose_cmd restart
      success "Stack restarted."
      docker_compose_cmd ps
      ;;
    4)
      info "Streaming logs (press Ctrl+C to exit)..."
      docker_compose_cmd logs -f
      ;;
    5)
      update_stack
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
      warn "Unknown option: $choice"
      ;;
  esac
}

# ── Entry Point & CLI Subcommands ─────────────────────────────────────────────
ensure_install_dir

case "${1:-}" in
  up|--up)
    docker_compose_cmd up -d
    ;;
  down|--down)
    docker_compose_cmd down
    ;;
  restart|--restart)
    docker_compose_cmd restart
    ;;
  logs|--logs)
    docker_compose_cmd logs -f "${2:-}"
    ;;
  update|pull|--update|--pull)
    shift || true
    update_stack "$@"
    ;;
  info|status|--info|--status)
    show_summary_card
    ;;
  -r|--reconfigure)
    run_wizard
    ;;
  -h|--help)
    echo "SaviorBill Stack Manager"
    echo "Usage: ./setup.sh [up|down|restart|logs|update|info|--reconfigure]"
    ;;
  *)
    if [ -f .env ] && [ -s .env ]; then
      main_menu
    else
      run_wizard
    fi
    ;;
esac
