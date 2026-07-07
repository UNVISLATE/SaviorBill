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

**Шаг 1 — `POST /media/upload?kind=image`** (`Authorization: Bearer <access-JWT>`,
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
   `{upload_token, expires_in, upload_url: "/media/upload/{token}"}`.

**Шаг 2 — `POST /media/upload/{upload_token}`**, тело — файл (стрим). Забаненный IP
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

### Ручная загрузка превью (видео)

`POST /media/{token}/preview` (владелец медиа, `kind=video`) — стримит картинку,
ставит задачу `media:tasks {op:preview}`; воркер пересобирает `preview` и
`preview_thumb` и публикует результат `media:results {op:preview}`, а billing
домержит их в `variants` (`SystemMediaMngr.merge_variants`).

## Отдача

- Локальный бэкенд: файл отдаёт **сам mediaworker** (`GET /media/{token}` →
  `FileResponse`), находя ключ через кэш `media:file:{token}` либо по соглашению об
  именах (`{token}.webp` / `{token}.webm`, `/media/{token}.thumb` →
  `{token}.thumb.webp` и т.д.). Caddy лишь проксирует `/media/*` в mediaworker.
- S3: `mediaworker` `GET /media/{token}` (и `/media/{token}.<variant>`) → `307` на
  presigned-URL.
- Статус при отдаче: `425 Too Early` пока `media:status` = `queued`/`processing`;
  `404` — конвертация провалилась либо файла/варианта нет.
- Статус: `GET /api/v1/media/status/{token}` (billing) → `{state, url?, mime?, error?}`.

## Удаление и чистка

- `DELETE /api/v1/admin/media/{id}` — удаляет запись и ставит задачу
  `media:tasks {op:delete}` (файл удаляет mediaworker). Право `media.delete`.
- `POST /api/v1/admin/media/cleanup` — удаляет «осиротевшие» медиа (не привязанные ни
  к товарам-вложениям, ни к аватаркам пользователей). Право `media.cleanup`.
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

- Swagger UI — `GET /docs`, ReDoc — `GET /redoc`, схема — `GET /openapi.json`.
- Описание (`app.description`) содержит форматы загрузки, тела ответов и таблицу
  кодов состояния (`201/202/307/401/403/413/425/429`).
- Дока включается флагом `MEDIA_DOCS_ENABLED` (по умолчанию `true`); при `false`
  все три эндпоинта отдают `404`.

Аналогично у billing (`DOCS_ENABLED`, по умолчанию `true`): его описание
(`/docs`) содержит ссылку на доку mediaworker, построенную из ENV-доменов —
`MEDIA_PUBLIC_URL` → `https://{DOMAIN}` → внутренний `MEDIAWORKER_URL` (+ `/docs`).

## Конфигурация

billing (`src/utils/config.py`): `DOMAIN`, `MEDIAWORKER_URL`, `MEDIA_PUBLIC_URL`,
`DOCS_ENABLED`, `MEDIA_TASK_STREAM`, `MEDIA_STATUS_TTL`, `STORAGE_BACKEND`
(`fs`|`s3`) + `S3_*`. Метаданные медиа читает из БД.

mediaworker (`mediaworker/src/config.py`): `VALKEY_*`, `DB_*` (Postgres напрямую),
`JWT_SECRET`/`JWT_SECRET_FILE`/`JWT_ALG`/`JWT_ISS`, `DATA_DIR`, `MEDIA_GROUP/CONSUMER`,
`MEDIA_MAX_BYTES`, `MEDIA_SMALL_MAX_BYTES`, `MEDIA_UPLOADS_PER_HOUR`, `ROLE_BANNED`,
`MEDIA_KEEP_ORIGINAL`, `MEDIA_WEBP_QUALITY`, `MEDIA_WEBM_CRF`, `MEDIA_THUMB_SIZE`,
`MEDIA_THUMB_QUALITY`, `MEDIA_DOCS_ENABLED`, `STORAGE_BACKEND` + `S3_*`.

> `service_catalogs.icon` пока остаётся строковым URL (вне scope рефакторинга).
