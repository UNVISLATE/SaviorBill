# LuaWorker

Изолированный исполнитель Lua-задач для SaviorBill. Запускается **отдельным
контейнером** и общается с ядром через **Redis Streams (Valkey)**.

## Зачем
Согласно архитектуре Lua — это «движок интеграций»: платёжные
системы, вебхуки, внешние API. Логика обновляется без пересборки Python-ядра —
достаточно поменять Lua-задачу/обработчик.

## Как работает шина
```
Python (LuaBus.call)                    LuaWorker
   |  XADD lua:tasks  cid/kind/payload      |
   | -------------------------------------> | XREADGROUP (BLOCK 0)
   |                                        | handlers.dispatch(kind, payload)
   |  XADD lua:results cid/ok/data          |
   | <------------------------------------- | XACK lua:tasks
   |  XREAD lua:results (match cid)         |
```

- Корреляция запрос/ответ — по полю `cid`.
- Задачи читаются consumer-группой `LUA_GROUP` (горизонтально масштабируется:
  поднимите несколько реплик с разными `LUA_CONSUMER`).

## Виды задач (`kind`)
| kind      | payload                                   | назначение                          |
|-----------|-------------------------------------------|-------------------------------------|
| `eval`    | `{ code, data }`                          | исполнить Lua-код в песочнице        |
| `http`    | `{ url, method?, headers?, body? }`       | внешний HTTP-запрос (интеграции)     |
| `billing` | `{ cmd, args }`                           | команда ядру биллинга (внутр. API)   |
| `run_script` | `{ script, kind?, ctx }`               | загрузить и выполнить `handle(ctx)`  |

Новый вид задачи — это новая функция в `src/handlers.lua`.

### Песочница `run_script`
Скриптам (service/payment/trigger) доступны, помимо `json`/`http`/`billing`:

- `log(...)`, `log.info/warn/error(...)` — лог выполнения; записи возвращаются в
  результате (`logs`) и сохраняются в Valkey ключом `LUA_LOG_PREFIX..cid` с TTL
  `LUA_LOG_TTL` (по умолчанию 3600 с);
- `crypto` — `sha1/sha256/sha512/md5`, `hmac_sha256/hmac_sha512`,
  `base64_encode/base64_decode`, `hex` (поверх OpenSSL/luaossl);
- `cache` — `get/set(key,val,ttl?)/del/incr` поверх Valkey (префикс
  `LUA_CACHE_PREFIX`).

## Переменные окружения
`VALKEY_HOST/PORT/DB`, `LUA_TASK_STREAM`, `LUA_RESP_STREAM`, `LUA_GROUP`,
`LUA_CONSUMER`, `BILLING_URL`, `LUA_SERVICE_TOKEN` (сервисный токен для команд
биллинга), `LUA_LOG_TTL`, `LUA_LOG_PREFIX`, `LUA_CACHE_PREFIX`.

## Пример использования LuaBus в Python-коде биллинга
```python
from dependencies.lua import get_lua_bus

bus = get_lua_bus(request)
res = await bus.call("http", {"url": "https://api.example.com/ping"})
res = await bus.call("eval", {"code": "return data.x + data.y", "data": {"x": 2, "y": 3}})
```
