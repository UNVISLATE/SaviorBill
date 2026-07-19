-- Библиотека песочницы LuaWorker: логирование выполнения, криптография и кэш.
-- Эти наборы функций пробрасываются в скрипты (run_script).

local cjson = require("cjson")

local M = {}

local function env(key, default)
  local v = os.getenv(key)
  if v == nil or v == "" then
    return default
  end
  return v
end

-- Логгер выполнения: собирает записи { ts, level, msg } и возвращает их ядру.
function M.make_logger()
  local entries = {}
  local function record(level, ...)
    local parts = {}
    for i = 1, select("#", ...) do
      parts[#parts + 1] = tostring(select(i, ...))
    end
    entries[#entries + 1] = {
      ts = os.time(),
      level = level,
      msg = table.concat(parts, " "),
    }
  end
  local api = setmetatable({
    info = function(...) record("info", ...) end,
    warn = function(...) record("warn", ...) end,
    error = function(...) record("error", ...) end,
    entries = entries,
  }, {
    -- log("...") == log.info("...")
    __call = function(_, ...) record("info", ...) end,
  })
  return api, entries
end

-- Криптография поверх OpenSSL (luaossl). hex/base64 — чистый Lua.
local B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"

local function b64encode(data)
  local out = {}
  local len = #data
  local i = 1
  while i <= len do
    local a = string.byte(data, i) or 0
    local b = string.byte(data, i + 1)
    local c = string.byte(data, i + 2)
    local n = a * 65536 + (b or 0) * 256 + (c or 0)
    local c1 = math.floor(n / 262144) % 64
    local c2 = math.floor(n / 4096) % 64
    local c3 = math.floor(n / 64) % 64
    local c4 = n % 64
    out[#out + 1] = string.sub(B64, c1 + 1, c1 + 1)
    out[#out + 1] = string.sub(B64, c2 + 1, c2 + 1)
    out[#out + 1] = b and string.sub(B64, c3 + 1, c3 + 1) or "="
    out[#out + 1] = c and string.sub(B64, c4 + 1, c4 + 1) or "="
    i = i + 3
  end
  return table.concat(out)
end

local _b64lookup
local function b64decode(data)
  if not _b64lookup then
    _b64lookup = {}
    for idx = 1, #B64 do
      _b64lookup[string.sub(B64, idx, idx)] = idx - 1
    end
  end
  data = string.gsub(data, "[^" .. B64 .. "=]", "")
  local out = {}
  local i = 1
  while i <= #data do
    local c1 = _b64lookup[string.sub(data, i, i)] or 0
    local c2 = _b64lookup[string.sub(data, i + 1, i + 1)] or 0
    local c3ch = string.sub(data, i + 2, i + 2)
    local c4ch = string.sub(data, i + 3, i + 3)
    local c3 = _b64lookup[c3ch] or 0
    local c4 = _b64lookup[c4ch] or 0
    local n = c1 * 262144 + c2 * 4096 + c3 * 64 + c4
    out[#out + 1] = string.char(math.floor(n / 65536) % 256)
    if c3ch ~= "=" and c3ch ~= "" then
      out[#out + 1] = string.char(math.floor(n / 256) % 256)
    end
    if c4ch ~= "=" and c4ch ~= "" then
      out[#out + 1] = string.char(n % 256)
    end
    i = i + 4
  end
  return table.concat(out)
end

local function to_hex(bin)
  return (string.gsub(bin, ".", function(ch)
    return string.format("%02x", string.byte(ch))
  end))
end

function M.make_crypto()
  local ok_d, digest = pcall(require, "openssl.digest")
  local ok_h, hmac = pcall(require, "openssl.hmac")

  local function hash(algo, s)
    if not ok_d then
      error("crypto: openssl.digest недоступен")
    end
    return to_hex(digest.new(algo):final(s))
  end

  return {
    base64_encode = b64encode,
    base64_decode = b64decode,
    hex = to_hex,
    md5 = function(s) return hash("md5", s) end,
    sha1 = function(s) return hash("sha1", s) end,
    sha256 = function(s) return hash("sha256", s) end,
    sha512 = function(s) return hash("sha512", s) end,
    hmac_sha256 = function(key, s)
      if not ok_h then
        error("crypto: openssl.hmac недоступен")
      end
      return to_hex(hmac.new(key, "sha256"):final(s))
    end,
    hmac_sha512 = function(key, s)
      if not ok_h then
        error("crypto: openssl.hmac недоступен")
      end
      return to_hex(hmac.new(key, "sha512"):final(s))
    end,
  }
end

-- Кэш поверх Valkey (redis-lua). Ключи изолируются префиксом.
function M.make_cache()
  local redis = require("redis")
  local host = env("VALKEY_HOST", "valkey")
  local port = tonumber(env("VALKEY_PORT", "6379"))
  local db = tonumber(env("VALKEY_DB", "0"))
  local prefix = env("LUA_CACHE_PREFIX", "luacache:")
  local conn

  local function client()
    if not conn then
      conn = redis.connect(host, port)
      if db and db > 0 then
        conn:select(db)
      end
    end
    return conn
  end

  return {
    get = function(key)
      local v = client():get(prefix .. tostring(key))
      if v == nil or v == false then
        return nil
      end
      return v
    end,
    set = function(key, value, ttl)
      local k = prefix .. tostring(key)
      if ttl and tonumber(ttl) and tonumber(ttl) > 0 then
        return client():set(k, tostring(value), "EX", math.floor(tonumber(ttl)))
      end
      return client():set(k, tostring(value))
    end,
    del = function(key)
      return client():del(prefix .. tostring(key))
    end,
    incr = function(key)
      return client():incr(prefix .. tostring(key))
    end,
  }
end

M.to_hex = to_hex
M.encode_json = cjson.encode
M.decode_json = cjson.decode

-- HMAC-SHA256(hex) — используется в main.lua для подписи шины lua:tasks/
-- lua:results (см. AUDIT.md H1), а также доступен как sbox.make_crypto()
-- внутри пользовательских скриптов.
function M.hmac_sha256_hex(key, s)
  local ok_h, hmac = pcall(require, "openssl.hmac")
  if not ok_h then
    error("crypto: openssl.hmac недоступен (нужен для подписи шины, см. AUDIT.md H1)")
  end
  return to_hex(hmac.new(key, "sha256"):final(s))
end

return M
