-- Юнит-тесты httpc.lua (таймауты, urlencode, parse_form).

package.path = "/app/?.lua;" .. package.path
local httpc = require("httpc")

local function case(name, fn)
  fn()
  print("ok: " .. name)
end

case("httpc: urlencode таблицы и строки", function()
  local s = httpc.urlencode("привет world")
  assert(s:find("world"), "строка должна быть закодирована")
  assert(httpc.urldecode(s) == "привет world", "urldecode должен восстановить строку")

  local tbl = { foo = "bar", n = 123, space = "a b" }
  local qs = httpc.urlencode(tbl)
  assert(qs:find("foo=bar"), "query string должен содержать foo=bar")
  assert(qs:find("n=123"), "query string должен содержать n=123")
  assert(qs:find("space=a%%20b") or qs:find("space=a%+b"), "query string должен кодировать пробел")

  local parsed = httpc.parse_form(qs)
  assert(parsed.foo == "bar", "parsed.foo должен быть bar")
  assert(parsed.n == "123", "parsed.n должен быть 123")
  assert(parsed.space == "a b", "parsed.space должен быть 'a b'")
end)

case("httpc: кастомный таймаут отрабатывает быстро при недоступном хосте", function()
  local t0 = os.clock()
  local res = httpc.request({
    url = "http://192.0.2.1:81", -- RFC 5737 TEST-NET-1 (non-routable, drops packets)
    timeout = 1,
  })
  local dt = os.clock() - t0
  assert(res.ok == false, "запрос должен завершиться с ошибкой")
  assert(res.error == "timeout" or res.status == "timeout", "ошибка должна быть timeout")
  assert(dt < 3, "таймаут должен сработать за ~1-2 сек, а не висеть минуту: " .. tostring(dt))
end)

print("ALL LUA HTTPC TESTS PASSED")
