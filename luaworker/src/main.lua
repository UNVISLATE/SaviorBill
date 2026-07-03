-- LuaWorker: исполнитель Lua-задач из шины Redis Streams (Valkey).
--
-- Поток работы:
--   1. Биллинг публикует задачу в LUA_TASK_STREAM (XADD) с полями cid/kind/payload.
--   2. Воркер читает её через consumer-группу (XREADGROUP), исполняет handler.
--   3. Результат публикуется в LUA_RESP_STREAM (XADD) с полями cid/ok/data.
--   4. Задача подтверждается (XACK).

local redis = require("redis")
local cjson = require("cjson")
local socket = require("socket")
local handlers = require("handlers")

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

-- redis-lua не знает stream-команды из коробки — регистрируем их.
for _, cmd in ipairs({ "xadd", "xack", "xgroup", "xreadgroup" }) do
  redis.commands[cmd] = redis.command(cmd:upper())
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

local function handle(client, entry_id, map)
  local cid = map.cid or ""
  local ok, result = pcall(handlers.dispatch, map.kind, cjson.decode(map.payload or "{}"))

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

  client:xadd(RESP, "*", "cid", cid, "ok", flag, "data", data)
  client:xack(TASK, GROUP, entry_id)
end

local function run_once(client)
  -- BLOCK 0 — ждём появления задачи без активного поллинга.
  local reply = client:xreadgroup(
    "GROUP", GROUP, CONSUMER,
    "COUNT", 10, "BLOCK", 0,
    "STREAMS", TASK, ">"
  )
  if not reply then
    return
  end
  for _, stream in ipairs(reply) do
    for _, entry in ipairs(stream[2]) do
      handle(client, entry[1], fields_to_map(entry[2]))
    end
  end
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
