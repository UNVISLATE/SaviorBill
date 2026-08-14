import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { RefreshCw, Undo2 } from "lucide-react"

import { api } from "@/api/api.ts"
import { getErrorDetail } from "@/lib/api-error.ts"
import { useAuth } from "@/hooks/use-auth"
import { useDataTableQuery } from "@/hooks/use-data-table"
import { DataTable, type DataTableColumn } from "@/components/data-table/DataTable"
import { Badge } from "@/components/shadsnui/badge"
import { Button } from "@/components/shadsnui/button"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/shadsnui/dialog"
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
    onError: (e: unknown) => toastError("Не удалось проверить платёж", getErrorDetail(e)),
  })

  const refund = useMutation({
    mutationFn: async () => api.post(`/v1/admin/purchases/${payment.id}/refund`),
    onSuccess: () => {
      toastSuccess("Возврат оформлен")
      void qc.invalidateQueries({ queryKey: ["admin-payments"] })
      onOpenChange(false)
    },
    onError: (e: unknown) => toastError("Не удалось оформить возврат", getErrorDetail(e)),
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

/** Провайдеры настраиваются реже, чем просматриваются платежи — вынесены
 * в «Настройки → Платёжные провайдеры» (см. PaymentProvidersSettings.tsx). */
export function PurchasesPage() {
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
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Платежи</h1>
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
    </div>
  )
}
