-- Пример callback-скрипта платёжного провайдера (server-to-server webhook).
--
-- Ядро принимает только вебхук на статичный URL /api/v1/callback/payment/{slug}
-- (страниц success/fail нет). Контракт: модуль возвращает таблицу с функцией
-- handle(ctx), где
--   ctx = {
--     provider  = { slug, settings = {...}, extra = {...} },  -- settings = секреты
--     request   = { ... },  -- тело вебхука/query как есть; свой payment_id внутри
--     directive = "webhook" | "recheck",  -- recheck = перепроверку начало само ядро
--   }
-- handle обязан вернуть { public = {...}, private = {...} }, где в private:
--   ok          — подпись/запрос валидны (иначе биллинг ответит 401);
--   paid        — платёж успешен;
--   payment_id  — id платежа в биллинге (если есть в request);
--   external_id — id транзакции у провайдера (как запасной способ сверки).
--
-- ВАЖНО: боевая интеграция при directive="recheck" (и в идеале всегда) сама
-- перепроверяет статус запросом к API провайдера — это надёжнее проверки подписи.
-- В демо мы сверяем общий секрет request.sign == settings.secret (заглушка).

local M = {}

function M.handle(ctx)
  local prov = ctx.provider or {}
  local settings = prov.settings or {}
  local req = ctx.request or {}

  local ok = false
  if settings.secret ~= nil and req.sign ~= nil then
    ok = (tostring(req.sign) == tostring(settings.secret))
  end

  -- success-флаг платёжки (строкой или булевым).
  local paid = false
  local s = req.success
  if s == true or s == "true" or s == "1" or s == 1 then
    paid = true
  end

  return {
    public = {},
    private = {
      ok = ok,
      paid = paid,
      payment_id = req.payment_id,
      external_id = req.external_id,
    },
  }
end

return M
