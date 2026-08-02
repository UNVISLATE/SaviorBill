import { SettingsSection } from "./SettingsSection"

/**
 * «Основное» — настройки, которые реально приходится трогать, без похода в
 * Raw-редактор и знания точных ключей. Каждая секция — карточка со своей
 * кнопкой сохранения (появляется только при изменении).
 *
 * Валюта и курсы живут на отдельной вкладке (`/settings/currency`) — там
 * своя логика с источниками и проверкой, в общий список она не помещается.
 *
 * Раскладка — CSS-колонки: на широком экране карточки встают в два столбца и
 * заполняют место справа, на узком схлопываются в один.
 */
export function SettingsGeneral() {
  return (
    <div className="columns-1 gap-4 xl:columns-2 [&>*]:break-inside-avoid">
      <SettingsSection
        title="Безопасность"
        fields={[
          {
            key: "auth.2fa.required_for_admin",
            label: "Обязательная 2FA для админов",
            kind: "switch",
            hint: "Роли с доступом в панель не смогут выполнять никаких действий, пока не включат второй фактор.",
          },
          {
            key: "auth.lockout.max_attempts",
            label: "Попыток входа до блокировки",
            kind: "number",
            hint: "Считается по логину и по IP отдельно.",
          },
          {
            key: "auth.lockout.window_sec",
            label: "Длительность блокировки",
            kind: "number",
            suffix: "сек",
          },
          {
            key: "session.ttl",
            label: "Время жизни сессии",
            kind: "number",
            suffix: "сек",
            placeholder: "86400",
            hint: "Запись об активной сессии (IP/устройство). Не путать со временем жизни токена.",
          },
        ]}
      />

      <SettingsSection
        title="Заказы"
        description="Что делать, если выдача услуги упала."
        fields={[
          {
            key: "orders.delivery.max_attempts",
            label: "Попыток выдачи",
            kind: "number",
            hint: "После исчерпания заказ признаётся проваленным, а сумма возвращается на внутренний баланс.",
          },
          {
            key: "orders.delivery.retry_backoff_sec",
            label: "Пауза между попытками",
            kind: "number",
            suffix: "сек",
          },
        ]}
      />

      <SettingsSection
        title="Медиа"
        description="Ограничения на загрузку и хранение файлов пользователями."
        fields={[
          {
            key: "media.quota.image_bytes",
            label: "Квота хранения (фото)",
            kind: "number",
            suffix: "байт",
            placeholder: "52428800",
            hint: "Суммарный объём файлов аккаунта без права media.upload.video. По умолчанию 50 MiB.",
          },
          {
            key: "media.quota.video_bytes",
            label: "Квота хранения (видео)",
            kind: "number",
            suffix: "байт",
            placeholder: "2147483648",
            hint: "То же для аккаунтов с правом media.upload.video. По умолчанию 2 GiB.",
          },
          {
            key: "media.small_max_bytes",
            label: "Размер файла (фото)",
            kind: "number",
            suffix: "байт",
            hint: "Потолок для одной загрузки без права media.upload.video.",
          },
          {
            key: "media.max_bytes",
            label: "Размер файла (видео)",
            kind: "number",
            suffix: "байт",
            hint: "Потолок для одной загрузки с правом media.upload.video.",
          },
          {
            key: "media.uploads_per_hour",
            label: "Загрузок в час",
            kind: "number",
            hint: "Не применяется к аккаунтам с правом media.upload.video.",
          },
          {
            key: "user.media.limit",
            label: "Файлов на аккаунт",
            kind: "number",
            hint: "Жёсткий отказ при превышении — старые файлы не удаляются автоматически.",
          },
        ]}
      />

      <SettingsSection
        title="Реферальная программа"
        fields={[
          {
            key: "referral.percent",
            label: "Отчисления рефереру",
            kind: "number",
            suffix: "%",
            hint: "Начисляется на бонусный баланс пригласившего с каждого платежа приглашённого.",
          },
        ]}
      />

      <SettingsSection
        title="Lua"
        description="Исполнение скриптов интеграций в воркере."
        fields={[
          { key: "lua.call_timeout_sec", label: "Таймаут вызова", kind: "number", suffix: "сек" },
          {
            key: "lua.max_retries",
            label: "Повторов при таймауте",
            kind: "number",
            hint: "Скрипт должен быть идемпотентным — иначе повтор может выдать услугу дважды.",
          },
          { key: "lua.retry_backoff_sec", label: "Пауза перед повтором", kind: "number", suffix: "сек" },
        ]}
      />

      <SettingsSection
        title="Триггеры"
        fields={[
          { key: "triggers.max_retries", label: "Попыток выполнения действия", kind: "number" },
          {
            key: "triggers.max_fires_per_event_per_minute",
            label: "Срабатываний события в минуту",
            kind: "number",
            hint: "Анти-петля: защита от триггера, который своим действием запускает сам себя.",
          },
        ]}
      />
    </div>
  )
}
