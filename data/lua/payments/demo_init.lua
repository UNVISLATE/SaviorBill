-- Пример init-скрипта платёжного провайдера (инициализация платежа).
--
-- Контракт: модуль возвращает таблицу с функцией handle(ctx), где
--   ctx = {
--     payment  = { id, amount, currency, target, user_svc_id, return_url },
--     provider = { slug, settings = {...}, extra = {...} },  -- settings = секреты
--     user     = { id, login, email },
--   }
-- handle обязан вернуть { public = {...}, private = {...} }:
--   public.pay_url     — ссылка на оплату, которую биллинг отдаёт клиенту;
--   private.external_id — id транзакции у провайдера (для сверки в колбэке).

local M = {}

function M.handle(ctx)
  local pay = ctx.payment or {}
  local prov = ctx.provider or {}
  local settings = prov.settings or {}

  -- Здесь была бы реальная инициализация платежа во внешнем API с использованием
  -- секретов из settings (api_key, shop_id и т.п.):
  --   local resp = http({ url = settings.api_url, method = "POST",
  --                        headers = { authorization = settings.api_key },
  --                        body = json.encode({...}) })
  local ext = string.format("pay_%s_%d", tostring(pay.id or 0), os.time())
  local base = pay.return_url or (settings.pay_base or "https://example.test/pay")

  return {
    public = {
      pay_url = base .. "?txn=" .. ext,
      amount = pay.amount,
      currency = pay.currency,
    },
    private = {
      external_id = ext,
      provider = prov.slug,
    },
  }
end

return M
