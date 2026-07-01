-- Platega: callback-скрипт (server-to-server webhook статуса транзакции).
--
-- Секреты провайдера (provider.settings): merchant_id, secret.
-- Доп. параметры (provider.extra):
--   status_url_tpl — шаблон URL проверки статуса (по умолчанию
--                    "https://app.platega.io/transaction/%s");
--   paid_statuses  — список «успешных» статусов через запятую
--                    (по умолчанию "CONFIRMED,SUCCESS,PAID,COMPLETED").
-- Контекст: ctx.request — тело вебхука Platega (ожидаются transactionId/id,
--   status и payload — наш id платежа из init-скрипта); ctx.directive =
--   "webhook" | "recheck" (recheck — перепроверку начало само ядро).
--
-- БЕЗОПАСНОСТЬ: статус из вебхука не доверяется напрямую — он перепроверяется
-- запросом к API Platega с merchant-секретами (одинаково для webhook и recheck).
-- Возврат private: ok, paid, payment_id (наш id из payload), external_id, status.

local M = {}

function M.handle(ctx)
  local prov = ctx.provider or {}
  local s = prov.settings or {}
  local extra = prov.extra or {}
  local req = ctx.request or {}

  local txn = req.transactionId or req.id or req.external_id
  local pid = req.payload or req.payment_id
  if not txn or not s.merchant_id or not s.secret then
    return { public = {}, private = { ok = false } }
  end

  -- Перепроверяем статус транзакции напрямую у Platega.
  local tpl = extra.status_url_tpl or "https://app.platega.io/transaction/%s"
  local resp = http({
    url = string.format(tpl, tostring(txn)),
    method = "GET",
    headers = {
      ["x-merchantid"] = tostring(s.merchant_id),
      ["x-secret"] = tostring(s.secret),
    },
  })
  if not resp.ok or resp.status ~= 200 then
    return { public = {}, private = { ok = false } }
  end

  local data = json.decode(resp.body) or {}
  local status = data.status or req.status

  local paid = false
  local ok_statuses = extra.paid_statuses or "CONFIRMED,SUCCESS,PAID,COMPLETED"
  for st in string.gmatch(ok_statuses, "[^,]+") do
    if status == st then
      paid = true
      break
    end
  end

  return {
    public = {},
    private = {
      ok = true,
      paid = paid,
      payment_id = pid,
      external_id = txn,
      status = status,
    },
  }
end

return M
