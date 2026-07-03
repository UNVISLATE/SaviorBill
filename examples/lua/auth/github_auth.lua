-- GitHub OAuth2 auth-скрипт (не OIDC — профиль берётся из REST API).
--
-- ctx.action:
--   start    — построить authorize_url;
--   callback — обменять code на токен и собрать профиль из api.github.com.
--
-- Секреты (ctx.provider.secrets):
--   client_id, client_secret.
-- ctx.provider.scopes — напр. "read:user user:email".

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
  assert(s.client_id, "github: нужен client_id")
  local url = "https://github.com/login/oauth/authorize?"
    .. query({
      client_id = s.client_id,
      redirect_uri = ctx.redirect_uri,
      scope = (ctx.provider or {}).scopes or "read:user user:email",
      state = ctx.state,
    })
  return { public = { authorize_url = url } }
end

local function exchange(ctx)
  local s = secrets(ctx)
  local resp = http({
    url = "https://github.com/login/oauth/access_token",
    method = "POST",
    headers = {
      ["content-type"] = "application/x-www-form-urlencoded",
      ["accept"] = "application/json",
    },
    body = query({
      client_id = s.client_id,
      client_secret = s.client_secret,
      code = ctx.code,
      redirect_uri = ctx.redirect_uri,
    }),
  })
  if not resp.ok or resp.status ~= 200 then
    return nil
  end
  return json.decode(resp.body) or {}
end

local function api_get(path, token)
  local resp = http({
    url = "https://api.github.com" .. path,
    method = "GET",
    headers = {
      ["authorization"] = "Bearer " .. tostring(token),
      ["accept"] = "application/vnd.github+json",
      ["user-agent"] = "SaviorBill",
    },
  })
  if not resp.ok or resp.status ~= 200 then
    return nil
  end
  return json.decode(resp.body)
end

-- Основной (verified) email из /user/emails, если /user.email пуст.
local function primary_email(token)
  local emails = api_get("/user/emails", token)
  if type(emails) ~= "table" then
    return nil, false
  end
  for _, e in ipairs(emails) do
    if e.primary then
      return e.email, e.verified == true
    end
  end
  return nil, false
end

local function do_callback(ctx)
  assert(ctx.code, "github: отсутствует code")
  local tokens = exchange(ctx)
  if tokens == nil or not tokens.access_token then
    return { private = { ok = false } }
  end
  local u = api_get("/user", tokens.access_token)
  if u == nil or not u.id then
    return { private = { ok = false } }
  end
  local email, verified = u.email, false
  if not email then
    email, verified = primary_email(tokens.access_token)
  end
  return {
    private = {
      ok = true,
      sub = tostring(u.id),
      email = email,
      email_verified = verified,
      name = u.name or u.login,
      picture = u.avatar_url,
      raw = u,
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
