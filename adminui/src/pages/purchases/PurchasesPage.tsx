import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { MoreHorizontal, Plus, RefreshCw, Undo2 } from "lucide-react"

import { api } from "@/api/api.ts"
import { useAuth } from "@/hooks/use-auth"
import { useDataTableQuery } from "@/hooks/use-data-table"
import { DataTable, type DataTableColumn } from "@/components/data-table/DataTable"
import { Badge } from "@/components/shadsnui/badge"
import { Button } from "@/components/shadsnui/button"
import { Input } from "@/components/shadsnui/input"
import { Label } from "@/components/shadsnui/label"
import { Switch } from "@/components/shadsnui/switch"
import { Textarea } from "@/components/shadsnui/textarea"
import { Card, CardContent } from "@/components/shadsnui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/shadsnui/tabs"
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

interface Payment {
  id: number
  account_id: number
  provider: string
  amount: string
  currency: string
  status: string
  target: string
  external_id: string | null
  public_data: Record<string, unknown>
  private_data: Record<string, unknown>
  created_at: string
}

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

interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
  has_more: boolean
}

const STATUS_VARIANT: Record<string, "default" | "outline" | "destructive" | "secondary"> = {
  pending: "secondary",
  paid: "default",
  failed: "destructive",
  refunded: "outline",
  wait: "destructive",
}

function errDetail(e: unknown): string | undefined {
  if (e && typeof e === "object" && "response" in e) {
    // @ts-expect-error — axios error shape
    const d = e.response?.data?.detail
    return typeof d === "string" ? d : undefined
  }
  return undefined
}

function PaymentDetailDialog({ payment, onOpenChange }: { payment: Payment; onOpenChange: (v: boolean) => void }) {
  const { can } = useAuth()
  const qc = useQueryClient()
  const canRecheck = can("purchases.recheck")
  const canRefund = can("purchases.refund")

  const recheck = useMutation({
    mutationFn: async () => api.post(`/v1/admin/purchases/${payment.id}/recheck`),
    onSuccess: () => {
      toastSuccess("Статус платежа обновлён")
      void qc.invalidateQueries({ queryKey: ["admin-payments"] })
      onOpenChange(false)
    },
    onError: (e: unknown) => toastError("Не удалось проверить платёж", errDetail(e)),
  })

  const refund = useMutation({
    mutationFn: async () => api.post(`/v1/admin/purchases/${payment.id}/refund`),
    onSuccess: () => {
      toastSuccess("Возврат оформлен")
      void qc.invalidateQueries({ queryKey: ["admin-payments"] })
      onOpenChange(false)
    },
    onError: (e: unknown) => toastError("Не удалось оформить возврат", errDetail(e)),
  })

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Платёж #{payment.id}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 text-sm">
          <div className="grid grid-cols-2 gap-2">
            <div>
              <p className="text-xs text-muted-foreground">Пользователь</p>
              <p className="font-mono">#{payment.account_id}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Провайдер</p>
              <p>{payment.provider}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Сумма</p>
              <p>{payment.amount} {payment.currency}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Статус</p>
              <Badge variant={STATUS_VARIANT[payment.status] ?? "outline"}>{payment.status}</Badge>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Назначение</p>
              <p>{payment.target === "balance" ? "пополнение баланса" : "оплата услуги"}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">ID у провайдера</p>
              <p className="truncate font-mono text-xs">{payment.external_id ?? "—"}</p>
            </div>
          </div>
          <div>
            <p className="mb-1 text-xs text-muted-foreground">Ответ провайдера (private_data)</p>
            <pre className="max-h-32 overflow-auto rounded-md bg-muted p-2 text-xs">
              {JSON.stringify(payment.private_data, null, 2)}
            </pre>
          </div>
        </div>
        <DialogFooter>
          {canRecheck && (
            <Button variant="outline" disabled={recheck.isPending} onClick={() => recheck.mutate()}>
              <RefreshCw className="size-4" /> Проверить статус
            </Button>
          )}
          {canRefund && payment.status === "paid" && (
            <Button variant="destructive" disabled={refund.isPending} onClick={() => refund.mutate()}>
              <Undo2 className="size-4" /> Возврат
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function PaymentsTab() {
  const table = useDataTableQuery()
  const [detail, setDetail] = useState<Payment | null>(null)

  const { data, isLoading, isError } = useQuery({
    queryKey: ["admin-payments", table.limit, table.offset, table.sort, table.search],
    queryFn: async () =>
      (
        await api.get<Page<Payment>>("/v1/admin/purchases", {
          params: {
            limit: table.limit,
            offset: table.offset,
            sort: table.sort ?? undefined,
            q: table.search || undefined,
          },
        })
      ).data,
    placeholderData: (prev) => prev,
  })

  const columns: DataTableColumn<Payment>[] = [
    { key: "id", header: "ID", render: (p) => <span className="font-mono text-xs">{p.id}</span> },
    { header: "Пользователь", render: (p) => <span className="font-mono text-xs">#{p.account_id}</span> },
    { key: "provider", header: "Провайдер", render: (p) => p.provider },
    { key: "amount", header: "Сумма", render: (p) => `${p.amount} ${p.currency}` },
    {
      header: "Статус",
      render: (p) => <Badge variant={STATUS_VARIANT[p.status] ?? "outline"}>{p.status}</Badge>,
    },
    {
      key: "created_at",
      header: "Создан",
      render: (p) => new Date(p.created_at).toLocaleString(),
    },
  ]

  return (
    <>
      <DataTable
        columns={columns}
        data={data?.items ?? []}
        total={data?.total ?? 0}
        isLoading={isLoading}
        isError={isError}
        getRowId={(p) => p.id}
        onRowClick={(p) => setDetail(p)}
        sort={table.sort}
        onToggleSort={table.toggleSort}
        searchValue={table.searchInput}
        onSearchChange={table.setSearchInput}
        searchPlaceholder="Поиск по провайдеру/внешнему ID…"
        emptyMessage="Платежей не найдено"
        emptyHint={table.search ? "Попробуйте изменить запрос." : "Здесь появятся платежи пользователей."}
        limit={table.limit}
        offset={table.offset}
        hasMore={data?.has_more ?? false}
        onLimitChange={table.changeLimit}
        onOffsetChange={table.setOffset}
      />
      {detail && <PaymentDetailDialog payment={detail} onOpenChange={(v) => !v && setDetail(null)} />}
    </>
  )
}

function ProviderFormDialog({
  open,
  onOpenChange,
  provider,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  provider: Provider | null
}) {
  const isEdit = !!provider
  const [slug, setSlug] = useState(provider?.slug ?? "")
  const [title, setTitle] = useState(provider?.title ?? "")
  const [currency, setCurrency] = useState(provider?.currency ?? "RUB")
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
      const body = { title: title || null, enabled, currency, secrets }
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

function ProvidersTab() {
  const { can } = useAuth()
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<Provider | null>(null)
  const canCreate = can("purchases.providers.create")
  const canEdit = can("purchases.providers.edit")

  const { data, isLoading } = useQuery({
    queryKey: ["admin-pay-providers"],
    queryFn: async () => (await api.get<Provider[]>("/v1/admin/purchases/providers")).data,
  })

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
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
      <ProviderFormDialog open={creating} onOpenChange={setCreating} provider={null} />
      {editing && (
        <ProviderFormDialog open={!!editing} onOpenChange={(v) => !v && setEditing(null)} provider={editing} />
      )}
    </div>
  )
}

export function PurchasesPage() {
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Платежи</h1>
      <Tabs defaultValue="payments">
        <TabsList>
          <TabsTrigger value="payments">Платежи</TabsTrigger>
          <TabsTrigger value="providers">Провайдеры</TabsTrigger>
        </TabsList>
        <TabsContent value="payments">
          <PaymentsTab />
        </TabsContent>
        <TabsContent value="providers">
          <ProvidersTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}
