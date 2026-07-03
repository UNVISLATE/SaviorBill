-- Универсальный OAuth2/OIDC auth-скрипт (action-driven).
--
-- Обрабатывает действия входа по ctx.action:
--   start    — построить authorize_url для редиректа пользователя;
--   callback — обменять code на токен и получить нормализованный профиль.
--
-- Секреты провайдера (ctx.provider.secrets):
--   client_id      — OAuth client_id;
--   client_secret  — OAuth client_secret;
--   authorize_url  — endpoint авторизации (напр. https://accounts.google.com/o/oauth2/v2/auth);
--   token_url      — endpoint обмена кода на токен;
--   userinfo_url   — endpoint профиля (OIDC userinfo).
-- ctx.provider.scopes — строка запрашиваемых scope (через пробел).
--
-- Возвращает:
--   start:    { public = { authorize_url = "..." } }
--   callback: { private = { ok, sub, email, email_verified, name, picture, raw } }

local M = {}

local function urlencode(s)
  s = tostring(s or "")
  return (s:gsub("[^%w%-_%.~]", function(c)
    return string.format("%%%02X", string.byte(c))
  end))
end

local function query(params)
  local parts = {}
  for k, v in pairs(params) do
    parts[#parts + 1] = urlencode(k) .. "=" .. urlencode(v)
  end
  return table.concat(parts, "&")
end

local function secrets(ctx)
  return (ctx.provider or {}).secrets or {}
end

local function do_start(ctx)
  local s = secrets(ctx)
  assert(s.client_id and s.authorize_url, "oauth: нужны client_id и authorize_url")
  local url = s.authorize_url
    .. "?"
    .. query({
      client_id = s.client_id,
      redirect_uri = ctx.redirect_uri,
      response_type = "code",
      scope = (ctx.provider or {}).scopes or "openid email profile",
      state = ctx.state,
    })
  return { public = { authorize_url = url } }
end

local function exchange(ctx)
  local s = secrets(ctx)
  local resp = http({
    url = s.token_url,
    method = "POST",
    headers = {
      ["content-type"] = "application/x-www-form-urlencoded",
      ["accept"] = "application/json",
    },
    body = query({
      grant_type = "authorization_code",
      code = ctx.code,
      redirect_uri = ctx.redirect_uri,
      client_id = s.client_id,
      client_secret = s.client_secret,
    }),
  })
  if not resp.ok or resp.status ~= 200 then
    return nil
  end
  return json.decode(resp.body) or {}
end

local function userinfo(ctx, access_token)
  local s = secrets(ctx)
  local resp = http({
    url = s.userinfo_url,
    method = "GET",
    headers = {
      ["authorization"] = "Bearer " .. tostring(access_token),
      ["accept"] = "application/json",
    },
  })
  if not resp.ok or resp.status ~= 200 then
    return nil
  end
  return json.decode(resp.body) or {}
end

local function do_callback(ctx)
  assert(ctx.code, "oauth: отсутствует code")
  local tokens = exchange(ctx)
  if tokens == nil or not tokens.access_token then
    return { private = { ok = false } }
  end
  local ui = userinfo(ctx, tokens.access_token)
  if ui == nil or not (ui.sub or ui.id) then
    return { private = { ok = false } }
  end
  return {
    private = {
      ok = true,
      sub = tostring(ui.sub or ui.id),
      email = ui.email,
      email_verified = ui.email_verified == true,
      name = ui.name,
      picture = ui.picture,
      raw = ui,
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
