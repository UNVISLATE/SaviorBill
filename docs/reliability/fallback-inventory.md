# Fallback inventory and baseline

Дата baseline: 2026-10-02  
Baseline commit: `ece421e94eb2d28464a50783604e3b21e3ea5030`

Этот документ фиксирует наблюдаемое поведение до изменения строгой семантики
fallback. Он не является разрешением оставить каждый найденный fallback:
статус `needs-review` означает, что call-site должен получить отдельное
решение и negative test.

## Baseline checks

| Проверка | Результат |
|---|---|
| Billing unit | `397 passed, 1 failed, 30 deselected` |
| Billing failure | `tests/unit/test_lua_versioning.py::test_patch_creates_new_version_and_bumps_lock_version`: на Windows получен `services\demo/v2.lua` вместо ожидаемого POSIX-пути `services/demo/v2.lua` |
| Mediaworker unit | `95 passed` |
| LuaWorker Docker build/tests | passed |
| Full integration stack | `428 passed, 6 warnings` |
| Admin UI typecheck | errors in current `RolesPage.tsx` |
| Admin UI lint | 29 errors and 1 warning, включая текущие Animate UI и pre-existing shadsnui/hooks issues |
| Admin UI build | errors в `RolesPage.tsx` |

Admin UI и related Animate UI изменения были в рабочем дереве до этой задачи и
не относятся к инвентаризации fallback.

## Правило классификации

| Статус | Значение |
|---|---|
| `allowed` | Presentation или технический default без изменения бизнес-смысла |
| `allowed-default` | Явно документированный default при создании/инициализации |
| `critical-error` | Должен завершать критичную операцию явной ошибкой |
| `degraded` | Допустим только для некритичного пути с metric/log и видимым статусом |
| `needs-review` | Контракт нужно подтвердить тестом или решением владельца |

## Критичные fallback-пути

| Место | Текущее поведение | Риск | Целевой статус |
|---|---|---|---|
| `src/models/system_scripts.py::resolve_version` | Отсутствующая pinned-версия возвращает `script.filename` и `current_version` | Платёж, выдача или OAuth могут выполнить другой код | `critical-error` |
| `src/models/system_scripts.py::resolve_version` | `version=None` выбирает текущую версию | Допустимо только если `null = latest` явно выбрано конфигурацией | `needs-review` / documented |
| `src/models/service.py` и связанные модели | Ссылка на Lua script/version хранится отдельно от файла | Ручное удаление файла приводит к runtime failure или пустому редактору | `critical-error` + artifact status |
| `src/lua/context.py::LuaRunner` | `filename or script.filename` выбирает имя файла | Пустое явно переданное значение может незаметно заменить путь | `needs-review` |
| `src/dependencies/payment.py` | `_script()` получает путь через version resolver | Fallback версии влияет на create/callback/check/refund | `critical-error` |
| `src/dependencies/oauth.py` | OAuth получает filename через `resolve_version_filename` | Может быть вызвана не та версия provider script | `critical-error` |
| `src/lua/integrations/delivery.py` | Delivery сохраняет фактически resolved version | Состояние услуги может быть связано с неожиданным кодом | `critical-error` |
| `src/lua/integrations/trigger_action.py` | Trigger получает filename через version resolver | Внешнее действие запускается другой версией | `critical-error` |
| `src/services/fx.py` | FX использует `resolve_version_filename(..., None)` | `None` намеренно означает latest, нужно документировать | `needs-review` |
| `src/security/sec/secrets/resolve.py` и stores | При `None` от backend возможен ENV/generation fallback | В production может использоваться старый или случайно сгенерированный секрет | `critical-error` для обязательных production secrets |
| `src/dependencies/ratelimit.py` | Ошибка Valkey пропускается после `note_degraded()` | Критичные auth/payment endpoints могут потерять ограничение | selective `degraded` / `critical-error` |
| `src/services/auth.py` | Reuse проверяется через Valkey denylist | Потеря/недоступность Valkey меняет гарантию проверки | `needs-review`; отдельный atomic rotation |

## Media and physical artifact fallback

| Место | Текущее поведение | Риск | Целевой статус |
|---|---|---|---|
| `src/models/system_media.py` | БД хранит `path`/`variants`, физическое наличие проверяется отдельно | `ready` может ссылаться на удалённый объект | explicit `missing`/`corrupt` |
| `src/schemas/media.py::Media.from_model` | `variants.get(...)` и `m.variants or {}` возвращают пустые variant data | UI может показать неполную/пустую карточку без причины | presentation fallback только при явном artifact status |
| `src/api/v1/media.py::media_status` | Cache status, затем DB/job fallback | Разные источники могут показывать разные состояния | authoritative status contract |
| `src/utils/storage.py::_delete_fs` | Небезопасный путь тихо игнорируется как best-effort delete | Ошибка удаления невидима, orphan может остаться | audit/metric; не маскировать security error |
| `mediaworker/src/api/serve.py` | Резолвит вариант через cache/storage | Потерянный main/thumb/preview должен быть виден клиенту | per-variant missing status |
| `src/models/system_media.py::orphans` | DB orphan определяется по ссылкам и возрасту | Нельзя путать orphan с повреждённым используемым файлом | reconciliation before cleanup |

## Lua runtime and script configuration

| Место | Текущее поведение | Риск | Целевой статус |
|---|---|---|---|
| `luaworker/src/handlers.lua` | `env(key, default)` применяет ENV defaults | Runtime limits/config can silently differ from deployment intent | `needs-review` per variable |
| `luaworker/src/sbox.lua` | Numeric parsing uses defaults such as `tonumber(n) or 0` | Invalid limit/input can become valid-looking value | `critical-error` for security limits |
| `luaworker/src/main.lua` | Payload fields use `map.field or ""` and decoded payload `{}` | Missing queue fields may become malformed but processed task | `critical-error` for required fields |
| `luaworker/src/handlers.lua` | Result uses `res.public or {}` and `res.private or {}` | Missing result sections are treated as success-shaped empty data | `needs-review`; validate contract |
| `docs/lua/scripts.md` / `docs/lua/llms.txt` | `ctx.lua.settings` and `ctx.service.settings` documented separately | Developers may implement wrong precedence or hide required fields with `or` | explicit recommendation, no runtime substitution |

## Defaults that are likely allowed

These are not automatically bugs, but each must remain explicit and outside
critical business resolution:

- `None`/empty optional UI description or label;
- documented initial settings for a newly created object;
- `ctx.service.settings` taking precedence over shared `ctx.lua.settings` for
  service-specific configuration, when the key is optional and the script
  documents inheritance;
- empty `previews` list when the main media artifact is known to be valid and
  there are genuinely no previews;
- presentation placeholder after the API explicitly reports `missing` or
  `storage_unavailable`.

## Required follow-up per inventory item

For every `critical-error` or `needs-review` row:

1. identify the exact caller and business operation;
2. define the error type/status and safe diagnostic detail;
3. add a positive test preserving valid behavior;
4. add a negative test for missing/invalid input;
5. assert no payment, service, token, external request, or success event was
   created on the negative path;
6. document the final status in `IMPLEMENTATION_PLAN.md` and update this
   inventory after implementation.

