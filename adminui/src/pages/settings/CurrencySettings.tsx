import { useState } from "react"
import { useMutation, useQuery } from "@tanstack/react-query"
import { CheckCircle2, Loader2, XCircle } from "lucide-react"

import { api } from "@/api/api.ts"
import { useSettingsMap } from "@/hooks/use-settings-map"
import { SettingsSection } from "./SettingsSection"
import { Button } from "@/components/shadsnui/button"

interface FxProvider {
  key: string
  title: string
  needs_key: boolean
  signup_url: string | null
  fixed_base: string | null
  note: string
}

interface FxTestResult {
  ok: boolean
  base: string
  rates: Record<string, string>
  total: number
  error: string | null
}

/** Кнопка «Проверить» + результат: что сервер реально получил и разобрал. */
function ProviderProbe({ provider }: { provider: string }) {
  const [result, setResult] = useState<FxTestResult | null>(null)

  const test = useMutation({
    mutationFn: async () =>
      (await api.post<FxTestResult>("/v1/admin/settings/fx/test", { provider })).data,
    onSuccess: setResult,
    onError: () =>
      setResult({ ok: false, base: "", rates: {}, total: 0, error: "запрос не удался" }),
  })

  return (
    <div className="w-full space-y-2">
      <Button
        size="sm"
        variant="outline"
        disabled={!provider || test.isPending}
        onClick={() => test.mutate()}
      >
        {test.isPending && <Loader2 className="size-4 animate-spin" />}
        Проверить источник
      </Button>

      {result && (
        <div className="rounded-md border p-3 text-xs">
          {result.ok ? (
            <>
              <p className="flex items-center gap-1.5 font-medium text-emerald-500">
                <CheckCircle2 className="size-4" />
                Получено курсов: {result.total} (база {result.base})
              </p>
              <div className="mt-2 grid grid-cols-2 gap-x-6 gap-y-1 sm:grid-cols-3">
                {Object.entries(result.rates).map(([code, rate]) => (
                  <div key={code} className="flex justify-between gap-2 font-mono">
                    <span className="text-muted-foreground">{code}</span>
                    <span>{Number(rate).toFixed(4)}</span>
                  </div>
                ))}
              </div>
              <p className="mt-2 text-muted-foreground">
                Значения — сколько {result.base} за одну единицу валюты.
              </p>
            </>
          ) : (
            <p className="flex items-start gap-1.5 text-destructive">
              <XCircle className="mt-px size-4 shrink-0" />
              {result.error}
            </p>
          )}
        </div>
      )}
    </div>
  )
}

/** Секции курсов валют — вынесены отдельно, т.к. состав полей зависит от
 * выбранного провайдера, а рядом живёт кнопка проверки источника. */
export function CurrencySettings() {
  const { map } = useSettingsMap()
  const source = map.get("billing.fx.source") ?? "manual"
  const provider = map.get("billing.fx.provider") ?? ""

  const { data: providers } = useQuery({
    queryKey: ["fx-providers"],
    queryFn: async () => (await api.get<FxProvider[]>("/v1/admin/settings/fx/providers")).data,
    staleTime: 10 * 60_000,
  })

  const selected = providers?.find((p) => p.key === provider)
  const providerOptions = [
    ...(providers ?? []).map((p) => ({ value: p.key, label: p.title })),
    { value: "lua", label: "Lua-скрипт (свой источник)" },
  ]

  return (
    <>
      <SettingsSection
        title="Валюта"
        description="Баланс аккаунтов ведётся в базовой валюте; платежи в других валютах конвертируются при зачислении."
        fields={[
          {
            key: "billing.currency",
            label: "Базовая валюта",
            kind: "currency",
            placeholder: "RUB",
            hint: "Меняет валюту всех балансов. Не меняйте на работающем инстансе без переноса данных.",
          },
          {
            key: "billing.fx.markup_percent",
            label: "Спред",
            kind: "number",
            suffix: "%",
            placeholder: "0",
            hint: "На столько уменьшается зачисляемая сумма при конвертации. 0 — по курсу без наценки.",
          },
        ]}
      />

      <SettingsSection
        title="Ручные курсы"
        description="Приоритетнее любого провайдера — задайте здесь только те валюты, которые хотите зафиксировать."
        fields={[
          {
            key: "billing.fx.rates",
            label: "Курсы к базовой валюте",
            kind: "rates",
            wide: true,
          },
        ]}
      />

      <SettingsSection
        title="Источник курсов"
        description="Откуда брать курсы для валют, не заданных вручную."
        footerNote={selected?.note}
        actions={source === "api" ? <ProviderProbe provider={provider} /> : undefined}
        fields={[
          {
            key: "billing.fx.source",
            label: "Режим",
            kind: "select",
            options: [
              { value: "manual", label: "Только ручные курсы" },
              { value: "api", label: "Внешний источник" },
            ],
          },
          {
            key: "billing.fx.provider",
            label: "Провайдер",
            kind: "select",
            options: providerOptions,
            showIf: { key: "billing.fx.source", equals: ["api"] },
            hint: selected?.fixed_base
              ? `Работает только с базовой валютой ${selected.fixed_base}.`
              : "ЦБ РФ и Frankfurter не требуют регистрации.",
          },
          {
            key: "billing.fx.api_key",
            label: "API-ключ",
            showIf: { key: "billing.fx.source", equals: ["api"] },
            hint: selected?.signup_url
              ? `Получить ключ: ${selected.signup_url}`
              : "Нужен не всем провайдерам.",
          },
          {
            key: "billing.fx.lua_slug",
            label: "Slug Lua-скрипта",
            showIf: { key: "billing.fx.source", equals: ["api"] },
            hint: 'Скрипт должен вернуть { public = { rates = { USD = "95.5" } } }.',
          },
          {
            key: "billing.fx.cache_ttl_sec",
            label: "Кэш курсов",
            kind: "number",
            suffix: "сек",
            showIf: { key: "billing.fx.source", equals: ["api"] },
            hint: "Как долго переиспользовать ответ источника, не запрашивая заново.",
          },
        ]}
      />
    </>
  )
}
