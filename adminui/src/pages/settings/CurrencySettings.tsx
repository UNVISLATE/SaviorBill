import { useState } from "react"
import { useMutation, useQuery } from "@tanstack/react-query"
import { CheckCircle2, ExternalLink, KeyRound, Loader2, XCircle } from "lucide-react"

import { api } from "@/api/api.ts"
import { SettingsSection } from "./SettingsSection"
import { Badge } from "@/components/shadsnui/badge"
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

/** Проверка источника: запрос прямо сейчас и показ того, что сервер разобрал. */
function ProviderProbe({
  provider,
  apiKey,
}: {
  provider: string
  apiKey: string
}) {
  const [result, setResult] = useState<FxTestResult | null>(null)

  const test = useMutation({
    mutationFn: async () =>
      (
        await api.post<FxTestResult>("/v1/admin/settings/fx/test", {
          provider,
          api_key: apiKey || undefined,
        })
      ).data,
    onSuccess: setResult,
    onError: () =>
      setResult({ ok: false, base: "", rates: {}, total: 0, error: "запрос не удался" }),
  })

  return (
    <div className="space-y-2">
      <Button
        size="sm"
        variant="outline"
        disabled={!provider || test.isPending}
        onClick={() => test.mutate()}
      >
        {test.isPending && <Loader2 className="size-4 animate-spin" />}
        Проверить источник
      </Button>

      {!provider && (
        <p className="text-xs text-muted-foreground">Сначала выберите провайдера.</p>
      )}

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

/** Справка по доступным источникам — что требует ключ и где его взять. */
function ProvidersReference({ providers }: { providers: FxProvider[] }) {
  return (
    <div className="divide-y rounded-lg border">
      {providers.map((p) => (
        <div key={p.key} className="flex items-start justify-between gap-4 p-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-medium">{p.title}</span>
              {p.needs_key ? (
                <Badge variant="outline" className="gap-1 text-[10px]">
                  <KeyRound className="size-3" /> нужен ключ
                </Badge>
              ) : (
                <Badge variant="outline" className="text-[10px] text-emerald-500">
                  без ключа
                </Badge>
              )}
              {p.fixed_base && (
                <Badge variant="outline" className="text-[10px]">
                  только {p.fixed_base}
                </Badge>
              )}
            </div>
            <p className="mt-0.5 text-xs text-muted-foreground">{p.note}</p>
          </div>
          {p.signup_url && (
            <a
              href={p.signup_url}
              target="_blank"
              rel="noreferrer"
              className="flex shrink-0 items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            >
              Ключ <ExternalLink className="size-3" />
            </a>
          )}
        </div>
      ))}
    </div>
  )
}

/** Отдельная страница настроек курсов: базовая валюта, ручные курсы и
 * источник автоматических курсов с проверкой. */
export function CurrencySettings() {
  const { data: providers } = useQuery({
    queryKey: ["fx-providers"],
    queryFn: async () => (await api.get<FxProvider[]>("/v1/admin/settings/fx/providers")).data,
    staleTime: 10 * 60_000,
  })

  const providerOptions = [
    ...(providers ?? []).map((p) => ({ value: p.key, label: p.title })),
    { value: "lua", label: "Lua-скрипт (свой источник)" },
  ]

  return (
    <div className="max-w-3xl space-y-4">
      <SettingsSection
        title="Базовая валюта"
        description="Балансы аккаунтов ведутся только в ней. Платежи в других валютах конвертируются при зачислении."
        fields={[
          {
            key: "billing.currency",
            label: "Валюта инстанса",
            kind: "currency",
            placeholder: "RUB",
            hint: "Не меняйте на работающем инстансе без переноса данных: уже начисленные балансы не пересчитываются.",
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
        description="Приоритетнее любого источника. Задайте только те валюты, которые хотите зафиксировать."
        fields={[
          { key: "billing.fx.rates", label: "Курсы к базовой валюте", kind: "rates", wide: true },
        ]}
      />

      <SettingsSection
        title="Автоматические курсы"
        description="Откуда брать курсы валют, не заданных вручную."
        actions={(current) =>
          current["billing.fx.source"] === "api" ? (
            <ProviderProbe
              provider={current["billing.fx.provider"] ?? ""}
              apiKey={current["billing.fx.api_key"] ?? ""}
            />
          ) : null
        }
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
            label: "Источник",
            kind: "select",
            options: providerOptions,
            showIf: { key: "billing.fx.source", equals: ["api"] },
          },
          {
            key: "billing.fx.api_key",
            label: "API-ключ",
            showIf: { key: "billing.fx.source", equals: ["api"] },
            hint: "Нужен не всем источникам — см. таблицу ниже.",
          },
          {
            key: "billing.fx.lua_slug",
            label: "Slug Lua-скрипта",
            showIf: { key: "billing.fx.source", equals: ["api"] },
            hint: "Только для источника «Lua-скрипт». Формат ответа — см. docs/lua/fx.md.",
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

      {providers && providers.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-medium">Доступные источники</h3>
          <ProvidersReference providers={providers} />
          <p className="text-xs text-muted-foreground">
            Нужного сервиса нет в списке — выберите «Lua-скрипт» и напишите свой
            (формат в <code className="font-mono">docs/lua/fx.md</code>).
          </p>
        </div>
      )}
    </div>
  )
}
