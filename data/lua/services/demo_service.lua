-- Пример сервисного Lua-скрипта (доставка цифровой услуги).
--
-- Контракт: модуль возвращает таблицу с функцией handle(ctx), где
--   ctx = {
--     order   = { id, params },          -- заказ и его кастом-параметры
--     service = { id, slug, params },     -- услуга и её настройки
--     user    = { id, login, email },     -- пользователь в биллинге
--   }
-- handle обязан вернуть { public = {...}, private = {...} }:
--   public  — что биллинг отдаёт клиенту по API;
--   private — внутренние данные (видит только система).

local M = {}

function M.handle(ctx)
  local user = ctx.user or {}
  local svc = ctx.service or {}
  local sp = svc.params or {}

  -- Здесь могла бы быть реальная интеграция: http(...) к внешнему API,
  -- billing.charge{...} и т.п. Для демонстрации формируем результат локально.
  local code = string.format("DEMO-%d-%d", svc.id or 0, user.id or 0)

  return {
    public = {
      message = sp.message or "Услуга успешно выдана",
      access_code = code,
    },
    private = {
      issued_to = user.id,
      raw = "internal-secret-" .. tostring(os.time()),
    },
  }
end

return M
