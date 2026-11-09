import { useEffect, useState, useMemo } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useSearchParams } from "react-router-dom"
import {
  CreditCard,
  ExternalLink,
  KeyRound,
  Percent,
  Plus,
  Trash2,
} from "lucide-react"

import { api } from "@/api/api.ts"
import { getErrorDetail } from "@/lib/api-error.ts"
import { useAuth } from "@/hooks/use-auth"
import { useInstanceCurrency } from "@/lib/currency"
import { toastError, toastSuccess } from "@/lib/toast"
import { TabbedDialog, type TabDefinition } from "@/components/common/TabbedDialog"
import { KeySecretEditor } from "@/components/common/forms/KeySecretEditor"
import { CurrencySelect } from "@/components/common/CurrencySelect"
import { CurrencyTagSelect } from "@/components/common/CurrencyTagSelect"
import { LuaScriptSelect, type LuaScriptOption } from "@/components/common/LuaScriptSelect"
import { Badge } from "@/components/shadsnui/badge"
import { Button } from "@/components/shadsnui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/shadsnui/card"
import { Input } from "@/components/shadsnui/input"
import { Label } from "@/components/shadsnui/label"
import { Switch } from "@/components/shadsnui/switch"

interface Provider {
  id: number
  slug: string
  title: string | null
  enabled: boolean
  currency: string
  currencies: string[]
  fee_enabled?: boolean
  fee_percent?: number
  add_fee_to_amount?: boolean
  script_id: number | null
  script_version: number | null
  extra: Record<string, unknown>
}


function ProviderFormDialog({
  open,
  onOpenChange,
  provider,
  paymentScripts,
  initialScriptId,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  provider: Provider | null
  paymentScripts: LuaScriptOption[] | undefined
  initialScriptId?: string | null
}) {
  const isEdit = !!provider
  const [slug, setSlug] = useState("")
  const [title, setTitle] = useState("")
  const { currency: instanceCurrency } = useInstanceCurrency()
  const [currency, setCurrency] = useState(instanceCurrency || "RUB")
  const [optionalCurrencies, setOptionalCurrencies] = useState<string[]>([])
  const [feeEnabled, setFeeEnabled] = useState(false)
  const [feePercent, setFeePercent] = useState("0")
  const [addFeeToAmount, setAddFeeToAmount] = useState(true)
  const [scriptId, setScriptId] = useState("")
  const [enabled, setEnabled] = useState(false)
  const [secretsText, setSecretsText] = useState("{}")
  const qc = useQueryClient()

  useEffect(() => {
    if (open) {
      if (provider) {
        setSlug(provider.slug ?? "")
        setTitle(provider.title ?? "")
        setCurrency(provider.currency ?? instanceCurrency ?? "RUB")
        setOptionalCurrencies(provider.currencies ?? [])
        setFeeEnabled(provider.fee_enabled ?? false)
        setFeePercent(String(provider.fee_percent ?? 0))
        setAddFeeToAmount(provider.add_fee_to_amount ?? true)
        setScriptId(provider.script_id ? String(provider.script_id) : "")
        setEnabled(provider.enabled ?? false)
        setSecretsText("{}")
      } else {
        const matched = initialScriptId && paymentScripts ? paymentScripts.find((s) => String(s.id) === String(initialScriptId)) : null
        const m = ((matched?.settings as any)?.manifest as any) || ((matched?.settings as any) || {})
        const pref = m.prefill || {}
        setSlug(pref.slug || matched?.slug || "")
        setTitle(pref.name || matched?.name || matched?.slug || "")
        setCurrency(instanceCurrency || "RUB")
        setOptionalCurrencies([])
        setFeeEnabled(false)
        setFeePercent("0")
        setAddFeeToAmount(true)
        setScriptId(matched ? String(matched.id) : "")
        setEnabled(true)
        setSecretsText("{}")
      }
    }
  }, [open, provider, instanceCurrency, initialScriptId, paymentScripts])

  const save = useMutation({
    mutationFn: async () => {
      let secrets: unknown = {}
      if (secretsText.trim()) {
        try {
          secrets = JSON.parse(secretsText)
        } catch {
          throw new Error("invalid json")
        }
      }
      const body = {
        title: title || null,
        enabled,
        currency,
        currencies: optionalCurrencies,
        fee_enabled: feeEnabled,
        fee_percent: Number(feePercent) || 0,
        add_fee_to_amount: addFeeToAmount,
        script_id: scriptId ? Number(scriptId) : null,
        secrets,
      }
      if (isEdit) return api.patch(`/v1/admin/purchases/providers/${provider!.id}`, body)
      return api.post("/v1/admin/purchases/providers", { slug, ...body })
    },
    onSuccess: () => {
      toastSuccess(isEdit ? "Провайдер обновлён" : "Провайдер создан")
      onOpenChange(false)
      void qc.invalidateQueries({ queryKey: ["admin-pay-providers"] })
    },
    onError: (e: unknown) =>
      toastError(
        isEdit ? "Не удалось обновить провайдера" : "Не удалось создать провайдера",
        (e as Error).message === "invalid json" ? "secrets должен быть корректным JSON" : getErrorDetail(e),
      ),
  })

  const selectedScript = useMemo(() => {
    if (!scriptId || !paymentScripts) return null
    return paymentScripts.find((s) => String(s.id) === String(scriptId)) ?? null
  }, [scriptId, paymentScripts])

  const scriptSettingsSchema = useMemo(() => {
    if (!selectedScript?.settings) return undefined
    const set = selectedScript.settings as Record<string, any>
    const m = set.manifest || set
    const fields = m.settings_form || m.client_order_form
    return Array.isArray(fields) && fields.length > 0 ? fields : undefined
  }, [selectedScript])

  const tabs: TabDefinition[] = [
    {
      id: "general",
      label: "Основное",
      icon: CreditCard,
      content: (
        <div className="space-y-4 text-xs">
          {!isEdit && (
            <div className="space-y-1.5">
              <Label className="text-xs">Слаг провайдера (уникальный ключ)</Label>
              <Input
                value={slug}
                onChange={(e) => setSlug(e.target.value)}
                placeholder="yookassa"
                autoFocus
                className="font-mono text-xs"
              />
              <p className="text-[10px] text-muted-foreground">Используется в API, например `yookassa`, `robokassa`, `cryptopay`</p>
            </div>
          )}
          <div className="space-y-1.5">
            <Label className="text-xs">Отображаемое название</Label>
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="ЮKassa (Банковские карты)"
              className="text-xs"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Основная валюта *</Label>
              <CurrencySelect
                value={currency}
                onChange={setCurrency}
                placeholder="RUB"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Статус активности</Label>
              <div className="flex h-9 items-center justify-between rounded-md border border-input bg-background px-3 py-1">
                <span className="text-xs text-muted-foreground">{enabled ? "Активен" : "Отключен"}</span>
                <Switch checked={enabled} onCheckedChange={setEnabled} />
              </div>
            </div>
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">Поддерживаемые валюты (теги)</Label>
            <CurrencyTagSelect
              value={optionalCurrencies}
              onChange={setOptionalCurrencies}
              placeholder="Выберите или введите валюту..."
            />
            <p className="text-[10px] text-muted-foreground">
              Дополнительные валюты, которые поддерживает платёжка (если для основной нет курса).
            </p>
          </div>

          {/* Настройка комиссии платежного провайдера */}
          <div className="space-y-3 rounded-lg border p-3 bg-muted/20">
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label className="text-xs flex items-center gap-1.5">
                  <Percent className="size-3.5 text-primary" /> Учитывать комиссию платёжной системы
                </Label>
                <p className="text-[11px] text-muted-foreground">
                  Настройка тарифа платёжного шлюза для автоматического расчёта
                </p>
              </div>
              <Switch checked={feeEnabled} onCheckedChange={setFeeEnabled} />
            </div>

            {feeEnabled && (
              <div className="space-y-3 pt-2 border-t text-xs">
                <div className="space-y-1.5">
                  <Label className="text-xs">Комиссия платёжного провайдера (%)</Label>
                  <div className="flex items-center gap-2">
                    <Input
                      type="number"
                      step="0.01"
                      min="0"
                      max="100"
                      value={feePercent}
                      onChange={(e) => setFeePercent(e.target.value)}
                      placeholder="3.5"
                      className="font-mono text-xs max-w-[120px]"
                    />
                    <span className="text-xs font-semibold text-muted-foreground">%</span>
                  </div>
                  <p className="text-[10px] text-muted-foreground">
                    Процент, который шлюз взимает за эквайринг/обработку платежа.
                  </p>
                </div>

                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <Label className="text-xs">Прибавлять комиссию к сумме счёта</Label>
                    <p className="text-[10px] text-muted-foreground">
                      {addFeeToAmount
                        ? "Комиссию оплачивает покупатель (прибавляется к счёту при создании платежа)"
                        : "Комиссию покрывает магазин (покупатель платит ровную сумму без наценки)"}
                    </p>
                  </div>
                  <Switch checked={addFeeToAmount} onCheckedChange={setAddFeeToAmount} />
                </div>
              </div>
            )}
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">Lua-скрипт обработки платежей</Label>
            <LuaScriptSelect
              value={scriptId}
              onChange={setScriptId}
              scripts={paymentScripts}
              kind="payment"
              placeholder="Выберите скрипт обработки платежей..."
            />
            <p className="text-[10px] text-muted-foreground">
              Скрипт формирует ссылки на оплату и проверяет webhook-нотификации
            </p>
          </div>
        </div>
      ),
    },
    {
      id: "secrets",
      label: "Ключи и секреты",
      icon: KeyRound,
      badge: isEdit ? "Зашифровано" : undefined,
      content: (
        <div className="space-y-3">
          <KeySecretEditor
            title="Секретные ключи API"
            description={
              isEdit
                ? "Оставьте значения пустыми или {}, если не хотите менять сохранённые секреты"
                : selectedScript
                ? `Параметры интеграции для скрипта «${selectedScript.name || selectedScript.slug}»`
                : "Укажите параметры и секретные ключи API платёжного шлюза"
            }
            value={secretsText}
            schema={scriptSettingsSchema}
            variant="flat"
            onChange={(_, text) => setSecretsText(text)}
          />
        </div>
      ),
    },
  ]

  return (
    <TabbedDialog
      open={open}
      onOpenChange={onOpenChange}
      title={isEdit ? `Провайдер «${provider?.title || provider?.slug}»` : "Новый платёжный провайдер"}
      description="Настройка шлюза приёма платежей и интеграции с платёжной системой"
      tabs={tabs}
      primaryAction={{
        label: isEdit ? "Сохранить изменения" : "Создать провайдера",
        onClick: () => save.mutate(),
        disabled: (!isEdit && slug.trim().length < 2) || save.isPending,
        loading: save.isPending,
      }}
      secondaryAction={{
        label: "Отмена",
        onClick: () => onOpenChange(false),
      }}
    />
  )
}

export function PaymentProvidersPage() {
  const { can } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  const createScriptId = searchParams.get("create_from_script")
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<Provider | null>(null)
  const canCreate = can("purchases.providers.create")
  const canEdit = can("purchases.providers.edit")
  const canDelete = can("purchases.providers.delete")
  const qc = useQueryClient()

  const { data: providers, isLoading } = useQuery({
    queryKey: ["admin-pay-providers"],
    queryFn: async () => (await api.get<Provider[]>("/v1/admin/purchases/providers")).data,
  })

  const { data: allScripts } = useQuery({
    queryKey: ["admin-lua-scripts"],
    queryFn: async () => {
      const res = await api.get<LuaScriptOption[]>("/v1/admin/lua")
      return Array.isArray(res.data) ? res.data : []
    },
  })

  const paymentScripts = useMemo(
    () => allScripts?.filter((s) => s.kind === "payment") ?? [],
    [allScripts]
  )

  useEffect(() => {
    if (createScriptId && allScripts) {
      setCreating(true)
    }
  }, [createScriptId, allScripts])

  const toggle = useMutation({
    mutationFn: async ({ id, enabled }: { id: number; enabled: boolean }) =>
      api.patch(`/v1/admin/purchases/providers/${id}`, { enabled }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["admin-pay-providers"] })
      toastSuccess("Статус провайдера обновлён")
    },
    onError: (e: unknown) => toastError("Не удалось обновить статус", getErrorDetail(e)),
  })

  const remove = useMutation({
    mutationFn: async (id: number) => api.delete(`/v1/admin/purchases/providers/${id}`),
    onSuccess: () => {
      toastSuccess("Провайдер удалён")
      void qc.invalidateQueries({ queryKey: ["admin-pay-providers"] })
    },
    onError: (e: unknown) => toastError("Не удалось удалить провайдера", getErrorDetail(e)),
  })

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <div>
          <h1 className="text-xl font-semibold">Платёжные провайдеры</h1>
          <p className="text-sm text-muted-foreground">
            Шлюзы оплаты и интеграции с внешними системами
          </p>
        </div>
        {canCreate && (
          <Button size="sm" onClick={() => setCreating(true)}>
            <Plus className="mr-1.5 size-4" /> Добавить
          </Button>
        )}
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Загрузка провайдеров…</p>}

      {!isLoading && (!providers || providers.length === 0) && (
        <p className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
          Нет подключенных провайдеров. Создайте первого провайдера, чтобы пользователи могли пополнять баланс.
        </p>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {providers?.map((p) => {
          const script = paymentScripts?.find((s) => s.id === p.script_id)
          return (
            <Card
              key={p.id}
              className="flex flex-col justify-between transition-colors hover:border-primary/50 cursor-pointer"
              onClick={() => canEdit && setEditing(p)}
            >
              <CardHeader className="space-y-1">
                <div className="flex items-start justify-between">
                  <div className="space-y-0.5 min-w-0 pr-2">
                    <CardTitle className="text-base truncate">{p.title || p.slug}</CardTitle>
                    <p className="font-mono text-xs text-muted-foreground">{p.slug}</p>
                  </div>
                  <Switch
                    checked={p.enabled}
                    disabled={!canEdit || toggle.isPending}
                    onCheckedChange={(v) => toggle.mutate({ id: p.id, enabled: v })}
                    onClick={(e) => e.stopPropagation()}
                  />
                </div>
              </CardHeader>
              <CardContent className="space-y-2 text-xs">
                <div className="flex flex-wrap items-center gap-1">
                  <Badge variant="outline" className="font-mono text-[10px]">
                    Основная: {p.currency}
                  </Badge>
                  {p.currencies && p.currencies.length > 0 && (
                    p.currencies.map((c) => (
                      <Badge key={c} variant="secondary" className="font-mono text-[10px]">
                        {c}
                      </Badge>
                    ))
                  )}
                  {p.fee_enabled && (
                    <Badge variant="outline" className="text-[10px] text-amber-600 border-amber-500/30">
                      +{p.fee_percent}% {p.add_fee_to_amount ? "к счёту" : "комиссия"}
                    </Badge>
                  )}
                </div>
                <div className="text-muted-foreground">
                  Скрипт: {script ? <span className="text-foreground">{script.name ?? script.slug}</span> : <span className="italic">не выбран</span>}
                </div>
                <div className="flex items-center justify-between pt-2 border-t">
                  <a
                    href={`/api/v1/user/purchases/callback/${p.slug}`}
                    target="_blank"
                    rel="noreferrer"
                    onClick={(e) => e.stopPropagation()}
                    className="text-[11px] text-muted-foreground hover:text-foreground inline-flex items-center gap-1"
                  >
                    Webhook URL <ExternalLink className="size-3" />
                  </a>
                  {canDelete && (
                    <Button
                      size="icon"
                      variant="ghost"
                      className="size-7 text-destructive hover:text-destructive hover:bg-destructive/10"
                      onClick={(e) => {
                        e.stopPropagation()
                        if (confirm(`Удалить провайдера ${p.slug}?`)) remove.mutate(p.id)
                      }}
                    >
                      <Trash2 className="size-3.5" />
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          )
        })}
      </div>

      <ProviderFormDialog
        open={creating || editing !== null}
        onOpenChange={(v) => {
          if (!v) {
            setCreating(false)
            setEditing(null)
            if (createScriptId) {
              setSearchParams({})
            }
          }
        }}
        provider={editing}
        paymentScripts={paymentScripts}
        initialScriptId={createScriptId}
      />
    </div>
  )
}
