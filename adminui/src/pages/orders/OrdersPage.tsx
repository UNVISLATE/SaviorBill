import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { FileText, PackageCheck, Plus, Sparkles, UserRound } from "lucide-react"

import { api } from "@/api/api.ts"
import { getErrorDetail } from "@/lib/api-error.ts"
import { useAuth } from "@/hooks/use-auth"
import { useProfileDialog } from "@/hooks/use-profile-dialog"
import { useInstanceCurrency } from "@/lib/currency"
import { useDataTableQuery } from "@/hooks/use-data-table"
import { DataTable, type DataTableColumn } from "@/components/data-table/DataTable"
import { UserPickerDialog } from "@/components/users/UserPickerDialog"
import { TabbedDialog } from "@/components/common/TabbedDialog"
import { DataPropertySheet } from "@/components/common/DataPropertySheet"
import { Badge } from "@/components/shadsnui/badge"
import { Button } from "@/components/shadsnui/button"
import { Label } from "@/components/shadsnui/label"
import { Switch } from "@/components/shadsnui/switch"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/shadsnui/select"
import { toastError, toastSuccess } from "@/lib/toast"

interface Order {
  id: number
  service_id: number
  account_id: number
  payment_id: number | null
  status: string
  price: string
  discount: string
  product_key: string | null
  expires_at: string | null
  created_at: string
  delivered_at: string | null
  error: string | null
  public_data: Record<string, unknown>
  private_data: Record<string, unknown>
}

interface Service {
  id: number
  name: string
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
  active: "default",
  frozen: "outline",
  stopped: "destructive",
  expired: "outline",
  failed: "destructive",
  cancelled: "destructive",
}

function OrderDetailDialog({ order, onOpenChange }: { order: Order; onOpenChange: (v: boolean) => void }) {
  const [activeTab, setActiveTab] = useState<string>("info")
  const { openUserProfile } = useProfileDialog()
  const { symbol } = useInstanceCurrency()

  const tabs = [
    { id: "info", title: "Детали заказа", icon: FileText },
    {
      id: "delivery",
      title: "Данные выдачи",
      icon: PackageCheck,
      badge: Object.keys(order.public_data || {}).length > 0 ? "данные" : undefined,
    },
  ]

  return (
    <TabbedDialog
      open
      onOpenChange={onOpenChange}
      title={`Заказ #${order.id}`}
      description={`Услуга #${order.service_id} · ${order.created_at ? new Date(order.created_at).toLocaleString() : "—"}`}
      tabs={tabs}
      activeTab={activeTab}
      onTabChange={setActiveTab}
      maxWidth="w-full max-w-3xl sm:max-w-3xl"
      height="h-[580px]"
    >
      {activeTab === "info" && (
        <div className="space-y-6 text-sm">
          <div className="grid grid-cols-2 gap-4 rounded-xl border border-border/80 bg-card/60 p-4">
            <div>
              <p className="text-xs text-muted-foreground">Пользователь</p>
              <button
                type="button"
                onClick={() => {
                  onOpenChange(false)
                  openUserProfile(order.account_id)
                }}
                className="font-mono text-sm font-medium text-primary hover:underline cursor-pointer flex items-center gap-1.5 mt-0.5"
                title="Открыть профиль пользователя"
              >
                <UserRound className="size-3.5" />
                <span>#{order.account_id}</span>
              </button>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Услуга</p>
              <p className="font-mono text-sm font-medium mt-0.5">#{order.service_id}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Цена</p>
              <p className="text-sm font-semibold mt-0.5">
                {order.price ?? "—"} {symbol} {Number(order.discount) > 0 && <span className="text-xs text-muted-foreground font-normal">(скидка {order.discount} {symbol})</span>}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Статус</p>
              <div className="mt-0.5">
                <Badge variant={STATUS_VARIANT[order.status] ?? "outline"}>{order.status}</Badge>
              </div>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Дата создания</p>
              <p className="text-xs mt-0.5">{new Date(order.created_at).toLocaleString()}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Срок действия</p>
              <p className="text-xs mt-0.5">
                {order.expires_at ? new Date(order.expires_at).toLocaleString() : "бессрочно"}
              </p>
            </div>
          </div>

          {order.product_key && (
            <div className="rounded-xl border border-border/80 bg-card/60 p-4 space-y-1.5">
              <span className="text-xs text-muted-foreground font-medium">Выданный лицензионный ключ</span>
              <div className="flex items-center justify-between rounded-lg bg-muted/50 p-2 font-mono text-xs">
                <span className="select-all font-semibold">{order.product_key}</span>
              </div>
            </div>
          )}

          {order.error && (
            <div className="rounded-xl border border-destructive/50 bg-destructive/10 p-4 text-xs text-destructive">
              <span className="font-semibold">Ошибка выдачи:</span> {order.error}
            </div>
          )}
        </div>
      )}

      {activeTab === "delivery" && (
        <div className="space-y-4">
          <DataPropertySheet
            title="Публичные данные выдачи (public_data)"
            data={order.public_data}
            emptyText="Скрипт не передал публичных данных"
          />

          <DataPropertySheet
            title="Приватные данные выдачи (private_data, только админы)"
            data={order.private_data}
            emptyText="Приватных данных нет"
          />
        </div>
      )}
    </TabbedDialog>
  )
}

function GrantServiceDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const [activeTab, setActiveTab] = useState<string>("main")
  const [userPickerOpen, setUserPickerOpen] = useState(false)
  const [accountId, setAccountId] = useState<number | null>(null)
  const [accountLabel, setAccountLabel] = useState("")
  const [serviceId, setServiceId] = useState<string>("")
  const [charge, setCharge] = useState(false)
  const qc = useQueryClient()

  const { data: services } = useQuery({
    queryKey: ["admin-services-lookup"],
    queryFn: async () =>
      (await api.get<Page<Service>>("/v1/admin/services", { params: { limit: 200 } })).data.items,
    enabled: open,
    staleTime: 30_000,
  })

  const reset = () => {
    setAccountId(null)
    setAccountLabel("")
    setServiceId("")
    setCharge(false)
    setActiveTab("main")
  }

  const grant = useMutation({
    mutationFn: async () =>
      api.post("/v1/admin/orders/grant", {
        account_id: accountId,
        service_id: Number(serviceId),
        charge,
      }),
    onSuccess: () => {
      toastSuccess("Услуга выдана")
      onOpenChange(false)
      reset()
      void qc.invalidateQueries({ queryKey: ["admin-orders"] })
    },
    onError: (e: unknown) => toastError("Не удалось выдать услугу", getErrorDetail(e)),
  })

  const tabs = [{ id: "main", title: "Параметры", icon: Sparkles }]

  return (
    <>
      <TabbedDialog
        open={open}
        onOpenChange={(v) => {
          onOpenChange(v)
          if (!v) reset()
        }}
        title="Выдать услугу вручную"
        description="Создание заказа администратором напрямую для пользователя"
        tabs={tabs}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        maxWidth="max-w-2xl"
        height="h-[460px]"
        footer={
          <div className="flex items-center justify-end gap-2 w-full">
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Отмена
            </Button>
            <Button
              disabled={!accountId || !serviceId || grant.isPending}
              onClick={() => grant.mutate()}
            >
              Выдать услугу
            </Button>
          </div>
        }
      >
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>Пользователь</Label>
            <Button
              variant="outline"
              className="w-full justify-start text-sm"
              onClick={() => setUserPickerOpen(true)}
            >
              {accountLabel ? (
                <span className="font-medium text-foreground">{accountLabel}</span>
              ) : (
                <span className="text-muted-foreground">Выбрать пользователя…</span>
              )}
            </Button>
          </div>

          <div className="space-y-1.5">
            <Label>Услуга / Товар</Label>
            <Select value={serviceId} onValueChange={(v) => setServiceId(v ?? "")}>
              <SelectTrigger>
                <SelectValue placeholder="Выберите услугу" />
              </SelectTrigger>
              <SelectContent>
                {services?.map((s) => (
                  <SelectItem key={s.id} value={String(s.id)}>
                    {s.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex items-center justify-between rounded-xl border border-border/80 bg-card/60 p-3.5">
            <div>
              <Label className="text-sm font-medium">Списать с баланса</Label>
              <p className="text-xs text-muted-foreground mt-0.5">
                Иначе услуга выдаётся бесплатно (бонусом)
              </p>
            </div>
            <Switch checked={charge} onCheckedChange={setCharge} />
          </div>
        </div>
      </TabbedDialog>

      <UserPickerDialog
        open={userPickerOpen}
        onOpenChange={setUserPickerOpen}
        onSelect={(u) => {
          setAccountId(u.id)
          setAccountLabel(`${u.login} (#${u.id})`)
        }}
      />
    </>
  )
}

export function OrdersPage() {
  const { can } = useAuth()
  const { openUserProfile } = useProfileDialog()
  const { symbol } = useInstanceCurrency()
  const table = useDataTableQuery()
  const [detail, setDetail] = useState<Order | null>(null)
  const [granting, setGranting] = useState(false)
  const canGrant = can("orders.create")

  const { data, isLoading, isError } = useQuery({
    queryKey: ["admin-orders", table.limit, table.offset, table.sort, table.search],
    queryFn: async () =>
      (
        await api.get<Page<Order>>("/v1/admin/orders", {
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

  const columns: DataTableColumn<Order>[] = [
    { key: "id", header: "ID", render: (o) => <span className="font-mono text-xs">{o.id}</span> },
    {
      header: "Пользователь",
      render: (o) => (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation()
            openUserProfile(o.account_id)
          }}
          className="font-mono text-xs text-primary underline-offset-4 hover:underline cursor-pointer flex items-center gap-1 hover:text-primary/80"
          title={`Открыть профиль пользователя #${o.account_id}`}
        >
          #{o.account_id}
        </button>
      ),
    },
    { header: "Услуга", render: (o) => <span className="font-mono text-xs">#{o.service_id}</span> },
    {
      header: "Статус",
      render: (o) => <Badge variant={STATUS_VARIANT[o.status] ?? "outline"}>{o.status}</Badge>,
    },
    { key: "price", header: "Цена", render: (o) => (o.price ? `${o.price} ${symbol}` : "—") },
    {
      key: "created_at",
      header: "Создан",
      render: (o) => (o.created_at ? new Date(o.created_at).toLocaleString() : "—"),
    },
    {
      key: "expires_at",
      header: "Истекает",
      render: (o) => (o.expires_at ? new Date(o.expires_at).toLocaleDateString() : "бессрочно"),
    },
  ]

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <h1 className="text-xl font-semibold">Заказы</h1>
        {canGrant && (
          <Button size="sm" onClick={() => setGranting(true)}>
            <Plus className="size-4" /> Выдать услугу
          </Button>
        )}
      </div>

      <DataTable
        columns={columns}
        data={data?.items ?? []}
        total={data?.total ?? 0}
        isLoading={isLoading}
        isError={isError}
        getRowId={(o) => o.id}
        onRowClick={(o) => setDetail(o)}
        sort={table.sort}
        onToggleSort={table.toggleSort}
        searchValue={table.searchInput}
        onSearchChange={table.setSearchInput}
        searchPlaceholder="Поиск по ключу продукта…"
        emptyMessage="Заказов не найдено"
        emptyHint={table.search ? "Попробуйте изменить запрос." : "Здесь появятся выданные услуги."}
        limit={table.limit}
        offset={table.offset}
        hasMore={data?.has_more ?? false}
        onLimitChange={table.changeLimit}
        onOffsetChange={table.setOffset}
      />

      {detail && <OrderDetailDialog order={detail} onOpenChange={(v) => !v && setDetail(null)} />}
      <GrantServiceDialog open={granting} onOpenChange={setGranting} />
    </div>
  )
}
