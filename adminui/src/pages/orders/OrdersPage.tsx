import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Plus } from "lucide-react"

import { api } from "@/api/api.ts"
import { getErrorDetail } from "@/lib/api-error.ts"
import { useAuth } from "@/hooks/use-auth"
import { useDataTableQuery } from "@/hooks/use-data-table"
import { DataTable, type DataTableColumn } from "@/components/data-table/DataTable"
import { UserPickerDialog } from "@/components/users/UserPickerDialog"
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
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/shadsnui/dialog"
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
  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Заказ #{order.id}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 text-sm">
          <div className="grid grid-cols-2 gap-2">
            <div>
              <p className="text-xs text-muted-foreground">Пользователь</p>
              <p className="font-mono">#{order.account_id}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Услуга</p>
              <p className="font-mono">#{order.service_id}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Цена</p>
              <p>{order.price} (скидка {order.discount})</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Статус</p>
              <Badge variant={STATUS_VARIANT[order.status] ?? "outline"}>{order.status}</Badge>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Создан</p>
              <p>{new Date(order.created_at).toLocaleString()}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Истекает</p>
              <p>{order.expires_at ? new Date(order.expires_at).toLocaleString() : "бессрочно"}</p>
            </div>
          </div>
          {order.error && <p className="text-destructive">Ошибка выдачи: {order.error}</p>}
          <div>
            <p className="mb-1 text-xs text-muted-foreground">public_data</p>
            <pre className="max-h-32 overflow-auto rounded-md bg-muted p-2 text-xs">
              {JSON.stringify(order.public_data, null, 2)}
            </pre>
          </div>
          <div>
            <p className="mb-1 text-xs text-muted-foreground">private_data (только для админов)</p>
            <pre className="max-h-32 overflow-auto rounded-md bg-muted p-2 text-xs">
              {JSON.stringify(order.private_data, null, 2)}
            </pre>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function GrantServiceDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
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

  return (
    <Dialog open={open} onOpenChange={(v) => { onOpenChange(v); if (!v) reset() }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Выдать услугу вручную</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1">
            <Label>Пользователь</Label>
            <Button variant="outline" className="w-full justify-start" onClick={() => setUserPickerOpen(true)}>
              {accountLabel || "Выбрать пользователя…"}
            </Button>
          </div>
          <div className="space-y-1">
            <Label>Услуга</Label>
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
          <div className="flex items-center justify-between">
            <div>
              <Label>Списать с баланса</Label>
              <p className="text-xs text-muted-foreground">Иначе услуга выдаётся бесплатно (бонусом)</p>
            </div>
            <Switch checked={charge} onCheckedChange={setCharge} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Отмена
          </Button>
          <Button disabled={!accountId || !serviceId || grant.isPending} onClick={() => grant.mutate()}>
            Выдать
          </Button>
        </DialogFooter>
        <UserPickerDialog
          open={userPickerOpen}
          onOpenChange={setUserPickerOpen}
          onSelect={(u) => {
            setAccountId(u.id)
            setAccountLabel(`${u.login} (#${u.id})`)
          }}
        />
      </DialogContent>
    </Dialog>
  )
}

export function OrdersPage() {
  const { can } = useAuth()
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
    { header: "Пользователь", render: (o) => <span className="font-mono text-xs">#{o.account_id}</span> },
    { header: "Услуга", render: (o) => <span className="font-mono text-xs">#{o.service_id}</span> },
    {
      header: "Статус",
      render: (o) => <Badge variant={STATUS_VARIANT[o.status] ?? "outline"}>{o.status}</Badge>,
    },
    { key: "price", header: "Цена", render: (o) => o.price },
    {
      key: "created_at",
      header: "Создан",
      render: (o) => new Date(o.created_at).toLocaleString(),
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
