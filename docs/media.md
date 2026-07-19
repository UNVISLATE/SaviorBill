# Медиа-подсистема

Медиа (изображения/видео/иконки/аватары) — самостоятельный воркер. 
`mediaworker` сам валидирует access-JWT, читает роль/квоту из БД, 
конвертирует файлы и пишет готовое медиа в БД; 
`billing` только **читает** результат.

## Компоненты

- **mediaworker** (Python + ffmpeg, `mediaworker/`) — самодостаточный сервис:
  валидация access-JWT (общий секрет), чтение роли/квоты из Postgres (**только
  SELECT**), двухшаговый приём upload (стриминг + бан IP + лимит частоты),
  конвертация (`webp`/`webm` + варианты), публикация результата в `media:results`,
  **самостоятельная отдача** файлов (fs напрямую, s3 presigned), удаление файлов по
  задаче. В БД **не пишет**.

## Поток загрузки (два шага)

Загрузка разбита на два запроса: сначала проверка прав и выдача одноразового
upload-token, затем — сама передача файла. Это отделяет авторизацию от приёма тела
и позволяет фронтенду получить лимиты заранее.

**Шаг 1 — `POST /api/media/upload?kind=image`** (`Authorization: Bearer <access-JWT>`,
тело не нужно). Забаненный IP → `403` сразу.

1. `mediaworker` валидирует access-JWT (общий `JWT_SECRET` / файл
   `data/keys/jwt.key`) и читает права роли аккаунта из Postgres:
   - забаненная роль (`role_key == "banned"`) → `403` **сразу**, ещё до проверки
     прав — это явное сравнение по ключу роли (`utils/authctx.py::authorize`),
     а не через `has_perm`. Бан в проекте не отдельный флаг, а назначение
     общей системной роли `banned` (см. `models/user.py::is_active` в billing
     — тот же принцип); если бы проверка шла через права, правка перм этой
     shared-роли по любой причине разбанила бы разом всех, кто на неё
     назначен — поэтому `media.upload`/`media.uploadlarge` в правах роли
     `banned` **не имеют эффекта**, бан всё равно побеждает первым;
   - `media.uploadlarge` → `MEDIA_MAX_BYTES` (по умолчанию 50 MiB);
   - `media.upload` → `MEDIA_SMALL_MAX_BYTES` (по умолчанию 1 MiB);
   - ни одного из двух прав → `403`.
2. Лимит частоты: для обычных пользователей (без `media.uploadlarge`) —
   `MEDIA_UPLOADS_PER_HOUR` загрузок в час (ключ `media:uprate:{acc}:{hour}`);
   превышение → `429`.
3. Выдаётся одноразовый token: `HSET media:uptoken:{token} owner/kind/max_bytes`,
   `EXPIRE MEDIA_UPLOAD_TOKEN_TTL` (по умолчанию 60 c). Ответ `201`:
   `{upload_token, expires_in, upload_url: "/api/media/upload/{token}"}`.

**Шаг 2 — `POST /api/media/upload/{upload_token}`**, тело — файл (стрим). Забаненный IP
→ `403`.

4. Token извлекается **атомарно** (Lua `HGETALL` + `DEL`); отсутствует/истёк →
   `404`. Из него берутся `owner`, `kind`, `max_bytes`.
5. Пре-проверка `Content-Length`: честно заявленный размер `> max_bytes` → `413`
   **без бана**.
6. Потоковый приём кусками с бегущим счётчиком. Если фактический объём превысил
   лимит (заголовок длины был фейковым) → `413` + **бан IP** на `MEDIA_BAN_SECONDS`
   (ключ `media:ban:{ip}`). Полное чтение в память запрещено.
7. `media_token = uuid`; оригинал → `data/uploads/{media_token}.orig`;
   `media:status:{media_token} = queued`; `XADD media:tasks {op:convert, ...}`.
8. Ответ клиенту: `{token, status: "queued"}`.

Статусы конвертации: `queued` (принято, ждёт воркера) → `processing` (воркер начал)
→ `ready` (готово) либо `failed`.

## Конвертация (consumer `media:tasks`)

Из одного оригинала ffmpeg генерирует несколько вариантов:

- **изображение** → `main` (`{token}.webp`, полное качество) + `thumb`
  (`{token}.thumb.webp`, обрезанный квадрат `MEDIA_THUMB_SIZE` минимального
  качества `MEDIA_THUMB_QUALITY`);
- **видео** → `main` (`{token}.webm`) + `preview` (`{token}.preview.webp`, полный
  кадр-постер) + `preview_thumb` (`{token}.preview_thumb.webp`, обрезанный мини-постер).

Далее:

1. Каждый вариант → `data/media/{key}` (fs) или S3. В обоих случаях пишется кэш
   `media:file:{token}` (поле-на-вариант), по которому `serve()` находит ключ файла.
2. `mediaworker` публикует результат в стрим `media:results` (`op:convert`, поля
   `token`/`kind`/`path`/`mime`/`size`/`backend` основного файла + JSON `variants`).
   Запись в БД делает **billing**: консьюмер `MediaResults` (`services/media_results.py`)
   читает стрим через consumer-группу `billingmedia` и идемпотентно пишет
   `system_media` (`SystemMediaMngr.upsert` по `token`). Так логика записи в БД
   живёт только в одном сервисе.
3. `media:status:{token} = ready` (`url`, `mime`).
4. Оригинал удаляется (`MEDIA_KEEP_ORIGINAL=false`). При ошибке ffmpeg →
   `media:status:{token} = failed`.

### Надёжность: ретраи и DLQ

- Воркер: провал обработки медиа-задачи учитывается по попыткам
  (`attempts:media:convert:{token}`). До `MEDIA_TASK_MAX_ATTEMPTS` задача
  возвращается в `media:tasks`; при исчерпании — уходит в `MEDIA_TASK_DLQ`
  (`media:tasks:dead`) и `media:status = failed`.
- billing-консьюмер результатов: провал записи учитывается по
  `attempts:media:result:{token}:{op}`; при исчерпании `MEDIA_RESULT_MAX_ATTEMPTS`
  результат уходит в `MEDIA_RESULT_DLQ` (`media:results:dead`).
- Backpressure: воркер читает из стрима не больше, чем есть свободных слотов
  семафора `MEDIA_TASK_CONCURRENCY`, и обрабатывает задачи конкурентно.
- Лок в обработке (`media:joblock:{op}:{token}`, TTL `MEDIA_JOB_LOCK_TTL_SEC`):
  долгая конвертация видео может не успеть `ack` за `MEDIA_RECLAIM_MIN_IDLE_MS`
  (обработка ещё жива, просто не закончилась) — без этого лока reclaim
  подхватил бы ту же PEL-запись и запустил дублирующую конвертацию того же
  токена конкурентно с ещё живым оригиналом; какой из двух результатов
  "победит" в статусе — гонка (наблюдалось как `ready` по
  `/api/v1/media/status/{token}`, но `404 conversion failed` при прямом
  запросе файла у mediaworker — дубликат проигрывал гонку и перезатирал
  `media:status` на `failed` после того, как оригинал уже опубликовал
  результат). Лок ставится в `_process_one` перед диспетчеризацией
  (`SET NX EX`) и снимается после завершения; если не удалось взять — задача
  просто ack'ается без повторной обработки, оригинальный держатель лока сам
  доводит её до конца.

### Единая state machine (`worker_jobs`)

Все статусы фоновых медиа-задач (конвертация/превью/удаление) фиксируются в
одной таблице `worker_jobs` (+ `worker_job_events` для истории переходов) —
и одиночный статус (`/media/status/{token}`), и списки в админке читают из
одного и того же источника, поэтому не бывает рассинхрона «в списке `failed`,
по прямому запросу `processing`». Consumer `MediaJobEvents`
(`services/media_job_events.py`) пишет переходы состояний по событиям из
`media:results`/`media:tasks`. `models/worker_jobs.py::WorkerJobsMngr` — точка
доступа для всех читателей (`latest()`, `count_pending()`, списки).
Bus-подписи (`BUS_SIGNING_KEY`) отражаются в метрике
`bus_signature_rejected_total`, а reclaim/failed переходы — в
`worker_jobs_reclaimed_total`/`worker_jobs_failed_total` (см. `docs/telemetry.md`).

### Realtime-лог и прогресс конвертации ffmpeg (`proclog`)

Каждый запуск ffmpeg/ffprobe (`convert`) регистрируется как отдельный
`job_id` в Valkey (`mediaworker/src/utils/proclog.py`) — не завязан на
`token`, у одного `token` может быть несколько параллельных job'ов (например,
конвертация + отдельная генерация превью).

**Всё это отдаёт сам `mediaworker` — не `billing`.** Раньше логи/прогресс
проксировались через billing (`apiws/v1/logs/media.py` + `api/v1/admin/logs/media.py`
+ `telemetry/proclog_read.py`), хотя billing ничего не добавлял: та же
проверка JWT + прав роли из той же Postgres, тот же Valkey-контракт — просто
лишний сетевой прыжок и два места, которые нужно было держать в синхроне при
изменении формата. `mediaworker` и так уже умеет проверять JWT/права (см.
`api/upload.py`), поэтому владеет своими realtime-роутами напрямую
(`mediaworker/src/api/logs.py`, `mediaworker/src/utils/authws.py`).
`billing` по-прежнему отдаёт только список загруженных/загружаемых файлов и
их терминальный статус (`/api/v1/media/status/{token}`, `/api/v1/admin/media`)
— это единственное, что ему нужно как единому источнику истины по готовым
медиа (`system_media`/`worker_jobs`).

Роуты `mediaworker` (все требуют право `logs.read`, авторизация — тот же
access-JWT, что и для upload/status):

- `GET /api/media/logs/jobs` — список последних job'ов.
- `GET /api/media/logs/jobs/{job_id}` — метаданные одного job'а.
- `GET /api/media/logs/jobs/{job_id}/progress` — одноразовый снимок percent/eta.
- `WS /api/media/logs/jobs/{job_id}/tail` — live сырой вывод (для xterm.js):
  бэклог + live-форвардинг терминального текста как есть (включая
  прогресс-строки ffmpeg с `\r` без `\n`).
- `WS /api/media/logs/jobs/{job_id}/progress/tail` — live percent/eta: снимок
  при подключении + JSON-события `{percent, eta_sec, fps, speed, frame,
  out_time_sec, done}`.

WS не может так же просто передать `Authorization` header из браузера, как
HTTP — авторизация происходит первым текстовым сообщением
`{"token": "<access-JWT>"}` сразу после подключения (`utils/authws.py`,
идентичная схема billing).

Прогресс публикуется **только** для основного видео-кодирования (webm) —
этап, который может идти минутами; thumb/preview — вырезка одного кадра,
процент для них не осмыслен, и они его не публикуют. Разобран из
machine-readable вывода ffmpeg (`-progress pipe:1 -nostats`,
`mediaworker/src/utils/ffprogress.py`), а не regex-парсинга человеческого
stderr — формат `key=value`, официально предназначен для программного
мониторинга и не меняется между версиями ffmpeg так, как читаемый вывод.
`percent`/`eta_sec` вычисляются из `out_time_us` и заранее известной
длительности (`probe_duration()`); при отсутствии длительности (не
распозналась) поля остаются `null`, но сырые `fps`/`frame`/`speed`
публикуются всё равно. Раздельные Valkey-ключи/каналы от сырого лога
(`proclog:progress:{job_id}` + `proclog:progress-events:{job_id}`, TTL как у
`proclog:*`) — иначе JSON попадал бы в тот же канал, что и терминальный
текст, и ломал xterm.js.

`GET /api/media/status/{token}` (собственный статус mediaworker, не
billing) дополнительно отдаёт `jobs: [{job_id, op, status, percent, eta_sec}]`
— сводку недавних/активных job'ов этого токена (`proclog.py::jobs_for_token`,
индекс `proclog:token_jobs:{token}`). Это ephemeral debug-данные самого
mediaworker, а не часть его "готово/не готово" контракта — `billing` их не
дублирует и не обязан.

### Полный путь данных при загрузке фото/видео (кто что пишет и зачем)

Чтобы не путаться, за что отвечает какой сервис и какое хранилище —
пошагово, что происходит с одним файлом от загрузки до отдачи:

1. **Клиент → mediaworker, шаг 1** (`POST /api/media/upload`): mediaworker
   сам проверяет JWT и права роли (SELECT в Postgres, той же самой БД, что и
   billing) — выдаёт одноразовый upload-token в Valkey.
2. **Клиент → mediaworker, шаг 2** (`POST /api/media/upload/{upload_token}`):
   потоковый приём файла, `media_token = uuid`, оригинал → `data/uploads/`,
   `media:status:{media_token} = queued` в Valkey, задача → стрим `media:tasks`.
   Ответ клиенту сразу: `{token, status: "queued"}`.
3. **mediaworker (consumer `media:tasks`)** забирает задачу, ставит
   per-`(op,token)` лок (`media:joblock:*`, см. "Надёжность" выше), запускает
   ffmpeg:
   - сырой вывод и (для видео) прогресс идут в `proclog:*` (Valkey,
     ephemeral, TTL — не БД) — это то, что отдают роуты из раздела выше;
   - `media:status:{media_token}` обновляется на `processing`, затем на
     `ready`/`failed` (тоже Valkey, ephemeral — источник для быстрого опроса
     без похода в БД, но **не** источник истины при долгом хранении).
4. **mediaworker → billing** (стрим `media:results`, подписан `BUS_SIGNING_KEY`):
   mediaworker публикует факт результата (`op:convert`, `token`, `kind`,
   `path`/`variants`, `mime`, `size`, `backend`) — **не пишет в БД сам**.
5. **billing (consumer `MediaResults`)** читает `media:results` и
   идемпотентно пишет `system_media` (durable, Postgres) — это и есть
   единственный источник истины "медиа существует и в каком оно состоянии"
   для всего, что переживает рестарт/TTL Valkey.
6. **billing (consumer `MediaJobEvents`)** параллельно читает те же события
   (`media:results`/`media:tasks`) и пишет `worker_jobs`/`worker_job_events`
   (durable state machine статусов, см. ниже) — используется и одиночным
   статусом, и списками в админке, чтобы они не расходились.
7. **Клиент опрашивает статус** — два варианта, оба легитимны, но с разной
   ролью:
   - `GET /api/v1/media/status/{token}` (billing) — единственный "правильный"
     публичный статус для конечного клиента/фронтенда: `queued`/`processing`/
     `ready`/`failed`, `url`, `mime` — источник истины (Valkey с фоллбэком на
     `system_media`/`worker_jobs`, если TTL Valkey истёк).
   - `GET /api/media/status/{token}` (mediaworker) — то же самое +
     `jobs: [...]` (см. выше) — для отладки/админки, когда нужно увидеть, что
     именно происходит с конвертацией *прямо сейчас* (ephemeral, без
     фоллбэка на БД, см. `api/status.py`).
8. **Отдача файла** — `GET /api/media/{token}` (mediaworker) — читает
   `media:file:{token}` (кэш ключа файла) и отдаёт сам (fs напрямую или
   presigned-редирект на S3); billing файлы не хранит и не отдаёт.

Итого: **Valkey (`media:status:*`, `proclog:*`) — ephemeral, для realtime**;
**Postgres (`system_media`, `worker_jobs`) — durable, источник истины**;
mediaworker управляет и тем, и другим (только Valkey — сам, в Postgres —
только SELECT), billing пишет в Postgres по событиям от mediaworker и не
трогает Valkey-контракт логов/прогресса напрямую.

### Ручная загрузка превью (видео)

`POST /api/media/{token}/preview` (владелец медиа, `kind=video`) — стримит картинку,
ставит задачу `media:tasks {op:preview}`; воркер пересобирает `preview` и
`preview_thumb` и публикует результат `media:results {op:preview}`, а billing
домержит их в `variants` (`SystemMediaMngr.merge_variants`).

## Отдача

- Локальный бэкенд: файл отдаёт **сам mediaworker** (`GET /api/media/{token}` →
  `FileResponse`), находя ключ через кэш `media:file:{token}` либо по соглашению об
  именах (`{token}.webp` / `{token}.webm`, `/api/media/{token}.thumb` →
  `{token}.thumb.webp` и т.д.). Caddy лишь проксирует `/api/media/*` в mediaworker.
- S3: `mediaworker` `GET /api/media/{token}` (и `/api/media/{token}.<variant>`) → `307` на
  presigned-URL.
- Статус при отдаче: `425 Too Early` пока `media:status` = `queued`/`processing`;
  `404` — конвертация провалилась либо файла/варианта нет.
- Статус: `GET /api/v1/media/status/{token}` (billing) → `{state, url?, mime?, error?}`.
  Consистентный источник для одиночного статуса и списков — `worker_jobs`
  (БД, см. §"Единая state machine" ниже); Valkey-кэш (`media:status:{token}`)
  используется только как быстрый путь сразу после аплоада, до появления
  первой записи в `worker_jobs`.
- Статус саб-операции (превью/thumb-replace, начатых уже после основной
  конвертации): `GET /api/v1/media/{token}/ops/{op}/status` → `{state, attempt,
  error, created_at, started_at, finished_at}` — тот же `worker_jobs`.

### Модель доступа (важно при добавлении новых видов медиа)

`GET /api/media/{token}` отдаёт файл **любому**, кто знает `token` (128-бит
`uuid4`), без проверки логина/владельца. Это осознанное решение, а не
недосмотр:

- Токен практически неугадываем перебором — стандартная и вполне безопасная
  модель для **публичного** контента (картинки товаров, аватары, превью).
- Риск проявляется только для **потенциально приватного** контента: если у
  файла нет разумной модели "публичный по умолчанию" (например, документы
  верификации/KYC, приватные вложения), секретность одного URL — недостаточная
  защита, потому что URL: (а) кэшируется публично на CDN на 1 год
  (`Cache-Control`), (б) может утечь через реферер, логи прокси, историю
  браузера, случайную пересылку ссылки — и тогда файл виден вечно без
  возможности отозвать доступ post-factum.
- **Правило на будущее**: для новых видов медиа (`kind`), не предназначенных
  для публичного показа, `serve()`/раздача обязаны требовать
  `Depends(get_current_acc)` и проверку владельца (или отдельного права), а не
  полагаться на секретность токена. Существующие публичные виды
  (`image`/`icon`/`avatar`/`video`) остаются как есть.

## Проверка сигнатуры файла (magic bytes)

Перед запуском ffmpeg (`utils/convert.py::convert()`) первые байты оригинала
сверяются с таблицей известных magic bytes для вида медиа (`image`/`icon`/
`avatar` → JPEG/PNG/GIF/BMP/WEBP; `video` → MP4/MOV (`ftyp`), WebM/MKV (EBML),
OGG, а также общий RIFF-контейнер WEBP/AVI). При несовпадении —
`SignatureError` (подкласс `ConvertError`) без запуска ffmpeg: задача
помечается `failed` с описанием ошибки в `media:status`. Это не защита от
подделки как таковая (эвристика по нескольким байтам легко обходится), а
экономия ресурсов на заведомо невалидном/не том файле — основной сценарий:
клиент указал не тот `kind`, либо загрузил битый файл.

## Удаление и чистка

- `DELETE /api/v1/admin/media/{id}` — удаляет запись и ставит задачу
  `media:tasks {op:delete}` (файл удаляет mediaworker). Право `media.delete`.
- `POST /api/v1/admin/media/cleanup` — удаляет «осиротевшие» медиа (не привязанные ни
  к товарам-вложениям, ни к аватаркам пользователей). Право `media.cleanup`.
  Грейс-период: записи младше `media.cleanup_grace_sec` (настройка в БД,
  дефолт 3600 сек = 1 час) кандидатами не рассматриваются — защита от TOCTOU:
  файл, только что загруженный и ещё не успевший привязаться к сущности (или
  ещё обрабатываемый mediaworker'ом), просто не попадёт в текущий проход
  очистки, будет учтён в следующем, если действительно осиротел.
- Список — право `media.read`.

## Вложения товаров

Одиночное поле `services.image` заменено таблицей `service_attachments`
(`media_id` + `tag` ≤16 симв. + `position`). Управление:

- `GET /api/v1/admin/services/{id}/attachments`
- `POST /api/v1/admin/services/{id}/attachments` (`{media_id, tag?, position?}`)
- `DELETE /api/v1/admin/services/{id}/attachments/{att_id}`

Аватар пользователя — `accounts.avatar_media_id` (FK → `system_media`, `SET NULL`).

## OpenAPI-документация

`mediaworker` — самостоятельный FastAPI-сервис со своей интерактивной докой:

- Swagger UI — `GET /api/media/docs`, ReDoc — `GET /api/media/redoc`, схема —
  `GET /api/media/openapi.json`.
- Описание (`app.description`) содержит форматы загрузки, тела ответов и таблицу
  кодов состояния (`201/202/307/401/403/413/425/429`).
- Дока включается флагом `MEDIA_DOCS_ENABLED` (по умолчанию `true`); при `false`
  все три эндпоинта отдают `404`.

Аналогично у billing (`DOCS_ENABLED`, по умолчанию `true`): его дока
(`/api/docs`) содержит ссылку на доку mediaworker, построенную из ENV-доменов —
`MEDIA_PUBLIC_URL` → `https://{DOMAIN}` → внутренний `MEDIAWORKER_URL` (+
`/api/media/docs`).

## Конфигурация

billing (`src/core/config.py`): `DOMAIN`, `MEDIAWORKER_URL`, `MEDIA_PUBLIC_URL`,
`DOCS_ENABLED`, `MEDIA_TASK_STREAM`, `MEDIA_STATUS_TTL`, `STORAGE_BACKEND`
(`fs`|`s3`) + `S3_*`. Метаданные медиа читает из БД.

mediaworker (`mediaworker/src/config.py`): `VALKEY_*`, `DB_*` (Postgres напрямую),
`JWT_SECRET`/`JWT_SECRET_FILE`/`JWT_ALG`/`JWT_ISS`, `DATA_DIR`, `MEDIA_GROUP/CONSUMER`,
`MEDIA_MAX_BYTES`, `MEDIA_SMALL_MAX_BYTES`, `MEDIA_UPLOADS_PER_HOUR`, `ROLE_BANNED`,
`MEDIA_KEEP_ORIGINAL`, `MEDIA_WEBP_QUALITY`, `MEDIA_WEBM_CRF`, `MEDIA_THUMB_SIZE`,
`MEDIA_THUMB_QUALITY`, `MEDIA_DOCS_ENABLED`, `STORAGE_BACKEND` + `S3_*`.

> `service_catalogs.icon` пока остаётся строковым URL (вне scope рефакторинга).
