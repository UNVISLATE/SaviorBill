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

case("lint: http/billing недоступны при компиляции-проверке (не должны падать сборку)", function()
  local res = handlers.lint({
    code = "return { handle = function(ctx) return { public = {} } end }",
  })
  assert(res.ok == true, "lint не должен требовать реальных http/billing")
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

case("run_script_sandbox: billing-вызов из скрипта подавляется", function()
  local res = handlers.run_script_sandbox({
    code = [[
      return { handle = function(ctx)
        local r = billing.charge({})
        return { public = { blocked = (r.ok == false) } }
      end }
    ]],
    ctx = {},
  })
  assert(res.public.blocked == true, "billing должен быть заглушен в песочнице")
end)

print("ALL LUA HANDLERS TESTS PASSED")
