-- Базовый шаблон услуги (action-driven). Регистрируется системой при старте.
--
-- ctx = {
--   action  = "create" | "renew" | "stop" | "delete" | "freeze",
--   user    = { id, login, email, service = { id, status, price, params }, payment },
--   service = { id, slug, name, price, params, settings },
-- }
--
-- handle обязан вернуть таблицу; система читает:
--   public   — данные для клиента (API);
--   private  — внутренние данные (только система);
--   private.state      — новое состояние услуги (active/frozen/stopped);
--   private.expires_at  — unix-время истечения (для billing-loop), опционально.
--
-- Длительность берётся из service.settings.duration или service.params.duration
-- (в секундах). Если не задана — услуга бессрочна (expires_at не выставляется).

local M = {}

local function ttl_seconds(svc)
  local s = svc.settings or {}
  local p = svc.params or {}
  return tonumber(s.duration) or tonumber(p.duration) or 0
end

function M.handle(ctx)
  local action = ctx.action or "create"
  local svc = ctx.service or {}
  local ttl = ttl_seconds(svc)
  local now = os.time()

  local public = {}
  local private = { action = action }

  if action == "create" or action == "renew" then
    private.state = "active"
    if ttl > 0 then
      private.expires_at = now + ttl
    end
    public.message = (svc.settings or {}).message or "Услуга активна"
  elseif action == "freeze" then
    private.state = "frozen"
    public.message = "Услуга заморожена"
  elseif action == "stop" or action == "delete" then
    private.state = "stopped"
    public.message = "Услуга остановлена"
  else
    error("неподдерживаемое действие: " .. tostring(action))
  end

  return {
    public = public,
    private = private,
    state = private.state,
    expires_at = private.expires_at,
  }
end

return M
