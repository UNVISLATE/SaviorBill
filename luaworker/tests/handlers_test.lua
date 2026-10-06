-- Юнит-тесты M.lint / M.run_script_sandbox (handlers.lua).
-- Гоняются при сборке образа: падение теста роняет сборку (см. Dockerfile).

package.path = "/app/?.lua;" .. package.path
local handlers = require("handlers")

local function case(name, fn)
  fn()
  print("ok: " .. name)
end

case("lint: валидный скрипт проходит без ошибок", function()
  local res = handlers.lint({
    code = "return { handle = function(ctx) return { public = {} } end }",
  })
  assert(res.ok == true, "ожидался ok=true: " .. tostring(res.error))
end)

case("lint: синтаксическая ошибка возвращается, а не падает исключением", function()
  local res = handlers.lint({ code = "this is not lua(" })
  assert(res.ok == false, "ожидался ok=false")
  assert(res.error and #res.error > 0, "ожидалось сообщение об ошибке")
end)

case("lint: скрипт без handle() отклоняется", function()
  local res = handlers.lint({ code = "return { foo = 1 }" })
  assert(res.ok == false, "скрипт без handle должен быть отклонён")
end)

case("lint: http helpers доступны при компиляции-проверке", function()
  local res = handlers.lint({
    code = [[
      return { handle = function(ctx)
        local encoded = http.urlencode({ a = "1" })
        return { public = { s = encoded } }
      end }
    ]],
  })
  assert(res.ok == true, "lint должен поддерживать helpers")
end)

case("run_script_sandbox: возвращает public/private без внешних вызовов", function()
  local res = handlers.run_script_sandbox({
    code = "return { handle = function(ctx) return { public = { x = ctx.n + 1 } } end }",
    ctx = { n = 41 },
  })
  assert(res.public.x == 42, "public.x должен быть 42")
end)

case("run_script_sandbox: http-вызов из скрипта подавляется, а не бьёт наружу", function()
  local res = handlers.run_script_sandbox({
    code = [[
      return { handle = function(ctx)
        local r = http({ url = "http://example.com" })
        return { public = { blocked = (r.error ~= nil) } }
      end }
    ]],
    ctx = {},
  })
  assert(res.public.blocked == true, "http должен быть заглушен в песочнице")
end)

case("run_script_sandbox: billing доступен в песочнице с методами", function()
  local res = handlers.run_script_sandbox({
    code = [[
      return { handle = function(ctx)
        return {
          public = {
            has_billing = (billing ~= nil),
            has_import_keys = (billing and type(billing.import_keys) == "function"),
          }
        }
      end }
    ]],
    ctx = {},
  })
  assert(res.public.has_billing == true, "billing должен существовать в песочнице")
  assert(res.public.has_import_keys == true, "billing.import_keys должен быть функцией")
end)

case("run_script_sandbox: urlencode и parse_form доступны через http и crypto", function()
  local res = handlers.run_script_sandbox({
    code = [[
      return { handle = function(ctx)
        local data = { id = "100", title = "Тест Оплата", fee = "0.5" }
        local qs = http.urlencode(data)
        local parsed = http.parse_form(qs)
        local c_enc = crypto.url_encode("hello world!")
        local c_dec = crypto.url_decode(c_enc)
        return {
          public = {
            qs = qs,
            parsed_title = parsed.title,
            c_dec = c_dec,
          }
        }
      end }
    ]],
    ctx = {},
  })
  assert(res.public.parsed_title == "Тест Оплата", "parse_form должен возвращать русские строки")
  assert(res.public.c_dec == "hello world!", "crypto.url_decode должен декодировать")
end)

print("ALL LUA HANDLERS TESTS PASSED")
