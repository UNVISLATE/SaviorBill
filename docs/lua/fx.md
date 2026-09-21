# Курсы валют через Lua-скрипт

Готовые источники курсов (ЦБ РФ, Frankfurter, ExchangeRate-API и др.) описаны
в `src/services/fx_providers.py` и выбираются в админке: **Настройки → Валюта
и курсы**. Если нужного сервиса там нет — курсы может отдавать Lua-скрипт.

## Когда это нужно

- сервис не входит в список готовых (внутренний API компании, биржа, банк);
- нестандартная авторизация (подпись запроса, OAuth, заголовки вместо ключа
  в URL);
- курсы нужно собрать из нескольких источников или скорректировать по своей
  формуле.

## Подключение

1. **Настройки → Скрипты** — создайте скрипт вида `generic`.
2. **Настройки → Валюта и курсы**:
   - «Режим» → `Внешний источник`;
   - «Источник» → `Lua-скрипт (свой источник)`;
   - «Slug Lua-скрипта» → slug созданного скрипта.
3. Нажмите **«Проверить источник»** — увидите, что сервер получил и разобрал.

## Контракт

Скрипт вызывается с `ctx.action = "rates"` и обязан вернуть таблицу:

```lua
return {
  handle = function(ctx)
    return {
      public = {
        rates = {
          USD = "95.5",
          EUR = "103.2",
        },
      },
    }
  end,
}
```

Требования к `public.rates`:

- ключ — ISO-код валюты (регистр не важен, приводится к верхнему);
- значение — **сколько базовой валюты стоит одна единица указанной**
  (при базовой `RUB` запись `USD = "95.5"` означает «1 USD = 95.5 RUB»);
- значения передавайте **строками**, а не числами: у Lua один числовой тип
  (double), и на длинных дробях он теряет точность;
- курс базовой валюты к самой себе указывать не нужно;
- пустой список — ошибка, зачисление в чужой валюте будет отклонено.

Ошибку сообщайте через `error("…")` — текст попадёт в результат проверки в
админке и в лог.

## Что доступно внутри скрипта

`http`, `json`, `crypto`, `cache`, `log` — как в остальных скриптах (см.
`luaworker/src/handlers.lua`). Настройки самого скрипта — в `ctx.lua.settings`:
там удобно держать ключи доступа, не зашивая их в код.

## Пример: сервис с ключом в заголовке

```lua
local BASE = "RUB"

return {
  handle = function(ctx)
    local settings = (ctx.lua or {}).settings or {}
    local token = settings.api_token
    if not token or token == "" then
      error("не задан api_token в настройках скрипта")
    end

    local res = http({
      url = "https://api.example.com/v1/rates?base=" .. BASE,
      method = "GET",
      headers = {
        ["authorization"] = "Bearer " .. token,
        ["accept"] = "application/json",
      },
    })

    if res.status ~= 200 then
      error("источник вернул HTTP " .. tostring(res.status))
    end

    local body = json.decode(res.body)
    local rates = {}

    -- Сервис отдаёт "сколько валюты за 1 базовую" — переворачиваем.
    for code, value in pairs(body.quotes or {}) do
      local num = tonumber(value)
      if num and num > 0 then
        rates[code] = tostring(1 / num)
      end
    end

    return { public = { rates = rates } }
  end,
}
```

## Пример: два источника с приоритетом

```lua
-- Основной источник — биржа, недостающие валюты добираем из ЦБ.
local function fetch(url)
  local res = http({ url = url })
  if res.status ~= 200 then
    return nil
  end
  return json.decode(res.body)
end

return {
  handle = function(ctx)
    local rates = {}

    local cbr = fetch("https://www.cbr-xml-daily.ru/daily_json.js")
    for _, item in pairs((cbr or {}).Valute or {}) do
      local nominal = tonumber(item.Nominal) or 1
      local value = tonumber(item.Value)
      if value then
        rates[item.CharCode] = tostring(value / nominal)
      end
    end

    -- Курс криптовалюты, которого у ЦБ нет.
    local exchange = fetch("https://api.example.com/usdt-rub")
    if exchange and tonumber(exchange.price) then
      rates.USDT = tostring(exchange.price)
    end

    if next(rates) == nil then
      error("ни один источник не ответил")
    end

    log.info("курсов собрано: " .. tostring(#rates))
    return { public = { rates = rates } }
  end,
}
```

## Кэширование

Результат кладётся в Valkey на `billing.fx.cache_ttl_sec` (там же, где и у
готовых провайдеров), поэтому скрипт не вызывается на каждый платёж. Ставить
собственный кэш через `cache` внутри скрипта нужно только если один и тот же
внешний запрос используется где-то ещё.

## Отладка

- **«Проверить источник»** на странице курсов — показывает разобранные
  сервером курсы либо текст ошибки.
- **Test-run** в редакторе скрипта — запуск в песочнице; учтите, что там
  `http` заглушен, поэтому реальные курсы так не получить, зато видно
  синтаксические ошибки и логику разбора на фиктивных данных.
- Записи `log.info(...)` доступны через
  `GET /api/v1/admin/lua/executions/{cid}/logs`.

## Частые ошибки

| Симптом | Причина |
| --- | --- |
| `скрипт не вернул public.rates` | Вернули `{ rates = ... }` вместо `{ public = { rates = ... } }` |
| Курс завышен/занижен в разы | Не учтён номинал (у ЦБ JPY котируется за 100 единиц) либо не перевёрнута котировка |
| `вернул пустой список курсов` | Все значения не распарсились в число или оказались ≤ 0 |
| Курс не меняется после правки | Ещё жив кэш — дождитесь `billing.fx.cache_ttl_sec` или нажмите «Проверить источник» (он ходит мимо кэша) |
