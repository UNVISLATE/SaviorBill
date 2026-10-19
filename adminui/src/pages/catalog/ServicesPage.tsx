import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { useNavigate } from "react-router-dom"
import { Edit2, KeyRound, Package, Plus } from "lucide-react"

import { api } from "@/api/api.ts"
import { useAuth } from "@/hooks/use-auth"
import { useDataTableQuery } from "@/hooks/use-data-table"
import { DataTable, type DataTableColumn } from "@/components/data-table/DataTable"
import { Badge } from "@/components/shadsnui/badge"
import { Button } from "@/components/shadsnui/button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/shadsnui/select"

interface Catalog {
  id: number
  name: string
}

interface ServiceRow {
  id: number
  slug: string
  name: string
  catalog_id: number | null
  price: string
  currency: string
  delivery: string
  is_active: boolean
  out_of_stock: boolean | null
}

interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
  has_more: boolean
}

export function ServicesPage() {
  const { can } = useAuth()
  const navigate = useNavigate()
  const table = useDataTableQuery()
  const [catalogFilter, setCatalogFilter] = useState("")
  const canCreate = can("services.create")

  const { data: catalogs } = useQuery({
    queryKey: ["admin-catalogs"],
    queryFn: async () => (await api.get<Catalog[]>("/v1/admin/catalogs")).data,
    staleTime: 60_000,
  })
  const catalogName = (id: number | null) => catalogs?.find((c) => c.id === id)?.name

  const { data, isLoading, isError } = useQuery({
    queryKey: ["admin-services", table.limit, table.offset, table.sort, table.search, catalogFilter],
    queryFn: async () =>
      (
        await api.get<Page<ServiceRow>>("/v1/admin/services", {
          params: {
            limit: table.limit,
            offset: table.offset,
            sort: table.sort ?? undefined,
            q: table.search || undefined,
            catalog_id: catalogFilter || undefined,
          },
        })
      ).data,
    placeholderData: (prev) => prev,
  })

  const columns: DataTableColumn<ServiceRow>[] = [
    {
      key: "id",
      header: "ID",
      render: (s) => <span className="font-mono text-xs text-muted-foreground">#{s.id}</span>,
    },
    {
      key: "name",
      header: "Товар / Услуга",
      render: (s) => (
        <div className="flex flex-col">
          <span className="font-semibold text-foreground hover:text-primary transition-colors">
            {s.name}
          </span>
          <span className="font-mono text-[11px] text-muted-foreground">
            {s.slug}
          </span>
        </div>
      ),
    },
    {
      key: "catalog_id",
      header: "Категория",
      render: (s) => (
        <span className="text-xs text-muted-foreground">
          {catalogName(s.catalog_id) ?? "—"}
        </span>
      ),
    },
    {
      key: "price",
      header: "Цена",
      render: (s) => (
        <span className="font-mono text-xs font-semibold">
          {s.price} {s.currency}
        </span>
      ),
    },
    {
      header: "Выдача",
      render: (s) => (
        <Badge variant="outline" className="text-[10px] gap-1 font-normal">
          {s.delivery === "lua" ? (
            <>
              <span className="size-1.5 rounded-full bg-blue-500" /> Lua
            </>
          ) : (
            <>
              <span className="size-1.5 rounded-full bg-purple-500" /> Ключи
            </>
          )}
        </Badge>
      ),
    },
    {
      header: "Статус",
      render: (s) => {
        if (!s.is_active) {
          return (
            <Badge variant="outline" className="text-[10px] text-muted-foreground border-border/80">
              неактивна
            </Badge>
          )
        }
        if (s.out_of_stock) {
          return (
            <Badge variant="destructive" className="text-[10px] gap-1">
              <span className="size-1.5 rounded-full bg-red-400" /> нет ключей
            </Badge>
          )
        }
        return (
          <Badge variant="outline" className="text-[10px] gap-1 border-emerald-500/40 text-emerald-500 bg-emerald-500/10">
            <span className="size-1.5 rounded-full bg-emerald-500" /> активна
          </Badge>
        )
      },
    },
    {
      header: "",
      className: "text-right",
      render: (s) => (
        <div className="flex items-center justify-end gap-1" onClick={(e) => e.stopPropagation()}>
          {s.delivery === "key" && (
            <Button
              variant="ghost"
              size="icon"
              className="size-8"
              title="Инвентарь ключей"
              onClick={() => navigate(`/service-keys?service_id=${s.id}&tab=keys`)}
            >
              <KeyRound className="size-3.5 text-muted-foreground" />
            </Button>
          )}
          <Button
            variant="ghost"
            size="icon"
            className="size-8"
            title="Редактировать товар"
            onClick={() => navigate(`/services/${s.id}`)}
          >
            <Edit2 className="size-3.5 text-muted-foreground" />
          </Button>
        </div>
      ),
    },
  ]

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-2">
            <Package className="size-6 text-primary" /> Каталог услуг
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Управление цифровыми товарами, тарифами и способами автоматической выдачи.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate("/service-keys")}
            className="gap-1.5"
          >
            <KeyRound className="size-4 text-primary" /> Инвентарь ключей
          </Button>

          {canCreate && (
            <Button size="sm" onClick={() => navigate("/services/new")} className="gap-1.5 shadow-xs">
              <Plus className="size-4" /> Создать услугу
            </Button>
          )}
        </div>
      </div>

      <DataTable
        columns={columns}
        data={data?.items ?? []}
        total={data?.total ?? 0}
        isLoading={isLoading}
        isError={isError}
        getRowId={(s) => s.id}
        onRowClick={(s) => navigate(`/services/${s.id}`)}
        sort={table.sort}
        onToggleSort={table.toggleSort}
        searchValue={table.searchInput}
        onSearchChange={table.setSearchInput}
        searchPlaceholder="Поиск по названию/описанию…"
        emptyMessage="Услуги не найдены"
        emptyHint={table.search ? "Попробуйте изменить запрос." : "Создайте первую услугу каталога."}
        limit={table.limit}
        offset={table.offset}
        hasMore={data?.has_more ?? false}
        onLimitChange={table.changeLimit}
        onOffsetChange={table.setOffset}
        toolbarExtra={
          <Select
            value={catalogFilter || "all"}
            onValueChange={(v) => setCatalogFilter(v === "all" ? "" : (v ?? ""))}
          >
            <SelectTrigger className="w-48 h-8 text-xs">
              <SelectValue placeholder="Все категории" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Все категории</SelectItem>
              {catalogs?.map((c) => (
                <SelectItem key={c.id} value={String(c.id)}>
                  {c.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        }
      />
    </div>
  )
}
