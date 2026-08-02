import { useState } from "react"
import { useQuery } from "@tanstack/react-query"

import { api } from "@/api/api.ts"
import { useDataTableQuery } from "@/hooks/use-data-table"
import { DataTable, type DataTableColumn } from "@/components/data-table/DataTable"
import { Badge } from "@/components/shadsnui/badge"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/shadsnui/dialog"

interface AuditEntry {
  id: number
  ts: string
  actor_account_id: number | null
  actor_role: string | null
  action: string
  target_type: string | null
  target_id: string | null
  ip: string | null
  meta: Record<string, unknown>
  result: string
}

interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
  has_more: boolean
}

const columns: DataTableColumn<AuditEntry>[] = [
  { key: "id", header: "ID", render: (e) => e.id },
  {
    key: "ts",
    header: "Время",
    render: (e) => new Date(e.ts).toLocaleString(),
  },
  {
    header: "Актор",
    render: (e) =>
      e.actor_account_id != null ? (
        <span>
          #{e.actor_account_id}
          {e.actor_role && <span className="text-muted-foreground"> · {e.actor_role}</span>}
        </span>
      ) : (
        <span className="text-muted-foreground">система</span>
      ),
  },
  { key: "action", header: "Действие", render: (e) => <span className="font-medium">{e.action}</span> },
  {
    header: "Цель",
    render: (e) =>
      e.target_type ? (
        <span>
          {e.target_type}
          {e.target_id && <span className="text-muted-foreground"> #{e.target_id}</span>}
        </span>
      ) : (
        "—"
      ),
  },
  {
    header: "Результат",
    render: (e) => (
      <Badge variant={e.result === "ok" ? "outline" : "destructive"}>{e.result}</Badge>
    ),
  },
  { header: "IP", render: (e) => e.ip ?? "—" },
]

export function AuditPage() {
  const table = useDataTableQuery()
  const [detail, setDetail] = useState<AuditEntry | null>(null)

  const { data, isLoading, isError } = useQuery({
    queryKey: ["admin-audit", table.limit, table.offset, table.sort, table.search],
    queryFn: async () =>
      (
        await api.get<Page<AuditEntry>>("/v1/admin/audit", {
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

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <h1 className="text-xl font-semibold">Аудит</h1>
        {data && <span className="text-sm text-muted-foreground">Всего: {data.total}</span>}
      </div>

      <DataTable
        columns={columns}
        data={data?.items ?? []}
        total={data?.total ?? 0}
        isLoading={isLoading}
        isError={isError}
        getRowId={(e) => e.id}
        onRowClick={setDetail}
        sort={table.sort}
        onToggleSort={table.toggleSort}
        searchValue={table.searchInput}
        onSearchChange={table.setSearchInput}
        searchPlaceholder="Поиск по действию/цели…"
        limit={table.limit}
        offset={table.offset}
        hasMore={data?.has_more ?? false}
        onLimitChange={table.changeLimit}
        onOffsetChange={table.setOffset}
      />

      <Dialog open={!!detail} onOpenChange={(open) => !open && setDetail(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Запись аудита #{detail?.id}</DialogTitle>
          </DialogHeader>
          {detail && (
            <div className="space-y-3 text-sm">
              <dl className="grid grid-cols-[8rem_1fr] gap-y-1.5">
                <dt className="text-muted-foreground">Время</dt>
                <dd>{new Date(detail.ts).toLocaleString()}</dd>
                <dt className="text-muted-foreground">Актор</dt>
                <dd>
                  {detail.actor_account_id != null ? (
                    <>
                      #{detail.actor_account_id}
                      {detail.actor_role && <span className="text-muted-foreground"> · {detail.actor_role}</span>}
                    </>
                  ) : (
                    <span className="text-muted-foreground">система</span>
                  )}
                </dd>
                <dt className="text-muted-foreground">Действие</dt>
                <dd className="font-medium">{detail.action}</dd>
                <dt className="text-muted-foreground">Цель</dt>
                <dd>
                  {detail.target_type ? (
                    <>
                      {detail.target_type}
                      {detail.target_id && <span className="text-muted-foreground"> #{detail.target_id}</span>}
                    </>
                  ) : (
                    "—"
                  )}
                </dd>
                <dt className="text-muted-foreground">Результат</dt>
                <dd>
                  <Badge variant={detail.result === "ok" ? "outline" : "destructive"}>{detail.result}</Badge>
                </dd>
                <dt className="text-muted-foreground">IP</dt>
                <dd>{detail.ip ?? "—"}</dd>
              </dl>
              <div className="space-y-1.5">
                <p className="text-xs font-medium text-muted-foreground">
                  Технические детали (meta)
                </p>
                {Object.keys(detail.meta).length > 0 ? (
                  <pre className="max-h-72 overflow-auto rounded-md border bg-muted/40 p-3 text-xs">
                    {JSON.stringify(detail.meta, null, 2)}
                  </pre>
                ) : (
                  <p className="text-xs text-muted-foreground">пусто</p>
                )}
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
