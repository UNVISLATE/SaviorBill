# SaviorBill: правила работы с кодом

Эти правила описывают проектный процесс и применяются вместе с документацией
конкретной подсистемы. Архитектурные решения ищутся в `docs/`, README рядом с
подсистемой и в актуальных design-документах, если они есть.

## Общие правила

- Делать точечные изменения в рамках задачи. Несвязанный код не менять.
- Не оставлять мёртвый код, закомментированные обходы и временные заглушки.
- Если временный workaround неизбежен, явно описать причину и дальнейший план.
- Перед добавлением helper/логики искать существующий аналог и переиспользовать
  его.
- Не добавлять зависимости и инструменты без необходимости.
- Не добавлять комментарии, которые повторяют код. Комментарий должен объяснять
  только неочевидную причину или ограничение.
- Не скрывать ошибки широкими `except` и silent fallback. Ошибки должны быть
  обработаны по существующему контракту или переданы выше.

## Структура

- Billing-код находится в `src/`.
- Billing-интеграции с Lua находятся в `src/lua/`.
- Исполнитель Lua и его runtime-код находятся в `luaworker/src/`.
- Mediaworker находится в `mediaworker/src/`.
- Admin UI находится в `adminui/src/`.
- Lua-скрипты интеграций хранятся отдельно от runtime-кода: рабочие — в
  `data/lua/`, примеры — в `examples/lua/`, тестовые — в `tests/data/lua/`.
- Актуальный контракт Lua и инструкция для ИИ находятся в
  `docs/lua/scripts.md` и `docs/lua/llms.txt`. Перед созданием или изменением
  Lua-скрипта эти файлы нужно прочитать и сверить с исходным кодом
  `src/lua/`, `luaworker/src/handlers.lua` и соответствующими схемами.
- При изменении Lua-контракта в коде одновременно обновлять
  `docs/lua/scripts.md`, `docs/lua/llms.txt`, примеры, тестовые Lua-скрипты и
  связанные схемы/тесты. Не оставлять документацию с прежними полями,
  действиями или форматами результата.
- WS-роуты billing находятся в `src/apiws/v1/` и регистрируются в
  `src/apiws/v1/__init__.py`. Общую авторизацию брать из
  `src/apiws/authctx.py`, если конкретному handshake не нужен отдельный
  протокол.

## Безопасность

- Секреты, токены и подписи сравнивать constant-time (`hmac.compare_digest` и
  аналоги).
- Пользовательский текст выводить через безопасные React bindings; не применять
  `dangerouslySetInnerHTML` без санитизации.
- Использовать параметризованные SQL-запросы и безопасные API запуска процессов.
- Загружаемые файлы проверять на сервере по типу, размеру и содержимому; одной
  клиентской валидации недостаточно.
- Проверять токен и права до начала полезной работы HTTP/WS-обработчика.
- Для realtime-статусов использовать WebSocket и чтение состояния из Valkey,
  когда это соответствует контракту подсистемы. Если состояние ещё не попало в
  БД, протокол должен быть client-driven.

## Команды проверки

Команды ниже выполняются из корня репозитория в PowerShell.

### Billing unit-тесты

```powershell
$env:PYTHONPATH = "src"
pytest -c deploy/test/pytest.ini --rootdir=. -m unit
```

### Mediaworker unit-тесты

```powershell
Push-Location mediaworker
$env:PYTHONPATH = "src"
pytest -q
Pop-Location
```

### Полный integration-прогон

```powershell
docker compose -f deploy/dev/docker-compose.yml -f deploy/test/docker-compose.yml up --build --abort-on-container-exit --exit-code-from tests
```

После прогона тестовый стек останавливается отдельно:

```powershell
docker compose -f deploy/dev/docker-compose.yml -f deploy/test/docker-compose.yml down -v
```

### Admin UI

```powershell
Push-Location adminui
npm run typecheck
npm run lint
npm run build
Pop-Location
```

### LuaWorker

Dockerfile LuaWorker запускает встроенные Lua-тесты на стадии сборки:

```powershell
docker build -f luaworker/Dockerfile -t saviorbill-luaworker luaworker
```

### Makefile

Если доступен GNU Make, эквивалентные цели:

```text
make unit
make mw-unit
make test
```

## Когда какую проверку запускать

- Изменения только в billing unit-логике: billing unit-тесты.
- Изменения в `mediaworker/`: mediaworker unit-тесты.
- Изменения в `luaworker/`: сборка LuaWorker.
- Изменения API, БД, Valkey, worker-контрактов или межсервисных сообщений:
  полный integration-прогон.
- Изменения в `adminui/`: typecheck, lint и build.
- Для существенных UI, WS и runtime-изменений выполнить живую проверку на
  dev-стеке. Если в среде доступен Playwright MCP, использовать его инструменты
  для этой проверки; не устанавливать Playwright только ради этой инструкции.
- Полную пересборку без кэша выполнять для крупных изменений или перед релизом:

```powershell
docker compose -f deploy/dev/docker-compose.yml build --no-cache
```

Не требуется запускать весь набор проверок после каждой мелкой правки, если
затронутая подсистема и риск изменения очевидны.

## Frontend conventions

- Тема приложения тёмная. Основные акценты: `#009080`, `#0C5E53`,
  `#0D504B` с прозрачностью только для небольших фоновых паттернов.
- Для скрытия блока без сохранения пустого места использовать
  `max-h-0 overflow-hidden` с переходом к нужному `max-h-*`, а не только
  `opacity-0`.
- Кастомные модалки и lightbox, которым не подходит стандартный Dialog, рендерить
  через `createPortal` в `document.body`.
- Логотипы студии и проекта оставлять квадратными; круглую обрезку использовать
  только для пользовательских аватаров.

## Git

- Коммиты группировать по логическим изменениям.
- Сообщения оформлять в стиле Conventional Commits:
  `feat(scope): ...`, `fix(scope): ...`, `refactor(scope): ...`.
- Не коммитить секреты, runtime-данные, логи, временные файлы и локальные
  заметки.
- Перед коммитом проверить `git status --short` и `git diff --stat`.
