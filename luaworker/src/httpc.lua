-- HTTP-клиент LuaWorker поверх luasocket/luasec.
-- Поддерживает http и https, произвольные методы, заголовки и тело.

local socket_http = require("socket.http")
local https = require("ssl.https")
local ltn12 = require("ltn12")

local M = {}

--- Выполнить HTTP-запрос.
-- @param p таблица: { url, method?, headers?, body? }
-- @return таблица: { ok, status, headers, body }
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

  local engine = p.url:match("^https://") and https or socket_http
  local ok, code, resp_headers = engine.request(req)

  return {
    ok = ok ~= nil,
    status = code,
    headers = resp_headers or {},
    body = table.concat(sink_buf),
  }
end

return M
