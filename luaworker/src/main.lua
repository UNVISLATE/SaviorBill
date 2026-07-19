-- LuaWorker: исполнитель Lua-задач из шины Redis Streams (Valkey).
--
-- Поток работы:
--   1. Биллинг публикует задачу в LUA_TASK_STREAM (XADD) с полями cid/kind/payload.
--   2. Воркер читает её через consumer-группу (XREADGROUP), исполняет handler.
--   3. Результат публикуется в LUA_RESP_STREAM (XADD) с полями cid/ok/data.
--   4. Задача подтверждается (XACK).
--
-- Если задан BUS_SIGNING_KEY (общий с billing) — задачи/результаты подписываются
-- HMAC-SHA256 (поля ts+sig, см. verify_signed/sign_fields выше), что закрывает
-- подделку сообщений тем, у кого есть прямой доступ к Valkey.

local redis = require("redis")
local cjson = require("cjson")
local socket = require("socket")
local handlers = require("handlers")
local sbox = require("sbox")

local function env(key, default)
  local v = os.getenv(key)
  if v == nil or v == "" then
    return default
  end
  return v
end

local HOST = env("VALKEY_HOST", "valkey")
local PORT = tonumber(env("VALKEY_PORT", "6379"))
local DB = tonumber(env("VALKEY_DB", "0"))
local TASK = env("LUA_TASK_STREAM", "lua:tasks")
local RESP = env("LUA_RESP_STREAM", "lua:results")
local GROUP = env("LUA_GROUP", "luaworkers")
-- Уникальное имя консьюмера на реплику: HOSTNAME (id контейнера) + случайный
-- суффикс. Иначе несколько реплик с одинаковым именем делят PEL и путают
-- атрибуцию pending-задач при масштабировании.
math.randomseed(math.floor(socket.gettime() * 1000))
local DEFAULT_CONSUMER = (env("HOSTNAME", "worker") .. "-" .. tostring(math.random(100000, 999999)))
local CONSUMER = env("LUA_CONSUMER", DEFAULT_CONSUMER)
local LOG_TTL = tonumber(env("LUA_LOG_TTL", "3600"))
local LOG_PREFIX = env("LUA_LOG_PREFIX", "lua:log:")
-- HMAC-ключ подписи lua:tasks/lua:results — общий с
-- billing. Пустой = подпись отключена (dev-режим, совпадает с Python-стороной).
local SIGNING_KEY = env("BUS_SIGNING_KEY", "")
-- Окно допустимого расхождения времени (anti-replay), см. security/sec/bus_sign.py.
local MAX_SKEW_SEC = tonumber(env("BUS_SIGN_MAX_SKEW_SEC", "300"))
-- Приблизительный потолок длины lua:results.
local RESP_MAXLEN = tonumber(env("LUA_RESP_STREAM_MAXLEN", "10000"))
-- Reclaim зависших задач: раз в LUA_RECLAIM_INTERVAL_SEC
-- проверяем через XPENDING записи, которые провисели в PEL дольше
-- LUA_RECLAIM_MIN_IDLE_MS без ack (например, консьюмер упал после XREADGROUP,
-- но до XACK), забираем их себе через XCLAIM и исполняем как обычные задачи.
local RECLAIM_INTERVAL_SEC = tonumber(env("LUA_RECLAIM_INTERVAL_SEC", "30"))
local RECLAIM_MIN_IDLE_MS = tonumber(env("LUA_RECLAIM_MIN_IDLE_MS", "60000"))
-- Лимит попыток исполнения одной задачи (используем родной delivery-count
-- Redis Streams из XPENDING, отдельный счётчик не нужен) — при превышении
-- задача не reclaim-ится повторно, а сразу считается провалившейся.
local MAX_ATTEMPTS = tonumber(env("LUA_TASK_MAX_ATTEMPTS", "5"))
-- Метрики воркера (счётчики + last_seen) периодически пушатся в Valkey-хэш
-- lua:metrics:{CONSUMER} — billing переэкспортирует их как Prometheus Gauge
-- (см. telemetry/lua_metrics.py). Push, а не pull — у воркера нет своего
-- HTTP-порта для /metrics, и это не нужно вводить только под один эндпоинт.
local METRICS_INTERVAL_SEC = tonumber(env("LUA_METRICS_INTERVAL_SEC", "15"))
local METRICS_PREFIX = env("LUA_METRICS_PREFIX", "lua:metrics:")
-- TTL хэша метрик — больше интервала пуша, чтобы billing не считал воркер
-- живым дольше, чем на самом деле (умерший процесс просто не продлит TTL).
local METRICS_TTL_SEC = tonumber(env("LUA_METRICS_TTL_SEC", "60"))

-- redis-lua не знает stream-команды из коробки — регистрируем их.
for _, cmd in ipairs({ "xadd", "xack", "xgroup", "xreadgroup", "xclaim", "xpending", "xrange", "hset", "expire" }) do
  redis.commands[cmd] = redis.command(cmd:upper())
end

-- Накопленные с момента старта процесса счётчики (сбрасываются в 0 при
-- рестарте воркера — это ожидаемо и видно в Grafana как обрыв графика, а не
-- ошибка сбора метрик).
local metrics = { processed_total = 0, errors_total = 0, reclaimed_total = 0, exec_ms_sum = 0 }
local last_metrics_push = 0

-- Раз в METRICS_INTERVAL_SEC отправить снимок счётчиков в Valkey.
local function maybe_push_metrics(client)
  local now = socket.gettime()
  if now - last_metrics_push < METRICS_INTERVAL_SEC then
    return
  end
  last_metrics_push = now
  local avg_exec_ms = 0
  if metrics.processed_total > 0 then
    avg_exec_ms = metrics.exec_ms_sum / metrics.processed_total
  end
  local key = METRICS_PREFIX .. CONSUMER
  pcall(function()
    client:hset(
      key,
      "processed_total", tostring(metrics.processed_total),
      "errors_total", tostring(metrics.errors_total),
      "reclaimed_total", tostring(metrics.reclaimed_total),
      "avg_exec_ms", string.format("%.2f", avg_exec_ms),
      "last_seen_at", tostring(os.time())
    )
    client:expire(key, METRICS_TTL_SEC)
  end)
end

-- Сравнение строк за постоянное время (не выдаёт длину общего префикса через
-- время выполнения) — используется для сверки HMAC-подписи.
local function ct_equal(a, b)
  if type(a) ~= "string" or type(b) ~= "string" or #a ~= #b then
    return false
  end
  local diff = 0
  for i = 1, #a do
    diff = diff | (string.byte(a, i) ~ string.byte(b, i))
  end
  return diff == 0
end

-- Каноническая строка полей сообщения (без sig), отсортированных по имени —
-- должна побайтово совпадать с `security/sec/bus_sign.py::_canonical`.
local function canonical_fields(map)
  local keys = {}
  for k in pairs(map) do
    if k ~= "sig" then
      keys[#keys + 1] = k
    end
  end
  table.sort(keys)
  local parts = {}
  for _, k in ipairs(keys) do
    parts[#parts + 1] = k .. "=" .. tostring(map[k])
  end
  return table.concat(parts, "\31")
end

-- Проверить подпись+окно времени входящего сообщения. `true`, если подпись
-- отключена (SIGNING_KEY пуст) — совпадает с поведением Python-стороны.
local function verify_signed(map)
  if SIGNING_KEY == "" then
    return true
  end
  local sig, ts = map.sig, map.ts
  if not sig or not ts then
    return false
  end
  local skew = math.abs(socket.gettime() - tonumber(ts))
  if not tonumber(ts) or skew > MAX_SKEW_SEC then
    return false
  end
  local expected = sbox.hmac_sha256_hex(SIGNING_KEY, canonical_fields(map))
  return ct_equal(expected, sig)
end

-- Подписать исходящее сообщение (добавить ts+sig) либо вернуть без изменений,
-- если подпись отключена — совпадает с `security/sec/bus_sign.py::sign_fields`.
local function sign_fields(map)
  if SIGNING_KEY == "" then
    return map
  end
  map.ts = tostring(math.floor(socket.gettime()))
  map.sig = sbox.hmac_sha256_hex(SIGNING_KEY, canonical_fields(map))
  return map
end

local function connect()
  local client = redis.connect(HOST, PORT)
  if DB and DB > 0 then
    client:select(DB)
  end
  -- Создаём consumer-группу (идемпотентно). Стартуем с "0", а не "$", чтобы не
  -- потерять задачи, добавленные в стрим до момента создания группы (cold-start
  -- гонка между продюсером-биллингом и воркером на свежем стеке).
  local ok, err = pcall(function()
    client:xgroup("CREATE", TASK, GROUP, "0", "MKSTREAM")
  end)
  if not ok and not tostring(err):find("BUSYGROUP") then
    error(err)
  end
  return client
end

-- Преобразовать плоский список [k1, v1, k2, v2, ...] в таблицу.
local function fields_to_map(fields)
  local map = {}
  for i = 1, #fields, 2 do
    map[fields[i]] = fields[i + 1]
  end
  return map
end

-- Развернуть таблицу field->value в плоский список для клиента redis-lua.
local function map_to_args(map)
  local args = {}
  for k, v in pairs(map) do
    args[#args + 1] = k
    args[#args + 1] = v
  end
  return args
end

-- Опубликовать подписанный ответ в RESP с ограничением длины стрима (MAXLEN).
local function emit_response(client, fields)
  local resp = sign_fields(fields)
  client:xadd(RESP, "MAXLEN", "~", tostring(RESP_MAXLEN), "*", table.unpack(map_to_args(resp)))
end

local function handle(client, entry_id, map)
  local cid = map.cid or ""
  -- Пробрасываем traceparent из задачи в ответ без интерпретации (симметрично
  -- media:tasks/media:results, см. messaging/mediabus.py + telemetry/otel.py на
  -- billing-стороне) — billing открывает span_from_carrier по нему, сам Lua
  -- не обязан понимать формат W3C traceparent.
  local traceparent = map.traceparent

  if not verify_signed(map) then
    -- Задача с неверной/отсутствующей подписью — не исполняем, сразу ack
    -- (не через reclaim — иначе честно повторяли бы заведомо поддельное
    -- сообщение бесконечно).
    metrics.errors_total = metrics.errors_total + 1
    io.stderr:write("[luaworker] rejected task cid=" .. cid .. ": invalid signature\n")
    emit_response(client, { cid = cid, ok = "0", data = cjson.encode("invalid signature"), traceparent = traceparent })
    client:xack(TASK, GROUP, entry_id)
    return
  end

  local t0 = socket.gettime()
  local ok, result = pcall(handlers.dispatch, map.kind, cjson.decode(map.payload or "{}"))
  metrics.processed_total = metrics.processed_total + 1
  metrics.exec_ms_sum = metrics.exec_ms_sum + (socket.gettime() - t0) * 1000
  if not ok then
    metrics.errors_total = metrics.errors_total + 1
  end

  local data, flag
  if ok then
    flag, data = "1", cjson.encode(result)
    -- Лог выполнения скрипта сохраняем в Valkey на ограниченное время.
    if cid ~= "" and type(result) == "table" and result.logs
      and #result.logs > 0 and LOG_TTL and LOG_TTL > 0 then
      pcall(function()
        client:set(LOG_PREFIX .. cid, cjson.encode(result.logs), "EX", LOG_TTL)
      end)
    end
  else
    flag, data = "0", cjson.encode(tostring(result))
  end

  emit_response(client, { cid = cid, ok = flag, data = data, traceparent = traceparent })
  client:xack(TASK, GROUP, entry_id)
end

-- Раз в RECLAIM_INTERVAL_SEC подхватить зависшие записи PEL: консьюмер мог
-- упасть между XREADGROUP и XACK — сообщение осталось
-- "pending" навсегда без reclaim. Лимит попыток — родной delivery-count из
-- XPENDING, при превышении задача не забирается повторно, а сразу считается
-- провалившейся (ack + failed-результат с причиной max_retries_exceeded).
local function reclaim_once(client)
  local ok, pending = pcall(function()
    return client:xpending(TASK, GROUP, "IDLE", RECLAIM_MIN_IDLE_MS, "-", "+", 50)
  end)
  if not ok or not pending then
    return
  end
  for _, item in ipairs(pending) do
    local id, delivery_count = item[1], tonumber(item[4])
    if delivery_count and delivery_count > MAX_ATTEMPTS then
      -- Лимит попыток исчерпан — забираем cid для отчёта, ack без reclaim.
      local cid = ""
      local ok_r, rows = pcall(function() return client:xrange(TASK, id, id) end)
      if ok_r and rows and rows[1] then
        cid = fields_to_map(rows[1][2]).cid or ""
      end
      io.stderr:write("[luaworker] task " .. id .. " (cid=" .. cid .. ") exceeded max attempts\n")
      client:xack(TASK, GROUP, id)
      emit_response(client, { cid = cid, ok = "0", data = cjson.encode("max_retries_exceeded") })
    else
      local ok_c, claimed = pcall(function()
        return client:xclaim(TASK, GROUP, CONSUMER, RECLAIM_MIN_IDLE_MS, id)
      end)
      if ok_c and claimed then
        for _, entry in ipairs(claimed) do
          metrics.reclaimed_total = metrics.reclaimed_total + 1
          handle(client, entry[1], fields_to_map(entry[2]))
        end
      end
    end
  end
end

local function run_once(client)
  -- BLOCK ограничен RECLAIM_INTERVAL_SEC, а не 0 (бесконечно) — иначе при
  -- отсутствии новых задач reclaim-sweep никогда бы не запускался.
  local reply = client:xreadgroup(
    "GROUP", GROUP, CONSUMER,
    "COUNT", 10, "BLOCK", RECLAIM_INTERVAL_SEC * 1000,
    "STREAMS", TASK, ">"
  )
  if reply then
    for _, stream in ipairs(reply) do
      for _, entry in ipairs(stream[2]) do
        handle(client, entry[1], fields_to_map(entry[2]))
      end
    end
  end
  reclaim_once(client)
  maybe_push_metrics(client)
end

local function main()
  print(string.format("[luaworker] %s -> %s:%d db=%d group=%s", CONSUMER, HOST, PORT, DB, GROUP))
  local client
  while true do
    local ok, err = pcall(function()
      if not client then
        client = connect()
      end
      run_once(client)
    end)
    if not ok then
      io.stderr:write("[luaworker] error: " .. tostring(err) .. "\n")
      client = nil
      socket.sleep(2) -- backoff и переподключение
    end
  end
end

main()
