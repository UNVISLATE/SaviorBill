import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { MoreHorizontal, Plus } from "lucide-react"

import { api } from "@/api/api.ts"
import { useAuth } from "@/hooks/use-auth"
import { Badge } from "@/components/shadsnui/badge"
import { Button } from "@/components/shadsnui/button"
import { Input } from "@/components/shadsnui/input"
import { Label } from "@/components/shadsnui/label"
import { Switch } from "@/components/shadsnui/switch"
import { Textarea } from "@/components/shadsnui/textarea"
import { Card, CardContent } from "@/components/shadsnui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/shadsnui/select"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/shadsnui/dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/shadsnui/dropdown-menu"
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

function errDetail(e: unknown): string | undefined {
  if (e && typeof e === "object" && "response" in e) {
    // @ts-expect-error — axios error shape
    const d = e.response?.data?.detail
    return typeof d === "string" ? d : undefined
  }
  return undefined
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
  const [slug, setSlug] = useState(provider?.slug ?? "")
  const [title, setTitle] = useState(provider?.title ?? "")
  const [currency, setCurrency] = useState(provider?.currency ?? "RUB")
  const [scriptId, setScriptId] = useState(provider?.script_id ? String(provider.script_id) : "")
  const [enabled, setEnabled] = useState(provider?.enabled ?? false)
  const [secretsText, setSecretsText] = useState("{}")
  const qc = useQueryClient()

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
        (e as Error).message === "invalid json" ? "secrets должен быть корректным JSON" : errDetail(e),
      ),
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEdit ? "Изменить провайдера" : "Новый платёжный провайдер"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          {!isEdit && (
            <div className="space-y-1">
              <Label>Слаг</Label>
              <Input value={slug} onChange={(e) => setSlug(e.target.value)} placeholder="yookassa" autoFocus />
            </div>
          )}
          <div className="space-y-1">
            <Label>Название</Label>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="ЮKassa" />
          </div>
          <div className="space-y-1">
            <Label>Валюта</Label>
            <Input value={currency} onChange={(e) => setCurrency(e.target.value.toUpperCase())} maxLength={8} />
          </div>
          <div className="space-y-1">
            <Label>Lua-скрипт (обрабатывает создание/проверку/возврат платежа)</Label>
            <Select value={scriptId} onValueChange={(v) => setScriptId(v ?? "")}>
              <SelectTrigger>
                <SelectValue placeholder="Выберите скрипт" />
              </SelectTrigger>
              <SelectContent>
                {paymentScripts?.map((s) => (
                  <SelectItem key={s.id} value={String(s.id)}>
                    {s.name ?? s.slug}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {(paymentScripts?.length ?? 0) === 0 && (
              <p className="text-xs text-muted-foreground">
                Нет скриптов типа «payment» — создайте на странице «Скрипты».
              </p>
            )}
          </div>
          <div className="flex items-center justify-between">
            <Label>Включён</Label>
            <Switch checked={enabled} onCheckedChange={setEnabled} />
          </div>
          <div className="space-y-1">
            <Label>Секреты (JSON, шифруются на сервере)</Label>
            <Textarea
              className="font-mono text-xs"
              rows={4}
              value={secretsText}
              onChange={(e) => setSecretsText(e.target.value)}
              placeholder={isEdit ? "Оставьте {} чтобы не менять" : '{"shop_id": "...", "secret_key": "..."}'}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Отмена
          </Button>
          <Button
            disabled={(!isEdit && slug.trim().length < 2) || save.isPending}
            onClick={() => save.mutate()}
          >
            {isEdit ? "Сохранить" : "Создать"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** Настройки → «Платёжные провайдеры» — вынесено из /purchases (см. bug-list
 * пользователя: провайдеры — это конфигурация, а не список операций, ей
 * место рядом с остальными настройками, а не среди платежей). */
export function PaymentProvidersSettings() {
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
    <div className="space-y-3">
      <div className="flex items-baseline justify-between">
        <div>
          <h2 className="text-lg font-semibold">Платёжные провайдеры</h2>
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
