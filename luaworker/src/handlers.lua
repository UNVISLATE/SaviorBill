-- Обработчики задач LuaWorker. Каждый вид задачи (kind) — отдельная функция.

local cjson = require("cjson")
local httpc = require("httpc")
local sbox = require("sbox")
local billing = require("billing")

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
    string = sbox.limited_string(),
    table = table,
    math = math,
  }
  local chunk, err = load(payload.code, "task", "t", sandbox)
  if not chunk then
    error("eval/compile: " .. tostring(err))
  end
  return { result = sbox.with_limits(chunk) }
end

--- lint: только скомпилировать код скрипта, ничего не выполняя.
-- payload: { code = "..." }
-- Проверяет синтаксис и что скрипт возвращает таблицу с handle(ctx) — без
-- побочных эффектов (в отличие от eval/run_script*). Используется редактором
-- перед сохранением/публикацией версии.
function M.lint(payload)
  assert(payload.code, "lint: требуется поле code")
  local sandbox = {
    json = cjson,
    http = setmetatable({
      request = function() error("lint: http недоступен") end,
      urlencode = sbox.urlencode,
      urldecode = sbox.urldecode,
      parse_form = sbox.parse_form,
    }, {
      __call = function() error("lint: http недоступен") end,
    }),
    crypto = sbox.make_crypto(),
    billing = {
      import_keys = function() return { ok = true, imported = 0, duplicates = 0, available_total = 0 } end,
    },
    cache = { get = function() end, set = function() end, del = function() end, incr = function() end },
    log = sbox.make_logger(),
    tostring = tostring,
    tonumber = tonumber,
    pairs = pairs,
    ipairs = ipairs,
    type = type,
    error = error,
    assert = assert,
    pcall = pcall,
    string = sbox.limited_string(),
    table = table,
    math = math,
    os = { time = os.time, date = os.date },
  }
  local chunk, err = load(payload.code, "lint", "t", sandbox)
  if not chunk then
    return { ok = false, error = tostring(err) }
  end
  local ok, mod = pcall(chunk)
  if not ok then
    return { ok = false, error = "runtime error while loading module: " .. tostring(mod) }
  end
  if type(mod) ~= "table" or type(mod.handle) ~= "function" then
    return { ok = false, error = "script must return a table with function handle(ctx)" }
  end
  return { ok = true }
end

--- http: выполнить внешний HTTP-запрос (интеграции, вебхуки).
-- payload: { url, method?, headers?, body?, timeout? }
function M.http(payload)
  return httpc.request(payload)
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

  -- Логгер выполнения, криптография и кэш для скрипта.
  local logger, log_entries = sbox.make_logger()

  local http_api = setmetatable({
    request = httpc.request,
    urlencode = sbox.urlencode,
    urldecode = sbox.urldecode,
    parse_form = sbox.parse_form,
  }, {
    __call = function(_, p)
      return httpc.request(p)
    end,
  })

  -- Песочница: даём json, http, crypto, cache, log (не os/io).
  local sandbox = {
    json = cjson,
    http = http_api,
    billing = billing,
    crypto = sbox.make_crypto(),
    cache = sbox.make_cache(),
    log = logger,
    tostring = tostring,
    tonumber = tonumber,
    pairs = pairs,
    ipairs = ipairs,
    type = type,
    error = error,
    assert = assert,
    pcall = pcall,
    string = sbox.limited_string(),
    table = table,
    math = math,
    os = { time = os.time, date = os.date },
  }
  local chunk, lerr = load(code, "@" .. path, "t", sandbox)
  if not chunk then
    error("run_script/compile: " .. tostring(lerr))
  end

  local mod = sbox.with_limits(chunk)
  if type(mod) ~= "table" or type(mod.handle) ~= "function" then
    error("run_script: скрипт должен вернуть таблицу с функцией handle(ctx)")
  end

  local res = sbox.with_limits(mod.handle, strip_null(payload.ctx or {}))
  if type(res) ~= "table" then
    error("run_script: handle должен вернуть таблицу { public, private }")
  end
  return {
    public = res.public or {},
    private = res.private or {},
    state = res.state,
    expires_at = res.expires_at,
    next_run = res.next_run,
    logs = log_entries,
  }
end

--- run_script_sandbox: как run_script, но с заглушенным http —
-- безопасный test-run для редактора (без реальных внешних вызовов).
-- payload: { code = "...", ctx = { ... } } — код передаётся напрямую (можно
-- гонять несохранённый черновик), а не читается из файла.
function M.run_script_sandbox(payload)
  assert(payload.code, "run_script_sandbox: требуется поле code")

  local logger, log_entries = sbox.make_logger()
  local stub_http = setmetatable({
    request = function(p)
      logger.warn("http вызов подавлен в песочнице test-run: " .. tostring(p and p.url))
      return { ok = false, status = 0, body = "", error = "sandboxed: external http disabled" }
    end,
    urlencode = sbox.urlencode,
    urldecode = sbox.urldecode,
    parse_form = sbox.parse_form,
  }, {
    __call = function(_, p)
      logger.warn("http вызов подавлен в песочнице test-run: " .. tostring(p and p.url))
      return { ok = false, status = 0, body = "", error = "sandboxed: external http disabled" }
    end,
  })

  local sandbox = {
    json = cjson,
    http = stub_http,
    billing = {
      import_keys = function(service, keys)
        logger.info("billing.import_keys вызван в test-run для услуги: " .. tostring(service) .. ", ключей: " .. tostring(keys and #keys or 0))
        return { ok = true, imported = (keys and #keys) or 0, duplicates = 0, available_total = (keys and #keys) or 0 }
      end,
    },
    crypto = sbox.make_crypto(),
    cache = sbox.make_cache(),
    log = logger,
    tostring = tostring,
    tonumber = tonumber,
    pairs = pairs,
    ipairs = ipairs,
    type = type,
    error = error,
    assert = assert,
    pcall = pcall,
    string = sbox.limited_string(),
    table = table,
    math = math,
    os = { time = os.time, date = os.date },
  }
  local chunk, lerr = load(payload.code, "@test-run", "t", sandbox)
  if not chunk then
    error("run_script_sandbox/compile: " .. tostring(lerr))
  end

  local mod = sbox.with_limits(chunk)
  if type(mod) ~= "table" or type(mod.handle) ~= "function" then
    error("run_script_sandbox: скрипт должен вернуть таблицу с функцией handle(ctx)")
  end

  local res = sbox.with_limits(mod.handle, strip_null(payload.ctx or {}))
  if type(res) ~= "table" then
    error("run_script_sandbox: handle должен вернуть таблицу { public, private }")
  end
  return {
    public = res.public or {},
    private = res.private or {},
    state = res.state,
    expires_at = res.expires_at,
    next_run = res.next_run,
    logs = log_entries,
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
