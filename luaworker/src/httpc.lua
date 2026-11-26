-- HTTP-клиент LuaWorker поверх luasocket/luasec.
-- Поддерживает http и https, произвольные методы, заголовки, тело и таймауты.

local socket = require("socket")
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
local MAX_TIMEOUT = tonumber(env("LUA_MAX_HTTP_TIMEOUT", "30")) or 30
local DEFAULT_MAX_BODY_BYTES = tonumber(env("LUA_MAX_HTTP_BODY_BYTES", "10485760")) or 10485760

M.urlencode = sbox.urlencode
M.urldecode = sbox.urldecode
M.parse_form = sbox.parse_form

local function is_private_ipv4(ip)
  local a, b, c, d = ip:match("^(%d+)%.(%d+)%.(%d+)%.(%d+)$")
  if not a then
    return false
  end
  a, b, c, d = tonumber(a), tonumber(b), tonumber(c), tonumber(d)
  if a > 255 or b > 255 or c > 255 or d > 255 then
    return false
  end
  if a == 10 or a == 127 or a == 0 then
    return true
  end
  if a == 169 and b == 254 then
    return true
  end
  if a == 172 and b >= 16 and b <= 31 then
    return true
  end
  if a == 192 and b == 168 then
    return true
  end
  if a == 100 and b >= 64 and b <= 127 then
    return true
  end
  return false
end

local function is_private_ipv6(host)
  if host == "::1" or host == "::" then
    return true
  end
  if host:match("^fe[89ab][0-9a-f]:") or host:match("^fc") or host:match("^fd") then
    return true
  end
  -- IPv4-mapped IPv6 (e.g. ::ffff:127.0.0.1 or ::ffff:7f00:1)
  local v4 = host:match("::ffff:(%d+%.%d+%.%d+%.%d+)$")
  if v4 and is_private_ipv4(v4) then
    return true
  end
  if host:match("::ffff:") then
    return true
  end
  return false
end

local function is_alternative_ip_literal(host)
  -- Decimal integer IP (e.g. 2130706433) or hex (0x7f000001) or octal dotted
  if host:match("^%d+$") or host:match("^0x[0-9a-f]+$") then
    return true
  end
  -- Dotted with hex/octal/leading-zero octets (e.g. 0177.0.0.1, 0x7f.0.0.1)
  if host:match("^0x") or host:match("%.0x") then
    return true
  end
  local a, b, c, d = host:match("^([^%.]+)%.([^%.]+)%.([^%.]+)%.([^%.]+)$")
  if a and tonumber(a) and tonumber(b) and tonumber(c) and tonumber(d) then
    if (a:match("^0%d") or b:match("^0%d") or c:match("^0%d") or d:match("^0%d")) then
      return true
    end
  end
  return false
end

local function is_private_host(url)
  -- Block userinfo in URL authority (e.g. http://evil.com@127.0.0.1/)
  if url:match("^https?://[^/?#]*@") then
    return true
  end
  local host = url:match("^https?://([^/:?#]+)")
  if not host then
    return true
  end
  host = host:gsub("^%[", ""):gsub("%]$", ""):lower()
  if host == "localhost" or host:sub(-6) == ".local" or host:sub(-9) == ".internal" then
    return true
  end
  if is_private_ipv6(host) or is_alternative_ip_literal(host) or is_private_ipv4(host) then
    return true
  end
  if socket.dns and socket.dns.getaddrinfo then
    local infos = socket.dns.getaddrinfo(host)
    if type(infos) == "table" then
      for _, info in ipairs(infos) do
        local addr = type(info) == "table" and info.addr or nil
        if type(addr) == "string" then
          local norm = addr:lower()
          if is_private_ipv4(norm) or is_private_ipv6(norm) then
            return true
          end
        end
      end
    end
  elseif socket.dns and socket.dns.toip then
    local resolved = socket.dns.toip(host)
    if resolved and is_private_ipv4(resolved) then
      return true
    end
  end
  return false
end

local function do_request(p, allow_private)
  assert(type(p) == "table" and p.url, "http: требуется поле url")
  local url = tostring(p.url)
  if not url:match("^https?://") then
    return {
      ok = false,
      status = 0,
      headers = {},
      body = "",
      error = "http: only http:// and https:// URLs are allowed",
    }
  end

  if not allow_private and env("LUA_HTTP_BLOCK_PRIVATE", "1") ~= "0" and is_private_host(url) then
    return {
      ok = false,
      status = 0,
      headers = {},
      body = "",
      error = "ssrf: private network target blocked",
    }
  end

  local body = p.body or ""
  local headers = {}
  local has_content_length = false
  if type(p.headers) == "table" then
    for k, v in pairs(p.headers) do
      headers[k] = v
      if type(k) == "string" and k:lower() == "content-length" then
        has_content_length = true
      end
    end
  end
  if body ~= "" and not has_content_length then
    headers["content-length"] = tostring(#body)
  end

  local max_bytes = tonumber(p.max_bytes) or DEFAULT_MAX_BODY_BYTES
  if max_bytes > DEFAULT_MAX_BODY_BYTES then
    max_bytes = DEFAULT_MAX_BODY_BYTES
  end

  local sink_buf = {}
  local total_bytes = 0
  local function limited_sink(chunk, err)
    if chunk == nil then
      return 1
    end
    total_bytes = total_bytes + #chunk
    if total_bytes > max_bytes then
      return nil, "http: response body exceeds " .. tostring(max_bytes) .. " bytes"
    end
    sink_buf[#sink_buf + 1] = chunk
    return 1
  end

  local req = {
    url = url,
    method = (p.method or "GET"):upper(),
    headers = headers,
    source = ltn12.source.string(body),
    sink = limited_sink,
    redirect = false,
  }

  local timeout = tonumber(p.timeout) or DEFAULT_TIMEOUT
  if timeout < 1 then
    timeout = 1
  elseif timeout > MAX_TIMEOUT then
    timeout = MAX_TIMEOUT
  end
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

--- Выполнить внешний HTTP-запрос (с защитой от SSRF).
function M.request(p)
  return do_request(p, false)
end

--- Внутренний HTTP-запрос (только для billing.lua / fetch_artifact, не отдавать в sandbox).
function M.internal_request(p)
  return do_request(p, true)
end

return M
