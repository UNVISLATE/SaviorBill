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

Новый вид задачи — это новая функция в `src/handlers.lua`.

## Переменные окружения
`VALKEY_HOST/PORT/DB`, `LUA_TASK_STREAM`, `LUA_RESP_STREAM`, `LUA_GROUP`,
`LUA_CONSUMER`, `BILLING_URL`, `LUA_SERVICE_TOKEN` (сервисный токен для команд
биллинга).

## Локально
```bash
docker compose up --build luaworker
```

## Пример из Python
```python
from dependencies.lua import get_lua_bus

bus = get_lua_bus(request)
res = await bus.call("http", {"url": "https://api.example.com/ping"})
res = await bus.call("eval", {"code": "return data.x + data.y", "data": {"x": 2, "y": 3}})
```
