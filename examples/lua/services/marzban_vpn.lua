-- Пример сервисного Lua-скрипта: выдача VPN (VLESS) через панель Marzban.
--
-- Аналог bash-шаблона SHM (shm_marz_onlyvless.tpl), переписанный под контракт
-- SaviorBill. Скрипт action-driven: одно тело обслуживает весь жизненный цикл
-- услуги, действие приходит в ctx.action.
--
-- Контракт (см. services/demo_service.lua):
--   ctx = {
--     action = "create" | "renew" | "stop" | "delete" | "freeze",
--     user   = { id, login, email,
--                service = { id, status, expires_at, private_data, public_data },
--                payment = <id платежа | nil> },
--     service = { id, slug, name, price, duration, params, settings, actions },
--   }
-- handle возвращает { public = {...}, private = {...}, state, expires_at }.
--
-- Настройки берутся из шаблона (ctx.lua.settings.*) и/или услуги
-- (ctx.service.settings.*). Настройки шаблона общие для всех услуг, использующих
-- этот скрипт (удобно для учётных данных панели), настройки услуги их дополняют
-- и переопределяют:
--   marzban_domain   — домен панели Marzban (без схемы), напр. "panel.example.com";
--   marzban_user     — логин администратора панели;
--   marzban_pass     — пароль администратора панели;
--   data_limit_gb    — (опц.) лимит трафика в ГБ; 0/nil — безлимит;
--   reset_strategy   — (опц.) стратегия сброса трафика ("no_reset"/"month"/...);
--   duration         — (опц.) срок действия в секундах (если не задан в услуге).
--
-- ВАЖНО: имя пользователя Marzban генерируется один раз при create и сохраняется
-- в private_data.username. На последующих действиях оно берётся оттуда и снова
-- возвращается, чтобы не потеряться (issuer перезаписывает private_data целиком).

local M = {}

-- --- helpers ---------------------------------------------------------------

-- Общие настройки шаблона (ctx.lua.settings) переопределяются настройками
-- конкретной услуги (ctx.service.settings).
local function settings(ctx)
  local out = {}
  local tpl = (ctx.lua or {}).settings or {}
  for k, v in pairs(tpl) do
    out[k] = v
  end
  local svc = (ctx.service or {}).settings or {}
  for k, v in pairs(svc) do
    out[k] = v
  end
  return out
end

local function host(s)
  return "https://" .. tostring(s.marzban_domain)
end

-- Срок действия (сек): service.duration, иначе settings.duration.
local function duration_seconds(ctx)
  local svc = ctx.service or {}
  return tonumber(svc.duration) or tonumber(settings(ctx).duration) or 0
end

-- Целевой unix-момент истечения: продлеваем от текущего expires_at, если он в
-- будущем (renew), иначе от «сейчас».
local function expire_ts(ctx)
  local ttl = duration_seconds(ctx)
  if ttl <= 0 then
    return 0
  end
  local now = os.time()
  local base = now
  local cur = ((ctx.user or {}).service or {}).expires_at
  cur = tonumber(cur)
  if cur and cur > now then
    base = cur
  end
  return base + ttl
end

local function data_limit_bytes(s)
  local gb = tonumber(s.data_limit_gb) or 0
  if gb <= 0 then
    return 0
  end
  return math.floor(gb * 1024 * 1024 * 1024)
end

-- Детерминированный псевдослучайный суффикс (в песочнице нет /dev/urandom).
local function rand_suffix(seed, n)
  math.randomseed((tonumber(seed) or 0) + os.time())
  local chars = "abcdefghijklmnopqrstuvwxyz0123456789"
  local out = {}
  for _ = 1, n do
    local idx = math.random(1, #chars)
    out[#out + 1] = string.sub(chars, idx, idx)
  end
  return table.concat(out)
end

-- Имя пользователя Marzban: из private_data (если уже создавали) либо новое
-- вида "{login}_{rand4}", ограниченное 32 символами.
local function target_username(ctx)
  local usvc = (ctx.user or {}).service or {}
  local saved = (usvc.private_data or {}).username
  if saved ~= nil and saved ~= "" then
    return tostring(saved)
  end
  local login = tostring((ctx.user or {}).login or "user")
  local clean = string.lower(string.gsub(login, "[^%w_]", ""))
  local full = clean .. "_" .. rand_suffix((ctx.user or {}).id, 4)
  return string.sub(full, 1, 32)
end

-- Авторизация в Marzban: возвращает access_token или падает.
local function get_token(s)
  local resp = http({
    url = host(s) .. "/api/admin/token",
    method = "POST",
    headers = { ["content-type"] = "application/x-www-form-urlencoded" },
    body = "grant_type=password&username="
      .. tostring(s.marzban_user)
      .. "&password="
      .. tostring(s.marzban_pass),
  })
  if not resp.ok or resp.status ~= 200 then
    error("marzban: авторизация не удалась (" .. tostring(resp.status) .. ")")
  end
  local data = json.decode(resp.body) or {}
  assert(data.access_token, "marzban: пустой access_token")
  return data.access_token
end

local function auth(token)
  return { ["authorization"] = "Bearer " .. tostring(token) }
end

-- Список тегов активных VLESS-inbound'ов панели.
local function vless_inbounds(s, token)
  local resp = http({
    url = host(s) .. "/api/inbounds",
    method = "GET",
    headers = auth(token),
  })
  local tags = {}
  if resp.ok and resp.status == 200 then
    local data = json.decode(resp.body) or {}
    for _, inb in ipairs(data.vless or {}) do
      tags[#tags + 1] = inb.tag
    end
  end
  return tags
end

-- --- действия --------------------------------------------------------------

local function do_create(ctx)
  local s = settings(ctx)
  assert(s.marzban_domain and s.marzban_user and s.marzban_pass,
    "marzban: нужны marzban_domain/marzban_user/marzban_pass в настройках шаблона или услуги")

  local token = get_token(s)
  local username = target_username(ctx)
  local exp = expire_ts(ctx)

  local payload = json.encode({
    username = username,
    proxies = { vless = { flow = "" } },
    inbounds = { vless = vless_inbounds(s, token) },
    expire = exp,
    data_limit = data_limit_bytes(s),
    data_limit_reset_strategy = s.reset_strategy or "no_reset",
    status = "active",
    note = "SaviorBill: " .. tostring((ctx.user or {}).login),
  })

  local resp = http({
    url = host(s) .. "/api/user",
    method = "POST",
    headers = { ["authorization"] = "Bearer " .. token, ["content-type"] = "application/json" },
    body = payload,
  })
  if not resp.ok or (resp.status ~= 200 and resp.status ~= 201) then
    error("marzban: создание пользователя не удалось: "
      .. tostring(resp.status) .. " " .. tostring(resp.body))
  end

  local data = json.decode(resp.body) or {}
  local sub = data.subscription_url or ""
  if sub ~= "" and not string.match(sub, "^https?://") then
    sub = host(s) .. sub
  end

  log.info("marzban user created", username)
  return {
    public = {
      -- Дефолтный интерфейс отрисует public_data.subscription как ссылку.
      subscription = sub,
      username = username,
    },
    private = { username = username, marzban_status = "active" },
    state = "active",
    product_key = "subscription",
    product_kind = "url",
    expires_at = (exp > 0) and exp or nil,
  }
end

local function do_renew(ctx)
  local s = settings(ctx)
  local token = get_token(s)
  local username = target_username(ctx)
  local exp = expire_ts(ctx)

  local payload = json.encode({
    inbounds = { vless = vless_inbounds(s, token) },
    proxies = { vless = { flow = "" } },
    expire = exp,
    data_limit = data_limit_bytes(s),
    status = "active",
  })
  local resp = http({
    url = host(s) .. "/api/user/" .. username,
    method = "PUT",
    headers = { ["authorization"] = "Bearer " .. token, ["content-type"] = "application/json" },
    body = payload,
  })
  if not resp.ok or resp.status ~= 200 then
    error("marzban: продление не удалось: " .. tostring(resp.status))
  end
  log.info("marzban user renewed", username)
  return {
    public = { subscription = (json.decode(resp.body) or {}).subscription_url, username = username },
    private = { username = username, marzban_status = "active" },
    state = "active",
    product_key = "subscription",
    product_kind = "url",
    expires_at = (exp > 0) and exp or nil,
  }
end

local function do_freeze(ctx)
  local s = settings(ctx)
  local token = get_token(s)
  local username = target_username(ctx)
  http({
    url = host(s) .. "/api/user/" .. username,
    method = "PUT",
    headers = { ["authorization"] = "Bearer " .. token, ["content-type"] = "application/json" },
    body = json.encode({ status = "disabled" }),
  })
  log.info("marzban user disabled", username)
  return {
    public = { username = username },
    private = { username = username, marzban_status = "disabled" },
    state = "frozen",
  }
end

local function do_remove(ctx)
  local s = settings(ctx)
  local token = get_token(s)
  local username = target_username(ctx)
  http({
    url = host(s) .. "/api/user/" .. username,
    method = "DELETE",
    headers = auth(token),
  })
  log.info("marzban user removed", username)
  return {
    public = {},
    private = { username = username, marzban_status = "removed" },
    state = "stopped",
  }
end

local _DISPATCH = {
  create = do_create,
  renew = do_renew,
  freeze = do_freeze,
  stop = do_remove,
  delete = do_remove,
}

function M.handle(ctx)
  local action = ctx.action or "create"
  local fn = _DISPATCH[action]
  if fn == nil then
    return { public = {}, private = { ok = false, error = "unknown action: " .. tostring(action) } }
  end
  return fn(ctx)
end

return M
