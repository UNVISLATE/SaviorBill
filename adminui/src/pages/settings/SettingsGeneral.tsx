import { SettingField } from "./SettingField"

/** "Основное" — часто нужные настройки, для которых раньше приходилось
 * лезть в Raw-редактор и вручную знать точный ключ (см. PLAN.md). Сгруппировано
 * по смыслу на одной странице — заводить отдельную вкладку под 3-5 полей
 * каждая было бы избыточно. */
export function SettingsGeneral() {
  return (
    <div className="space-y-8">
      <section className="space-y-4">
        <div>
          <h3 className="text-sm font-semibold">Валюта и конвертация</h3>
          <p className="text-sm text-muted-foreground">
            Базовая валюта инстанса и правила конвертации платежей в других валютах.
          </p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <SettingField
            settingKey="billing.currency"
            label="Базовая валюта"
            hint="ISO-код (RUB, USD, EUR…). Баланс аккаунтов ведётся только в ней."
            placeholder="RUB"
          />
          <SettingField
            settingKey="billing.fx.source"
            label="Источник курсов"
            hint="'manual' — только billing.fx.rates ниже, 'api' — внешний JSON-API"
            placeholder="manual"
          />
          <SettingField
            settingKey="billing.fx.rates"
            label="Ручные курсы (JSON)"
            type="json"
            hint='Напр. {"USD": "95.5"} — сколько базовой валюты стоит 1 единица указанной'
            placeholder='{"USD": "95.5"}'
          />
          <SettingField
            settingKey="billing.fx.markup_percent"
            label="Спред при конвертации, %"
            type="int"
            hint="На сколько уменьшается зачисляемая сумма (0 — без наценки)"
            placeholder="0"
          />
          <SettingField
            settingKey="billing.fx.api_url"
            label="URL API курсов"
            hint="Только для источника 'api'"
          />
          <SettingField
            settingKey="billing.fx.api_path"
            label="Путь до курсов в ответе API"
            hint="Напр. 'data.rates'; пусто — курсы в корне ответа"
          />
          <SettingField
            settingKey="billing.fx.api_quote"
            label="Направление котировки API"
            hint="'base_per_unit' или 'unit_per_base'"
          />
          <SettingField
            settingKey="billing.fx.cache_ttl_sec"
            label="TTL кэша курсов API, сек"
            type="int"
          />
        </div>
      </section>

      <section className="space-y-4">
        <div>
          <h3 className="text-sm font-semibold">Безопасность</h3>
          <p className="text-sm text-muted-foreground">
            Требования ко входу в панель.
          </p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <SettingField
            settingKey="auth.2fa.required_for_admin"
            label="Обязательная 2FA для админов"
            type="bool"
            hint="Пока фактор не включён, такие аккаунты не смогут выполнять админ-действия"
          />
          <SettingField
            settingKey="session.ttl"
            label="TTL активной сессии, сек"
            type="int"
            placeholder="86400"
          />
        </div>
      </section>

      <section className="space-y-4">
        <div>
          <h3 className="text-sm font-semibold">Реферальная программа</h3>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <SettingField
            settingKey="referral.percent"
            label="Отчисления рефереру, %"
            type="int"
            hint="Начисляется на бонусный баланс пригласившего"
          />
        </div>
      </section>

      <section className="space-y-4">
        <div>
          <h3 className="text-sm font-semibold">Заказы</h3>
          <p className="text-sm text-muted-foreground">
            Повтор выдачи услуги после ошибки и компенсация при окончательном провале.
          </p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <SettingField
            settingKey="orders.delivery.max_attempts"
            label="Максимум попыток выдачи"
            type="int"
          />
          <SettingField
            settingKey="orders.delivery.retry_backoff_sec"
            label="Пауза между попытками, сек"
            type="int"
          />
        </div>
      </section>

      <section className="space-y-4">
        <div>
          <h3 className="text-sm font-semibold">Медиа: квоты</h3>
          <p className="text-sm text-muted-foreground">
            Суммарный объём хранимых медиа-файлов на аккаунт (не путать с
            лимитом размера одного файла — тот в разделе Raw settings, группа media).
          </p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <SettingField
            settingKey="media.quota.image_bytes"
            label="Квота без media.upload.video, байт"
            type="int"
            placeholder="52428800"
          />
          <SettingField
            settingKey="media.quota.video_bytes"
            label="Квота с media.upload.video, байт"
            type="int"
            placeholder="2147483648"
          />
        </div>
      </section>
    </div>
  )
}
