-- Юнит-тесты ограничений песочницы (sbox.with_limits / sbox.limited_string).
-- Гоняются при сборке образа: падение теста роняет сборку (см. Dockerfile).

package.path = "/app/?.lua;" .. package.path
local sbox = require("sbox")

local function case(name, fn)
  fn()
  print("ok: " .. name)
end

case("бесконечный цикл прерывается по лимиту инструкций", function()
  local ok, err = pcall(sbox.with_limits, function()
    while true do end
  end)
  assert(not ok, "цикл должен был прерваться")
  assert(tostring(err):find("инструкц"), "неожиданная ошибка: " .. tostring(err))
end)

case("обычный код выполняется и возвращает значения", function()
  local a, b = sbox.with_limits(function(x)
    return x + 1, "y"
  end, 41)
  assert(a == 42 and b == "y", "возврат значений сломан")
end)

case("ошибка внутри кода пробрасывается как есть", function()
  local ok, err = pcall(sbox.with_limits, function()
    error("boom")
  end)
  assert(not ok and tostring(err):find("boom"), "ошибка потерялась")
end)

case("бесконечный цикл не обходит лимит через pcall/xpcall", function()
  local ok, err = pcall(sbox.with_limits, function()
    sbox.safe_pcall(function()
      while true do end
    end)
  end)
  assert(not ok, "pcall не должен гасить лимит инструкций")
  assert(tostring(err):find("инструкц"), "неожиданная ошибка: " .. tostring(err))
  assert(debug.gethook() == nil, "хук должен быть снят после перехвата")

  local ok2, err2 = pcall(sbox.with_limits, function()
    sbox.safe_xpcall(function()
      while true do end
    end, function(e) return "caught:" .. tostring(e) end)
  end)
  assert(not ok2, "xpcall не должен гасить лимит инструкций")
  assert(tostring(err2):find("инструкц"), "неожиданная ошибка xpcall: " .. tostring(err2))
  assert(debug.gethook() == nil, "хук должен быть снят после xpcall")
end)

case("хук снимается после выполнения", function()
  assert(debug.gethook() == nil, "хук остался установленным")
end)

case("string.rep ограничен по объёму результата", function()
  local s = sbox.limited_string()
  assert(s.rep("ab", 3) == "ababab", "короткий rep должен работать")
  assert(not pcall(s.rep, "A", 2 ^ 30), "огромный rep должен падать")
  assert(s.upper("x") == "X", "остальные функции string должны быть доступны")
end)

print("ALL LUA SANDBOX TESTS PASSED")
