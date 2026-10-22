import { useState, useEffect } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { CreditCard, KeyRound, MoreHorizontal, Plus } from "lucide-react"

import { api } from "@/api/api.ts"
import { getErrorDetail } from "@/lib/api-error.ts"
import { useAuth } from "@/hooks/use-auth"
import { Badge } from "@/components/shadsnui/badge"
import { Button } from "@/components/shadsnui/button"
import { Input } from "@/components/shadsnui/input"
import { Label } from "@/components/shadsnui/label"
import { Switch } from "@/components/shadsnui/switch"
import { Card, CardContent } from "@/components/shadsnui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/shadsnui/select"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/shadsnui/dropdown-menu"
import { TabbedDialog, type TabDefinition } from "@/components/common/TabbedDialog"
import { KeySecretEditor, COMMON_PAYMENT_PRESETS } from "@/components/common/forms/KeySecretEditor"
import { useInstanceCurrency } from "@/lib/currency"
import { toastError, toastSuccess } from "@/lib/toast"

interface Provider {
  id: number
  slug: string
  title: string | null
  enabled: boolean
  currency: string
  script_id: number | null
  script_version: number | null
  extra: Record<string, unknown>
}

interface LuaScript {
  id: number
  name: string | null
  slug: string
  kind: string
}

function ProviderFormDialog({
  open,
  onOpenChange,
  provider,
  paymentScripts,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  provider: Provider | null
  paymentScripts: LuaScript[] | undefined
}) {
  const isEdit = !!provider
  const [slug, setSlug] = useState("")
  const [title, setTitle] = useState("")
  const { currency: instanceCurrency } = useInstanceCurrency()
  const [currency, setCurrency] = useState(instanceCurrency || "RUB")
  const [scriptId, setScriptId] = useState("")
  const [enabled, setEnabled] = useState(false)
  const [secretsText, setSecretsText] = useState("{}")
  const qc = useQueryClient()

  useEffect(() => {
    if (open) {
      setSlug(provider?.slug ?? "")
      setTitle(provider?.title ?? "")
      setCurrency(provider?.currency ?? instanceCurrency ?? "RUB")
      setScriptId(provider?.script_id ? String(provider.script_id) : "")
      setEnabled(provider?.enabled ?? false)
      setSecretsText("{}")
    }
  }, [open, provider])

  const selectedScript = paymentScripts?.find((s) => String(s.id) === scriptId)

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

  const tabs: TabDefinition[] = [
    {
      id: "general",
      label: "Основное",
      icon: CreditCard,
      content: (
        <div className="space-y-4">
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
              <Label className="text-xs">Базовая валюта</Label>
              <Input
                value={currency}
                onChange={(e) => setCurrency(e.target.value.toUpperCase())}
                maxLength={8}
                className="font-mono text-xs uppercase"
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
            <Label className="text-xs">Lua-скрипт обработки платежей</Label>
            <Select value={scriptId} onValueChange={(v) => setScriptId(v ?? "")}>
              <SelectTrigger className="text-xs">
                <SelectValue placeholder="Выберите Lua-скрипт">
                  {selectedScript ? (selectedScript.name ?? selectedScript.slug) : undefined}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {paymentScripts?.map((s) => (
                  <SelectItem key={s.id} value={String(s.id)} className="text-xs">
                    {s.name ?? s.slug}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {(paymentScripts?.length ?? 0) === 0 ? (
              <p className="text-xs text-muted-foreground">
                Нет скриптов типа «payment» — создайте их на странице «Lua-скрипты».
              </p>
            ) : (
              <p className="text-[10px] text-muted-foreground">
                Скрипт формирует ссылки на оплату и проверяет webhook-нотификации
              </p>
            )}
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
                : "Укажите ключи мерчанта или выберите готовый шаблон провайдера"
            }
            presets={COMMON_PAYMENT_PRESETS}
            value={secretsText}
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
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<Provider | null>(null)
  const canCreate = can("purchases.providers.create")
  const canEdit = can("purchases.providers.edit")

  const { data, isLoading } = useQuery({
    queryKey: ["admin-pay-providers"],
    queryFn: async () => (await api.get<Provider[]>("/v1/admin/purchases/providers")).data,
  })

  const { data: scripts } = useQuery({
    queryKey: ["admin-lua-scripts-lookup"],
    queryFn: async () => (await api.get<LuaScript[]>("/v1/admin/lua")).data,
    staleTime: 60_000,
  })
  const paymentScripts = scripts?.filter((s) => s.kind === "payment")

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <div>
          <h1 className="text-xl font-semibold">Платёжные провайдеры</h1>
          <p className="text-sm text-muted-foreground">
            Провайдеры пополнения баланса и оплаты услуг — каждый обрабатывается своим Lua-скриптом.
          </p>
        </div>
        {canCreate && (
          <Button size="sm" onClick={() => setCreating(true)}>
            <Plus className="size-4" /> Добавить провайдера
          </Button>
        )}
      </div>
      {isLoading && <p className="text-sm text-muted-foreground">Загрузка…</p>}
      {!isLoading && (data?.length ?? 0) === 0 && (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            Провайдеры ещё не настроены.
          </CardContent>
        </Card>
      )}
      <div className="grid gap-2">
        {data?.map((p) => (
          <Card key={p.id}>
            <CardContent className="flex items-center justify-between gap-3 py-3">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-medium">{p.title ?? p.slug}</span>
                  <span className="font-mono text-xs text-muted-foreground">{p.slug}</span>
                  <Badge variant={p.enabled ? "default" : "outline"}>{p.enabled ? "включён" : "выключен"}</Badge>
                </div>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  Валюта: {p.currency}
                  {p.script_id ? ` · Lua-скрипт #${p.script_id}` : ""}
                </p>
              </div>
              {canEdit && (
                <DropdownMenu>
                  <DropdownMenuTrigger
                    render={
                      <Button variant="ghost" size="icon" className="size-8">
                        <MoreHorizontal className="size-4" />
                      </Button>
                    }
                  />
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={() => setEditing(p)}>Изменить</DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
      <ProviderFormDialog open={creating} onOpenChange={setCreating} provider={null} paymentScripts={paymentScripts} />
      {editing && (
        <ProviderFormDialog
          open={!!editing}
          onOpenChange={(v) => !v && setEditing(null)}
          provider={editing}
          paymentScripts={paymentScripts}
        />
      )}
    </div>
  )
}
