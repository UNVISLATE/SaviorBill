-- Пример сервисного Lua-скрипта (action-driven доставка/обслуживание услуги).
--
-- Контракт: модуль возвращает таблицу с функцией handle(ctx), где
--   ctx = {
--     action  = "create" | "renew" | "stop" | "delete" | "freeze",
--     user    = { id, login, email,
--                 service = { id, status, state, price, params },  -- услуга юзера
--                 payment = <id платежа | nil> },                  -- nil = выдача вручную
--     service = { id, slug, name, price, params, settings, actions },  -- эталон каталога
--   }
-- handle возвращает { public = {...}, private = {...} } и опционально поля
-- верхнего уровня для billing-loop:
--   state       — новое состояние услуги (active/frozen/stopped);
--   expires_at  — unix-время истечения (если услуга срочная).
-- Срок берётся из service.settings.duration или service.params.duration (сек).

local M = {}

local function ttl_seconds(svc)
  local s = svc.settings or {}
  local p = svc.params or {}
  return tonumber(s.duration) or tonumber(p.duration) or 0
end

function M.handle(ctx)
  local action = ctx.action or "create"
  local user = ctx.user or {}
  local svc = ctx.service or {}
  local sp = svc.params or {}

  -- Здесь могла бы быть реальная интеграция: http(...) к внешнему API,
  -- billing.charge{...} и т.п. Для демонстрации формируем результат локально.
  local code = string.format("DEMO-%d-%d", svc.id or 0, user.id or 0)
  local public = {}
  local private = { action = action, issued_to = user.id }

  if action == "create" or action == "renew" then
    private.state = "active"
    local ttl = ttl_seconds(svc)
    if ttl > 0 then
      private.expires_at = os.time() + ttl
    end
    public.message = sp.message or "Услуга успешно выдана"
    public.access_code = code
    private.raw = "internal-secret-" .. tostring(os.time())
  elseif action == "freeze" then
    private.state = "frozen"
    public.message = "Услуга заморожена"
  else -- stop | delete
    private.state = "stopped"
    public.message = "Услуга остановлена"
  end

  return {
    public = public,
    private = private,
    state = private.state,
    expires_at = private.expires_at,
  }
end

return M
