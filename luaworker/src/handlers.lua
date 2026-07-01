-- Обработчики задач LuaWorker. Каждый вид задачи (kind) — отдельная функция.
-- Контракт данных задаётся Python-стороной (Pydantic), сюда приходит уже
-- декодированная из JSON таблица payload.

local cjson = require("cjson")
local httpc = require("httpc")

local M = {}

local function env(key, default)
  local v = os.getenv(key)
  if v == nil or v == "" then
    return default
  end
  return v
end

--- eval: исполнить переданный Lua-код в песочнице.
-- payload: { code = "...", data = { ... } }
-- В коде доступны: data (вход), json (cjson). Возврат кода кладётся в result.
function M.eval(payload)
  assert(payload.code, "eval: требуется поле code")
  local sandbox = {
    data = payload.data,
    json = cjson,
    tostring = tostring,
    tonumber = tonumber,
    pairs = pairs,
    ipairs = ipairs,
    string = string,
    table = table,
    math = math,
  }
  local chunk, err = load(payload.code, "task", "t", sandbox)
  if not chunk then
    error("eval/compile: " .. tostring(err))
  end
  return { result = chunk() }
end

--- http: выполнить внешний HTTP-запрос (интеграции, вебхуки).
-- payload: { url, method?, headers?, body? }
function M.http(payload)
  return httpc.request(payload)
end

--- billing: отправить команду ядру биллинга через внутренний HTTP API.
-- payload: { cmd = "charge", args = { ... } }
function M.billing(payload)
  assert(payload.cmd, "billing: требуется поле cmd")
  local base = env("BILLING_URL", "http://billing:8000")
  local token = env("LUA_SERVICE_TOKEN", "")
  return httpc.request({
    url = base .. "/api/v1/internal/" .. payload.cmd,
    method = "POST",
    headers = {
      ["content-type"] = "application/json",
      ["authorization"] = "Bearer " .. token,
    },
    body = cjson.encode(payload.args or {}),
  })
end

-- Безопасно собрать путь к файлу скрипта внутри LUA_SCRIPTS_DIR.
local function script_path(filename)
  assert(type(filename) == "string" and filename ~= "", "run_script: требуется script")
  if filename:find("%.%.") or filename:sub(1, 1) == "/" then
    error("run_script: недопустимый путь скрипта")
  end
  local dir = env("LUA_SCRIPTS_DIR", "/lua")
  return dir .. "/" .. filename
end

-- Команды биллинга, доступные внутри скрипта (обёртка над M.billing).
local function make_billing()
  return setmetatable({}, {
    __index = function(_, cmd)
      return function(args)
        return M.billing({ cmd = cmd, args = args })
      end
    end,
  })
end

-- Рекурсивно заменить JSON null (cjson.null, userdata) на nil, чтобы скрипты
-- могли использовать привычное `value or default`. Ключи со значением null
-- просто исчезают из таблицы.
local function strip_null(v)
  if v == cjson.null then
    return nil
  end
  if type(v) == "table" then
    for k, item in pairs(v) do
      v[k] = strip_null(item)
    end
  end
  return v
end

--- run_script: загрузить файл скрипта из монтируемой папки и выполнить его
-- handle(ctx). Скрипт изолирует внешнюю интеграцию (услуга/платёж) и обязан
-- вернуть таблицу вида { public = {...}, private = {...} }.
-- payload: { script = "services/x.lua", ctx = { ... } }
function M.run_script(payload)
  local path = script_path(payload.script)
  local source, rerr = io.open(path, "r")
  if not source then
    error("run_script: файл не найден: " .. tostring(rerr))
  end
  local code = source:read("*a")
  source:close()

  -- Песочница: даём json, http и команды биллинга, но не os/io.
  local sandbox = {
    json = cjson,
    http = function(p)
      return httpc.request(p)
    end,
    billing = make_billing(),
    tostring = tostring,
    tonumber = tonumber,
    pairs = pairs,
    ipairs = ipairs,
    type = type,
    error = error,
    assert = assert,
    pcall = pcall,
    string = string,
    table = table,
    math = math,
    os = { time = os.time, date = os.date },
  }
  local chunk, lerr = load(code, "@" .. path, "t", sandbox)
  if not chunk then
    error("run_script/compile: " .. tostring(lerr))
  end

  local mod = chunk()
  if type(mod) ~= "table" or type(mod.handle) ~= "function" then
    error("run_script: скрипт должен вернуть таблицу с функцией handle(ctx)")
  end

  local res = mod.handle(strip_null(payload.ctx or {}))
  if type(res) ~= "table" then
    error("run_script: handle должен вернуть таблицу { public, private }")
  end
  return {
    public = res.public or {},
    private = res.private or {},
    state = res.state,
    expires_at = res.expires_at,
    next_run = res.next_run,
  }
end

--- Диспетчер по типу задачи.
function M.dispatch(kind, payload)
  local fn = M[kind]
  if type(fn) ~= "function" or kind == "dispatch" then
    error("неизвестный вид задачи: " .. tostring(kind))
  end
  return fn(payload)
end

return M
