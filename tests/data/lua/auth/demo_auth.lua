-- Демо-скрипт OAuth для тестов и локальной отладки (без внешних HTTP-вызовов).
--
-- ctx.action:
--   start    — возвращает authorize_url, ведущий обратно на наш redirect_uri
--              с готовыми code/state (чтобы прогнать колбэк без реального провайдера);
--   callback — считает вход успешным и отдаёт детерминированный профиль из code.
--
-- Секреты (ctx.provider.secrets), опционально:
--   email          — email, который вернуть (по умолчанию из code);
--   email_verified — булево (по умолчанию true).

local M = {}

local function secrets(ctx)
  return (ctx.provider or {}).secrets or {}
end

local function do_start(ctx)
  local url = ctx.redirect_uri
    .. "?code=demo-"
    .. tostring(ctx.state)
    .. "&state="
    .. tostring(ctx.state)
  return { public = { authorize_url = url } }
end

local function do_callback(ctx)
  local s = secrets(ctx)
  local sub = "demo-" .. tostring(ctx.code)
  local email = s.email or (sub .. "@demo.local")
  local verified = s.email_verified
  if verified == nil then
    verified = true
  end
  return {
    private = {
      ok = true,
      sub = sub,
      email = email,
      email_verified = verified == true,
      name = "Demo User",
      raw = { code = ctx.code, provider = (ctx.provider or {}).slug },
    },
  }
end

local _DISPATCH = {
  start = do_start,
  callback = do_callback,
}

function M.handle(ctx)
  local fn = _DISPATCH[ctx.action or "start"]
  if fn == nil then
    return { public = {}, private = { ok = false, error = "unknown action" } }
  end
  return fn(ctx)
end

return M
