-- HTTP-клиент LuaWorker поверх luasocket/luasec.
-- Поддерживает http и https, произвольные методы, заголовки, тело и таймауты.

local socket_http = require("socket.http")
local https = require("ssl.https")
local ltn12 = require("ltn12")
local sbox = require("sbox")

local M = {}

local function env(key, default)
  local v = os.getenv(key)
  if v == nil or v == "" then
    return default
  end
  return v
end

local DEFAULT_TIMEOUT = tonumber(env("LUA_HTTP_TIMEOUT", "15")) or 15

M.urlencode = sbox.urlencode
M.urldecode = sbox.urldecode
M.parse_form = sbox.parse_form

--- Выполнить HTTP-запрос.
-- @param p таблица: { url, method?, headers?, body?, timeout? }
-- @return таблица: { ok, status, headers, body, error? }
function M.request(p)
  assert(type(p) == "table" and p.url, "http: требуется поле url")

  local body = p.body or ""
  local sink_buf = {}
  local headers = p.headers or {}
  if body ~= "" and not headers["content-length"] then
    headers["content-length"] = tostring(#body)
  end

  local req = {
    url = p.url,
    method = (p.method or "GET"):upper(),
    headers = headers,
    source = ltn12.source.string(body),
    sink = ltn12.sink.table(sink_buf),
  }

  local timeout = tonumber(p.timeout) or DEFAULT_TIMEOUT
  local prev_http_timeout = socket_http.TIMEOUT
  local prev_https_timeout = https.TIMEOUT
  socket_http.TIMEOUT = timeout
  https.TIMEOUT = timeout

  local engine = p.url:match("^https://") and https or socket_http
  local pok, ok, code, resp_headers = pcall(engine.request, req)

  socket_http.TIMEOUT = prev_http_timeout
  https.TIMEOUT = prev_https_timeout

  if not pok then
    return {
      ok = false,
      status = 0,
      headers = {},
      body = "",
      error = tostring(ok),
    }
  end

  return {
    ok = ok ~= nil,
    status = code,
    headers = resp_headers or {},
    body = table.concat(sink_buf),
    error = ok == nil and tostring(code) or nil,
  }
end

return M
