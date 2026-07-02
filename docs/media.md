# Медиа-подсистема

Медиа (изображения/видео/иконки/аватары) полностью изолированы от ядра биллинга.
Ядро (`billing`) хранит только метаданные и решает вопросы прав/квот/ссылок; вся
работа с файлами (приём загрузки, стриминг, конвертация, отдача, удаление) вынесена
в отдельный сервис `mediaworker`. Очередь и статусы — Valkey. Единый reverse-proxy —
Caddy (авто TLS, HTTP/2 и HTTP/3).

## Компоненты

- **Caddy** (`deploy/Caddyfile`, `{$DOMAIN:localhost}`) — единая точка входа:
  - `/media/*` — локально готовые файлы (`{token}.webp` / `{token}.webm`) отдаёт САМ
    Caddy из `data/media` (`file_server` + `try_files`); промах (S3 / не готово) и
    загрузка (`POST /media/upload`) уходят в `mediaworker`;
  - `/internal/*` — закрыт наружу (внутренний API billing);
  - всё прочее — `billing:8000`.
- **billing** — авторизация загрузки (права+квоты), регистрация готового медиа в БД
  по колбэку, статус-эндпоинт, admin-удаление/чистка, товарные вложения. Файлы не
  трогает.
- **mediaworker** (Python + ffmpeg, `mediaworker/`) — приём upload (стриминг + бан
  IP), конвертация (`webp`/`webm`), отдача из S3 (presigned) и fallback, удаление
  файлов по задаче. Postgres не использует — только Valkey, ФС/S3 и внутренний API
  billing.

## Поток загрузки

1. `POST /media/upload?kind=image` (`Authorization: Bearer <access-JWT>`), тело —
   файл (стрим). Забаненный IP → `403` сразу.
2. `mediaworker` → billing `POST /internal/media/authorize` (service-token + JWT
   пользователя) → `{owner_id, max_bytes}` либо `401/403`.
   - `media.uploadlarge` → `MEDIA_MAX_BYTES` (по умолчанию 50 MiB);
   - `media.upload` → `MEDIA_SMALL_MAX_BYTES` (по умолчанию 1 MiB).
3. Пре-проверка `Content-Length`: честно заявленный размер `> max_bytes` → `413`
   **без бана**.
4. Потоковый приём кусками (~1 MiB) с бегущим счётчиком. Если фактический объём
   превысил лимит (значит заголовок длины был фейковым) → `413` + **бан IP** на
   `MEDIA_BAN_SECONDS` (ключ `media:ban:{ip}`). Полное чтение в память запрещено.
5. `token = uuid`; оригинал → `data/uploads/{token}.orig` (fs) или S3;
   `media:status:{token} = processing`; `XADD media:tasks {op:convert, ...}`.
6. Ответ клиенту: `{token, status: "processing"}`.

## Конвертация (consumer `media:tasks`)

1. ffmpeg: изображение → `webp`, видео → `webm` (пресеты `MEDIA_WEBP_QUALITY`,
   `MEDIA_WEBM_CRF`). fs → `data/media/{token}.webp|webm`; S3 → upload + кэш
   `media:file:{token}` для отдачи.
2. `media:status:{token} = ready` (`url`, `mime`).
3. `mediaworker` → billing `POST /internal/media/register` (service-token) → billing
   создаёт запись `system_media` (идемпотентно по `token`).
4. Оригинал удаляется (`MEDIA_KEEP_ORIGINAL=false`). При ошибке ffmpeg →
   `media:status:{token} = failed`.

## Отдача

- Локальный бэкенд: файл отдаёт Caddy напрямую (`/media/{token}` → `{token}.webp`).
- S3: `mediaworker` `GET /media/{token}` → `307` на presigned-URL.
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

## Конфигурация

billing (`src/utils/config.py`): `DOMAIN`, `MEDIAWORKER_URL`, `MEDIA_TASK_STREAM`,
`MEDIA_STATUS_TTL`, `MEDIA_BAN_SECONDS`, `MEDIA_SMALL_MAX_BYTES`, `MEDIA_MAX_BYTES`,
`STORAGE_BACKEND` (`fs`|`s3`) + `S3_*`, service-token = `LUA_SERVICE_TOKEN`.

mediaworker (`mediaworker/src/config.py`): `VALKEY_*`, `DATA_DIR`, `BILLING_URL`,
`LUA_SERVICE_TOKEN`, `MEDIA_GROUP/CONSUMER`, `MEDIA_KEEP_ORIGINAL`,
`MEDIA_WEBP_QUALITY`, `MEDIA_WEBM_CRF`, `STORAGE_BACKEND` + `S3_*`.

> `service_catalogs.icon` пока остаётся строковым URL (вне scope рефакторинга).
