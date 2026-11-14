-- Пример почтового Lua-скрипта для smtp.bz через HTTP REST API.
--
-- Скрипт получает уже отрендеренное письмо от ядра биллинга и отправляет
-- его по HTTPS (порт 443), минуя возможные блокировки портов SMTP хостером.
--
-- Контракт (ScriptKind.EMAIL):
--   ctx = {
--     action = "send",
--     email = {
--       to         = "user@example.com",
--       subject    = "Тема письма",
--       body       = "<html>...</html>",
--       is_html    = true,
--       from_email = "noreply@myshop.com",
--       from_name  = "SaviorBill Shop",
--     },
--     config = {
--       api_key  = "...", -- токен API smtp.bz (или в lua.secrets.api_key)
--       endpoint = "https://api.smtp.bz/v1/smtp/send",
--     },
--     lua = { settings = {...}, secrets = {...} }
--   }
--
-- Возвращает:
--   { ok = true } или { ok = false, error = "текст ошибки" }

local M = {}

function M.handle(ctx)
  local email = ctx.email or {}
  local config = ctx.config or (ctx.lua and ctx.lua.secrets) or {}

  local api_key = config.api_key or (ctx.lua and ctx.lua.secrets and ctx.lua.secrets.api_key)
  if not api_key or api_key == "" then
    return { ok = false, error = "smtp.bz api_key is not configured in config/secrets" }
  end

  local endpoint = config.endpoint or "https://api.smtp.bz/v1/smtp/send"

  local payload = {
    from = email.from_email,
    to = email.to,
    subject = email.subject,
    html = email.is_html and email.body or nil,
    text = (not email.is_html) and email.body or nil,
    name = email.from_name,
  }

  local resp = http.request({
    url = endpoint,
    method = "POST",
    headers = {
      ["Authorization"] = api_key,
      ["Content-Type"] = "application/json",
    },
    body = json.encode(payload),
    timeout = 10,
  })

  if not resp or not resp.ok then
    local err = (resp and resp.error) or ("HTTP status " .. tostring(resp and resp.status))
    if resp and resp.body and #resp.body > 0 then
      local ok_json, parsed = pcall(json.decode, resp.body)
      if ok_json and parsed and (parsed.message or parsed.error) then
        err = tostring(parsed.message or parsed.error)
      end
    end
    return { ok = false, error = "smtp.bz API error: " .. tostring(err) }
  end

  return { ok = true }
end

return M
