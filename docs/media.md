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
   - `media.uploadlarge` → `MEDIA_MAX_BYTES` (по умолчанию 50 MiB);
   - `media.upload` → `MEDIA_SMALL_MAX_BYTES` (по умолчанию 1 MiB);
   - иначе `403`; забаненная роль → `403`.
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
