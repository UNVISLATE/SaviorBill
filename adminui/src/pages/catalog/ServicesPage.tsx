import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "react-router-dom"
import { Plus } from "lucide-react"

import { api } from "@/api/api.ts"
import { useAuth } from "@/hooks/use-auth"
import { useDataTableQuery } from "@/hooks/use-data-table"
import { DataTable, type DataTableColumn } from "@/components/data-table/DataTable"
import { Badge } from "@/components/shadsnui/badge"
import { Button } from "@/components/shadsnui/button"
import { Input } from "@/components/shadsnui/input"
import { Label } from "@/components/shadsnui/label"
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

function errDetail(e: unknown): string | undefined {
  if (e && typeof e === "object" && "response" in e) {
    // @ts-expect-error — axios error shape
    const d = e.response?.data?.detail
    return typeof d === "string" ? d : undefined
  }
  return undefined
}

function CreateServiceDialog({
  open,
  onOpenChange,
  catalogs,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  catalogs: Catalog[] | undefined
}) {
  const [name, setName] = useState("")
  const [slug, setSlug] = useState("")
  const [catalogId, setCatalogId] = useState<string>("")
  const [price, setPrice] = useState("0")
  const [currency, setCurrency] = useState("RUB")
  const [delivery, setDelivery] = useState<"key" | "lua">("key")
  const qc = useQueryClient()
  const navigate = useNavigate()

  const reset = () => {
    setName("")
    setSlug("")
    setCatalogId("")
    setPrice("0")
    setCurrency("RUB")
    setDelivery("key")
  }

  const create = useMutation({
    mutationFn: async () =>
      api.post("/v1/admin/services", {
        name,
        slug,
        catalog_id: catalogId ? Number(catalogId) : null,
        price,
        currency,
        delivery,
      }),
    onSuccess: (res) => {
      toastSuccess(`Услуга «${name}» создана`)
      onOpenChange(false)
      reset()
      void qc.invalidateQueries({ queryKey: ["admin-services"] })
      const id = (res.data as { id: number }).id
      navigate(`/services/${id}`)
    },
    onError: (e: unknown) => toastError("Не удалось создать услугу", errDetail(e)),
  })

  return (
    <Dialog open={open} onOpenChange={(v) => { onOpenChange(v); if (!v) reset() }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Новая услуга</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1">
            <Label>Название</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} autoFocus />
          </div>
          <div className="space-y-1">
            <Label>Слаг</Label>
            <Input value={slug} onChange={(e) => setSlug(e.target.value)} placeholder="vpn-1-month" />
          </div>
          <div className="space-y-1">
            <Label>Каталог</Label>
            <Select value={catalogId || "root"} onValueChange={(v) => setCatalogId(v === "root" ? "" : v ?? "")}>
              <SelectTrigger>
                <SelectValue placeholder="Без каталога" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="root">— Без каталога —</SelectItem>
                {catalogs?.map((c) => (
                  <SelectItem key={c.id} value={String(c.id)}>
                    {c.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label>Цена</Label>
              <Input type="number" min={0} step="0.01" value={price} onChange={(e) => setPrice(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label>Валюта</Label>
              <Input value={currency} onChange={(e) => setCurrency(e.target.value.toUpperCase())} maxLength={8} />
            </div>
          </div>
          <div className="space-y-1">
            <Label>Способ выдачи</Label>
            <Select value={delivery} onValueChange={(v) => setDelivery((v as "key" | "lua") ?? "key")}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="key">Ключи из пула</SelectItem>
                <SelectItem value="lua">Lua-скрипт</SelectItem>
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Скрипт для delivery=lua и остальные параметры настраиваются после создания.
            </p>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Отмена
          </Button>
          <Button
            disabled={name.trim().length < 1 || slug.trim().length < 2 || create.isPending}
            onClick={() => create.mutate()}
          >
            Создать
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function ServicesPage() {
  const { can } = useAuth()
  const navigate = useNavigate()
  const table = useDataTableQuery()
  const [creating, setCreating] = useState(false)
  const canCreate = can("services.create")

  const { data: catalogs } = useQuery({
    queryKey: ["admin-catalogs"],
    queryFn: async () => (await api.get<Catalog[]>("/v1/admin/catalogs")).data,
    staleTime: 60_000,
  })
  const catalogName = (id: number | null) => catalogs?.find((c) => c.id === id)?.name

  const { data, isLoading, isError } = useQuery({
    queryKey: ["admin-services", table.limit, table.offset, table.sort, table.search],
    queryFn: async () =>
      (
        await api.get<Page<ServiceRow>>("/v1/admin/services", {
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

  const columns: DataTableColumn<ServiceRow>[] = [
    { key: "id", header: "ID", render: (s) => <span className="font-mono text-xs">{s.id}</span> },
    { key: "name", header: "Название", render: (s) => <span className="font-medium">{s.name}</span> },
    { header: "Каталог", render: (s) => catalogName(s.catalog_id) ?? "—" },
    {
      key: "price",
      header: "Цена",
      render: (s) => `${s.price} ${s.currency}`,
    },
    {
      header: "Выдача",
      render: (s) => <Badge variant="outline">{s.delivery === "lua" ? "Lua" : "Ключи"}</Badge>,
    },
    {
      header: "Статус",
      render: (s) => {
        if (!s.is_active) return <Badge variant="destructive">неактивна</Badge>
        if (s.out_of_stock) return <Badge variant="destructive">нет в наличии</Badge>
        return <Badge variant="outline">активна</Badge>
      },
    },
  ]

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <h1 className="text-xl font-semibold">Услуги</h1>
        {canCreate && (
          <Button size="sm" onClick={() => setCreating(true)}>
            <Plus className="size-4" /> Создать
          </Button>
        )}
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
      />

      <CreateServiceDialog open={creating} onOpenChange={setCreating} catalogs={catalogs} />
    </div>
  )
}
