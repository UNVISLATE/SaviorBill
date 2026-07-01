-- Пример триггерного Lua-скрипта (простой).
--
-- Триггер связывает доменное событие (регистрация пользователя, выдача услуги,
-- оплата и т.п.) с действием. Это действие-скрипт: получает контекст события и
-- может, например, отправить уведомление во внешний webhook (Telegram-бот,
-- корпоративный чат, CRM) или выполнить любую другую интеграцию.
--
-- Контракт (см. schemas/lua/trigger.py):
--   ctx = {
--     event  = "user.registered" | "service.delivered" | "payment.succeeded" | ...,
--     config = { ... },   -- полная конфигурация действия триггера (из админки)
--     data   = { ... },   -- данные, из-за которых сработал триггер
--   }
-- handle возвращает таблицу { public = {...}, private = {...} } (результат
-- ядром не интерпретируется — важен факт успешного исполнения).
--
-- Конфигурация действия (ctx.config.*):
--   webhook_url  — (опц.) URL, на который отправить POST с телом события;
--   message      — (опц.) произвольный текст-подпись для уведомления.

local M = {}

function M.handle(ctx)
  local event = ctx.event or "unknown"
  local config = ctx.config or {}
  local data = ctx.data or {}

  log.info("trigger fired", event)

  local url = config.webhook_url
  if url == nil or url == "" then
    -- Webhook не настроен — просто логируем и выходим успешно.
    return { public = {}, private = { ok = true, event = event, sent = false } }
  end

  local payload = json.encode({
    event = event,
    message = config.message,
    data = data,
    ts = os.time(),
  })

  local resp = http({
    url = url,
    method = "POST",
    headers = { ["content-type"] = "application/json" },
    body = payload,
  })

  return {
    public = {},
    private = {
      ok = resp.ok and resp.status and resp.status < 300 or false,
      event = event,
      sent = true,
      status = resp.status,
    },
  }
end

return M
