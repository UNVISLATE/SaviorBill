# Справочник методов и API для Lua-скриптов SaviorBill

> Этот документ является актуальным реестром всех методов, глобальных библиотек и хелперов, доступных внутри изолированной песочницы **LuaWorker** (скрипты услуг, триггеры, обработчики платежей). Реестр будет расширяться по мере добавления новых методов взаимодействия с платформой.

---

## 1. Взаимодействие с биллингом (`billing.*`)

Модуль `billing` предоставляет методы для прямого программного управления ресурсами и товарами SaviorBill из Lua-скриптов (авторизуется через внутренний сервисный токен `LUA_SERVICE_TOKEN`).

### `billing.import_keys(service, keys)`

Массовая загрузка цифровых лицензий/ключей в пул указанной услуги.

* **Параметры:**
  * `service` *(number | string, обязательно)*: Числовой идентификатор услуги (`id`) или строковый URL-идентификатор (`slug`, например `"vpn-pro-1m"`).
  * `keys` *(table / array of strings, обязательно)*: Массив строк с уникальными ключами для импорта.
* **Возвращаемое значение:**
  * При успехе:
    ```lua
    {
      ok = true,
      imported = 10,        -- Количество успешно добавленных новых ключей
      duplicates = 0,      -- Количество пропущенных дубликатов (уже существовавших в пуле)
      available_total = 25 -- Текущий суммарный остаток неиспользованных ключей
    }
    ```
  * При ошибке:
    ```lua
    {
      ok = false,
      error = "описание ошибки" -- Например: "Услуга 'vpn-pro-1m' не найдена"
    }
    ```

#### Пример использования в скрипте:
```lua
local M = {}

function M.handle(ctx)
  -- Пример: скрипт автоматического пополнения или генерации ключей
  local generated_keys = {
    "VPN-KEY-ALPHA-001",
    "VPN-KEY-ALPHA-002",
    "VPN-KEY-ALPHA-003",
  }

  local res = billing.import_keys("vpn-pro-1m", generated_keys)
  if not res.ok then
    log.error("Не удалось импортировать ключи:", res.error)
    return {
      public = { error = "Пополнение не удалось" },
      private = { error_detail = res.error },
    }
  end

  log.info("Успешно импортировано ключей:", res.imported, "Всего доступно:", res.available_total)

  return {
    public = { status = "replenished", count = res.imported },
    private = { available = res.available_total },
  }
end

return M
```

---

## 2. Сетевые запросы (`http.*`)

Клиент HTTP для интеграции с внешними API, платежными шлюзами и вебхуками.

* **`http.request(opts)`** (или просто вызов `http(opts)`):
  * `url` *(string, обязательно)*: Целевой URL (`http://` или `https://`).
  * `method` *(string, по умолчанию `"GET"`)*: HTTP-метод (`"GET"`, `"POST"`, `"PUT"`, `"PATCH"`, `"DELETE"`).
  * `headers` *(table, опционально)*: Заголовки запроса (`{ ["Authorization"] = "Bearer ...", ["Content-Type"] = "application/json" }`).
  * `body` *(string, опционально)*: Тело запроса.
  * `timeout` *(number, по умолчанию 15)*: Сетевой таймаут в секундах.
  * **Возвращает:** `{ ok = bool, status = int, headers = table, body = string, error = string }`.

* **`http.urlencode(tbl)`**:
  * Преобразует плоскую Lua-таблицу вида `{ search = "ключ слово", page = 1 }` в экранированную query-строку `search=%D0%BA%D0%BB%D1%8E%D1%87+%D1%81%D0%BB%D0%BE%D0%B2%D0%BE&page=1`.

* **`http.parse_form(body)`**:
  * Разбирает тело запроса `application/x-www-form-urlencoded` в удобную Lua-таблицу.

---

## 3. Криптография (`crypto.*`)

Безопасные криптографические операции поверх OpenSSL:
* `crypto.sha256(data)` — SHA-256 хеш (hex-строка).
* `crypto.hmac_sha256(key, data)` — HMAC-SHA256 подпись (hex-строка).
* `crypto.md5(data)` — MD5 хеш.
* `crypto.random_bytes(len)` — криптографически стойкие случайные байты.
* `crypto.random_hex(len)` — случайная hex-строка.
* `crypto.base64_encode(str)` / `crypto.base64_decode(str)` — Base64 кодирование/декодирование.

---

## 4. Быстрый изолированный кэш (`cache.*`)

Хранилище ключ-значение в оперативной памяти Valkey:
* `cache.get(key)` — получить значение (строка или `nil`).
* `cache.set(key, value, [ttl_seconds])` — сохранить значение с опциональным временем жизни в секундах.
* `cache.del(key)` — удалить ключ.
* `cache.incr(key)` — атомарный инкремент счётчика.

---

## 5. Логирование (`log.*`)

Записи логов связываются с задачей в журнале аудита и сохраняются для просмотра администратором:
* `log.info(...)` (или `log(...)`) — информационное сообщение.
* `log.warn(...)` — предупреждение.
* `log.error(...)` — ошибка выполнения.

---

## 6. Работа с JSON (`json.*`)

* `json.encode(tbl)` — сериализация Lua-таблицы в JSON-строку.
* `json.decode(str)` — парсинг JSON-строки в Lua-таблицу (значения `null` автоматически конвертируются в привычный `nil`).
