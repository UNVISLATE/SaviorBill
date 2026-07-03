# Медиа-подсистема

Медиа (изображения/видео/иконки/аватары) — самостоятельный домен, полностью
разъединённый с ядром биллинга: `billing` и `mediaworker` не знают о существовании
друг друга и общаются только через общие Postgres и Valkey. `mediaworker` сам
валидирует access-JWT, читает роль/квоту из БД, конвертирует файлы и пишет готовое
медиа в БД; `billing` только **читает** результат. Единый reverse-proxy — Caddy
(авто TLS, HTTP/2 и HTTP/3).

## Компоненты

- **Caddy** (`deploy/Caddyfile`, `{$DOMAIN:localhost}`) — единая точка входа:
  - `/media/*` — локально готовые файлы (`{token}.webp` / `{token}.webm`, а также
    варианты `{token}.thumb.webp`, `{token}.preview.webp`) отдаёт САМ Caddy из
    `data/media` (`file_server` + `try_files`); промах (S3 / не готово) и загрузка
    (`POST /media/upload`) уходят в `mediaworker`;
  - `/internal/*` — закрыт наружу (`404`);
  - всё прочее — `billing:8000`.
- **billing** — читает метаданные медиа из БД (статус-эндпоинт, admin-список,
  товарные вложения, аватары), admin-удаление/чистка. **Владелец схемы БД**:
  единственный сервис, который пишет `system_media` — потребляет результаты
  конвертации из стрима `media:results` и сам записывает запись. Файлы не трогает,
  загрузку не авторизует.
- **mediaworker** (Python + ffmpeg, `mediaworker/`) — самодостаточный сервис:
  валидация access-JWT (общий секрет), чтение роли/квоты из Postgres (**только
  SELECT**), приём upload (стриминг + бан IP + лимит частоты), конвертация
  (`webp`/`webm` + варианты), публикация результата в `media:results`, отдача из S3
  (presigned) и fallback, удаление файлов по задаче. В БД **не пишет**.

## Поток загрузки

1. `POST /media/upload?kind=image` (`Authorization: Bearer <access-JWT>`), тело —
   файл (стрим). Забаненный IP → `403` сразу.
2. `mediaworker` валидирует access-JWT (общий `JWT_SECRET` / файл `data/keys/jwt.key`)
   и читает права роли аккаунта из Postgres:
   - `media.uploadlarge` → `MEDIA_MAX_BYTES` (по умолчанию 50 MiB);
   - `media.upload` → `MEDIA_SMALL_MAX_BYTES` (по умолчанию 1 MiB);
   - иначе `403`; забаненная роль → `403`.
3. Лимит частоты: для обычных пользователей (без `media.uploadlarge`) —
   `MEDIA_UPLOADS_PER_HOUR` загрузок в час (ключ `media:uprate:{acc}:{hour}`);
   превышение → `429`.
4. Пре-проверка `Content-Length`: честно заявленный размер `> max_bytes` → `413`
   **без бана**.
5. Потоковый приём кусками с бегущим счётчиком. Если фактический объём превысил
   лимит (заголовок длины был фейковым) → `413` + **бан IP** на `MEDIA_BAN_SECONDS`
   (ключ `media:ban:{ip}`). Полное чтение в память запрещено.
6. `token = uuid`; оригинал → `data/uploads/{token}.orig`;
   `media:status:{token} = processing`; `XADD media:tasks {op:convert, ...}`.
7. Ответ клиенту: `{token, status: "processing"}`.

## Конвертация (consumer `media:tasks`)

Из одного оригинала ffmpeg генерирует несколько вариантов:

- **изображение** → `main` (`{token}.webp`, полное качество) + `thumb`
  (`{token}.thumb.webp`, обрезанный квадрат `MEDIA_THUMB_SIZE` минимального
  качества `MEDIA_THUMB_QUALITY`);
- **видео** → `main` (`{token}.webm`) + `preview` (`{token}.preview.webp`, полный
  кадр-постер) + `preview_thumb` (`{token}.preview_thumb.webp`, обрезанный мини-постер).

Далее:

1. Каждый вариант → `data/media/{key}` (fs) или S3 (+ кэш `media:file:{token}`
   поле-на-вариант для отдачи).
2. `mediaworker` публикует результат в стрим `media:results` (`op:convert`, поля
   `token`/`kind`/`path`/`mime`/`size`/`backend` основного файла + JSON `variants`).
   Запись в БД делает **billing**: консьюмер `MediaResults` (`services/media_results.py`)
   читает стрим через consumer-группу `billingmedia` и идемпотентно пишет
   `system_media` (`SystemMediaMngr.upsert` по `token`). Так логика записи в БД
   живёт только в одном сервисе.
3. `media:status:{token} = ready` (`url`, `mime`).
4. Оригинал удаляется (`MEDIA_KEEP_ORIGINAL=false`). При ошибке ffmpeg →
   `media:status:{token} = failed`.

### Ручная загрузка превью (видео)

`POST /media/{token}/preview` (владелец медиа, `kind=video`) — стримит картинку,
ставит задачу `media:tasks {op:preview}`; воркер пересобирает `preview` и
`preview_thumb` и публикует результат `media:results {op:preview}`, а billing
домержит их в `variants` (`SystemMediaMngr.merge_variants`).

## Отдача

- Локальный бэкенд: файл отдаёт Caddy напрямую (`/media/{token}` → `{token}.webp`,
  `/media/{token}.thumb` → `{token}.thumb.webp` и т.д.).
- S3: `mediaworker` `GET /media/{token}` (и `/media/{token}.<variant>`) → `307` на
  presigned-URL.
- Статус: `GET /api/v1/media/status/{token}` (billing) → `{state, url?, mime?, error?}`.

## Удаление и чистка

- `DELETE /api/v1/admin/media/{id}` — удаляет запись и ставит задачу
  `media:tasks {op:delete}` (файл удаляет mediaworker).
- `POST /api/v1/admin/media/cleanup` — удаляет «осиротевшие» медиа (не привязанные ни
  к товарам-вложениям, ни к аватаркам пользователей).
- Право `media.admin` (список — `media.read`).

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
