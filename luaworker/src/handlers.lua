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
      send_email = function() return { ok = true } end,
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
    pcall = sbox.safe_pcall,
    xpcall = sbox.safe_xpcall,
    string = sbox.limited_string(),
    table = table,
    math = math,
    os = { time = os.time, date = os.date },
  }
  local chunk, err = load(payload.code, "lint", "t", sandbox)
  if not chunk then
    return { ok = false, error = tostring(err) }
  end
  local ok, mod = pcall(sbox.with_limits, chunk)
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

-- Локальный иммутабельный кэш артефактов для кластера без общего диска.
local function cache_dir_for(cache_key)
  local base = env("LUA_CACHE_DIR", "/tmp/lua_cache")
  return base .. "/" .. cache_key
end

local function fetch_artifact(payload)
  local script_id = payload.script_id
  local version = payload.script_version
  if not script_id or not version then
    return nil, "missing script_id/script_version for pull"
  end

  local cache_key = tostring(payload.script_sha256 or (tostring(script_id) .. "_v" .. tostring(version)))
  if not cache_key:match("^[A-Za-z0-9_%-]+$") then
    return nil, "invalid cache_key"
  end
  local dir = cache_dir_for(cache_key)
  local init_path = dir .. "/init.lua"
  local f = io.open(init_path, "r")
  if f then
    local code = f:read("*a")
    f:close()
    return code, dir
  end

  local billing_url = env("BILLING_URL", "http://billing:8000")
  local token = billing._read_service_token()
  local url = string.format("%s/api/v1/internal/lua/artifacts/%s/%s", billing_url, tostring(script_id), tostring(version))
  local resp = httpc.request({
    url = url,
    method = "GET",
    headers = {
      ["Authorization"] = "Bearer " .. token,
    },
    timeout = 15,
  })
  if not resp or not resp.ok or not resp.body then
    return nil, "artifact pull failed: " .. tostring(resp and (resp.error or resp.status) or "unknown")
  end

  local headers = resp.headers or {}
  local art_type = headers["x-artifact-type"] or "lua"
  local tmp_dir = dir .. ".tmp." .. tostring(os.time())
  os.execute("mkdir -p " .. string.format("%q", tmp_dir))

  if art_type == "tar.gz" then
    local tgz = tmp_dir .. "/bundle.tar.gz"
    local tf, terr = io.open(tgz, "wb")
    if not tf then
      return nil, "cannot write temp bundle: " .. tostring(terr)
    end
    tf:write(resp.body)
    tf:close()
    local ok = os.execute("tar -xzf " .. string.format("%q", tgz) .. " -C " .. string.format("%q", tmp_dir))
    os.remove(tgz)
    if not ok then
      return nil, "failed to extract lua tar.gz bundle"
    end
  else
    local lf, lerr = io.open(tmp_dir .. "/init.lua", "w")
    if not lf then
      return nil, "cannot write temp script: " .. tostring(lerr)
    end
    lf:write(resp.body)
    lf:close()
  end

  os.execute("mv -f " .. string.format("%q", tmp_dir) .. " " .. string.format("%q", dir))
  local rf = io.open(init_path, "r")
  if not rf then
    return nil, "init.lua missing in artifact"
  end
  local code = rf:read("*a")
  rf:close()
  return code, dir
end

--- run_script: загрузить файл скрипта из монтируемой папки (или кэша/HTTP pull)
-- и выполнить его handle(ctx).
-- payload: { script = "services/x.lua", script_id?, script_version?, script_sha256?, ctx = { ... } }
function M.run_script(payload)
  local path = script_path(payload.script)
  local code = nil
  local artifact_dir = nil
  local source = io.open(path, "r")
  if source then
    code = source:read("*a")
    source:close()
  else
    local pull_err
    code, artifact_dir = fetch_artifact(payload)
    if not code then
      error("run_script: файл не найден и pull не удался: " .. tostring(artifact_dir))
    end
  end

  if artifact_dir and env("ALLOW_NATIVE_LUA_MODULES", "false") == "true" then
    local prev_cpath = package.cpath
    if not prev_cpath:find(artifact_dir, 1, true) then
      package.cpath = artifact_dir .. "/?.so;" .. prev_cpath
    end
  end

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
    pcall = sbox.safe_pcall,
    xpcall = sbox.safe_xpcall,
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
      send_email = function(opts)
        logger.info("billing.send_email called in test-run for: " .. tostring(opts and opts.to) .. ", template: " .. tostring(opts and opts.template))
        return { ok = true }
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
    pcall = sbox.safe_pcall,
    xpcall = sbox.safe_xpcall,
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
