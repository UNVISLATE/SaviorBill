# Наблюдаемость (метрики, трейсинг, health)

Метрики и трейсинг — обычные зависимости (`src/telemetry/`,
`mediaworker/src/utils/telemetry.py`), без опциональных заглушек: поведение
управляется явными флагами конфигурации, не "тихой деградацией".

## Метрики (Prometheus)

`METRICS_ENABLED` (default `true`) — `GET /metrics` через
`prometheus_fastapi_instrumentator`: latency, счётчики запросов, размеры тел
с лейблами `handler`/`method`/`status`. Готовые дашборды —
grafana.com/dashboards/14282.

Защита `/metrics`: сетевой рубеж — реверс-прокси не проксирует наружу (см.
`deploy/Caddyfile`); второй рубеж — `_install_metrics_guard()`
(`src/telemetry/otel.py`): sliding-window rate-limit по IP
(`METRICS_RATE_LIMIT_MAX`/`METRICS_RATE_LIMIT_WINDOW`, через
`security/ratelimit.py`) и, если задан `METRICS_TOKEN`, проверка заголовка
`X-Metrics-Token` (несовпадение → `404`, не `401`). mediaworker — тот же контракт, rate-limit process-local (без Valkey).

### Бизнес-метрики (`src/telemetry/metrics.py`)

Отдельный модуль-синглтон (регистрация метрики Prometheus дважды под одним
именем — ошибка, поэтому объявление в одном месте):

| Метрика | Тип | Лейблы | Смысл |
|---|---|---|---|
| `worker_jobs_pending` | Gauge | `kind` | джобы в `queued`/`processing` по `worker_jobs` |
| `worker_jobs_reclaimed_total` | Counter | `kind` | джобы, забранные как stale после `MEDIA_JOB_STALE_AFTER_SEC` |
| `worker_jobs_failed_total` | Counter | `kind`, `op` | завершившиеся ошибкой |
| `lua_script_duration_seconds` | Histogram | `slug` | полный RPC через `LuaBus`, включая ожидание ответа |
| `bus_signature_rejected_total` | Counter | `bus` | сообщения шины, отклонённые по HMAC-подписи |

### Метрики LuaWorker (push через Valkey, `src/telemetry/lua_metrics.py`)

У Lua-процесса нет своего HTTP-порта — вместо pull-модели `main.lua` раз в
`LUA_METRICS_INTERVAL_SEC` пушит снимок счётчиков (`processed_total`,
`errors_total`, `reclaimed_total`, `avg_exec_ms`, `last_seen_at`) в
Valkey-хэш `lua:metrics:{consumer}` с `EXPIRE LUA_METRICS_TTL_SEC`. Billing
фоновой задачей `LuaMetricsCollector` (запущена из `lifespan.py`) раз в
`LUA_METRICS_POLL_INTERVAL_SEC` читает эти хэши через `SCAN` (не блокирует
Valkey, в отличие от `KEYS`) и переносит их в Prometheus `Gauge` с лейблом
`consumer` — так каждая реплика воркера видна в Grafana по отдельности.
Значения — накопительные с момента старта процесса воркера, не
Prometheus-`Counter` (могут обнулиться при рестарте без сигнала billing —
обнуление на графике = обрыв, это ожидаемо). Реплика, чей ключ протух
(процесс не пушил `LUA_METRICS_TTL_SEC`), убирается из Gauge, а не висит с
последним известным значением навечно.

## Трейсинг (OpenTelemetry)

`OTEL_ENABLED` (default `false`) + `OTEL_EXPORTER_OTLP_ENDPOINT` — экспорт
спанов по OTLP (grpc/http, `OTEL_EXPORTER_OTLP_PROTOCOL`) в коллектор/Jaeger.
Автоинструментируются FastAPI (входящие HTTP) и SQLAlchemy (запросы к БД).
При включённом трейсинге ошибки отдают `trace_id` (ray id) в теле ответа и
заголовке `X-Trace-Id` — связка с трассой в Jaeger.

### Valkey — собственная инструментация

`opentelemetry-instrumentation-redis` патчит классы пакета `redis`, а
`valkey` — независимый форк с несовпадающей иерархией классов: пакет
устанавливался бы вхолостую, создавая ложное чувство покрытия трейсингом.
Вместо этого `instrument_valkey()` патчит `execute_command` — единую точку
входа всех команд клиента (обычных и Stream) — и открывает
`valkey.<command>` спан на каждый вызов.

### Сквозная трасса billing ↔ mediaworker ↔ luaworker

Прямых HTTP-вызовов между сервисами нет — общий контракт только через Valkey
Streams. Чтобы одна трасса в Jaeger покрывала все сервисы, W3C `traceparent`
прокидывается как обычное поле сообщения стрима:

- продюсер: `inject_carrier()` перед `XADD`;
- консьюмер: `span_from_carrier()` открывает спан-продолжение при чтении.

Обе функции — no-op при выключенном трейсинге (валидного контекста трассы
просто нет). `luaworker/src/main.lua` прокидывает `traceparent` как есть —
подпись сообщения (HMAC) считается по всем полям таблицы автоматически,
новое поле не требует правок протокола подписи на любой стороне.

## Health / readiness

- `GET /health` — liveness: процесс жив, без проверки зависимостей.
- `GET /health/ready` (billing и mediaworker) — проверка Postgres (`SELECT 1`
  / `DB.ping()`) и Valkey (`PING`) с таймаутом 2с; `503`, если что-то
  недоступно — для оркестратора/балансировщика, чтобы не слать трафик на
  инстанс, потерявший связь с зависимостью. billing дополнительно отдаёт
  информационное (не влияющее на `ok`) число активных реплик LuaWorker по
  `lua:metrics:*` — billing остаётся готовым обслуживать HTTP без живых
  lua-воркеров, это просто диагностика.

## Консистентность статусов между роутами

Метрики `worker_jobs_pending`/`worker_jobs_reclaimed_total`/
`worker_jobs_failed_total` и readiness-проверки читают тот же `worker_jobs`
(БД), что и API-роуты статуса (`GET /api/v1/media/status/{token}`,
`GET /api/v1/media/{token}/ops/{op}/status`, админ-списки) — единый
источник состояния устраняет класс багов «в списке один статус, по
конкретной джобе — другой» (см. `docs/media.md` §"Единая state machine").
