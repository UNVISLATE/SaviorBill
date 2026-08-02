import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { MoreHorizontal, Plus, Ticket, Trash2 } from "lucide-react"

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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/shadsnui/select"
import { Card, CardContent } from "@/components/shadsnui/card"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/shadsnui/dialog"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/shadsnui/alert-dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/shadsnui/dropdown-menu"
import { toastError, toastSuccess } from "@/lib/toast"

interface Catalog {
  id: number
  name: string
  slug: string
  kind: "bonus" | "discount" | "service"
  value: string
  discount_type: "percent" | "fixed" | null
  service_id: number | null
  per_user: number | null
  is_active: boolean
}

interface Service {
  id: number
  name: string
}

interface Code {
  id: number
  code: string
  catalog_id: number
  max_uses: number | null
  used_count: number
  valid_to: string | null
  is_active: boolean
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

const KIND_LABEL: Record<Catalog["kind"], string> = {
  bonus: "Бонус на баланс",
  discount: "Скидка",
  service: "Выдача услуги",
}

function CatalogFormDialog({
  open,
  onOpenChange,
  catalog,
  services,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  catalog: Catalog | null
  services: Service[] | undefined
}) {
  const isEdit = !!catalog
  const [name, setName] = useState(catalog?.name ?? "")
  const [slug, setSlug] = useState(catalog?.slug ?? "")
  const [kind, setKind] = useState<Catalog["kind"]>(catalog?.kind ?? "bonus")
  const [value, setValue] = useState(catalog?.value ?? "0")
  const [discountType, setDiscountType] = useState<"percent" | "fixed">(catalog?.discount_type ?? "percent")
  const [serviceId, setServiceId] = useState(catalog?.service_id ? String(catalog.service_id) : "")
  const [perUser, setPerUser] = useState(catalog?.per_user ? String(catalog.per_user) : "")
  const [isActive, setIsActive] = useState(catalog?.is_active ?? true)
  const qc = useQueryClient()

  const save = useMutation({
    mutationFn: async () => {
      const body = {
        name,
        kind,
        value,
        discount_type: kind === "discount" ? discountType : null,
        service_id: kind === "service" ? (serviceId ? Number(serviceId) : null) : null,
        per_user: perUser ? Number(perUser) : null,
        is_active: isActive,
      }
      if (isEdit) return api.patch(`/v1/admin/promo/catalogs/${catalog!.id}`, body)
      return api.post("/v1/admin/promo/catalogs", { ...body, slug })
    },
    onSuccess: () => {
      toastSuccess(isEdit ? "Каталог обновлён" : "Каталог создан")
      onOpenChange(false)
      void qc.invalidateQueries({ queryKey: ["admin-promo-catalogs"] })
    },
    onError: (e: unknown) => toastError(isEdit ? "Не удалось обновить каталог" : "Не удалось создать каталог", errDetail(e)),
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEdit ? "Изменить каталог промокодов" : "Новый каталог промокодов"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1">
            <Label>Название</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} autoFocus />
          </div>
          {!isEdit && (
            <div className="space-y-1">
              <Label>Слаг</Label>
              <Input value={slug} onChange={(e) => setSlug(e.target.value)} placeholder="new-year-2025" />
            </div>
          )}
          <div className="space-y-1">
            <Label>Тип действия</Label>
            <Select value={kind} onValueChange={(v) => setKind((v as Catalog["kind"]) ?? "bonus")}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="bonus">Бонус на баланс</SelectItem>
                <SelectItem value="discount">Скидка на услугу</SelectItem>
                <SelectItem value="service">Выдача услуги</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {kind !== "service" && (
            <div className="space-y-1">
              <Label>{kind === "bonus" ? "Сумма бонуса" : "Размер скидки"}</Label>
              <Input type="number" min={0} step="0.01" value={value} onChange={(e) => setValue(e.target.value)} />
            </div>
          )}
          {kind === "discount" && (
            <div className="space-y-1">
              <Label>Тип скидки</Label>
              <Select value={discountType} onValueChange={(v) => setDiscountType((v as "percent" | "fixed") ?? "percent")}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="percent">Процент от цены</SelectItem>
                  <SelectItem value="fixed">Фиксированная сумма</SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}
          {kind === "service" && (
            <div className="space-y-1">
              <Label>Услуга для выдачи</Label>
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
          )}
          <div className="space-y-1">
            <Label>Лимит разных кодов каталога на пользователя</Label>
            <Input
              type="number"
              min={1}
              value={perUser}
              onChange={(e) => setPerUser(e.target.value)}
              placeholder="без лимита"
            />
          </div>
          <div className="flex items-center justify-between">
            <Label>Активен</Label>
            <Switch checked={isActive} onCheckedChange={setIsActive} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Отмена
          </Button>
          <Button
            disabled={name.trim().length < 1 || (!isEdit && slug.trim().length < 2) || save.isPending}
            onClick={() => save.mutate()}
          >
            {isEdit ? "Сохранить" : "Создать"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function DeleteCatalogDialog({
  catalog,
  open,
  onOpenChange,
}: {
  catalog: Catalog
  open: boolean
  onOpenChange: (v: boolean) => void
}) {
  const qc = useQueryClient()
  const del = useMutation({
    mutationFn: async () => api.delete(`/v1/admin/promo/catalogs/${catalog.id}`),
    onSuccess: () => {
      toastSuccess(`Каталог «${catalog.name}» удалён`)
      onOpenChange(false)
      void qc.invalidateQueries({ queryKey: ["admin-promo-catalogs"] })
    },
    onError: (e: unknown) => toastError("Не удалось удалить каталог", errDetail(e)),
  })

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Удалить каталог «{catalog.name}»?</AlertDialogTitle>
          <AlertDialogDescription>Все коды каталога удалятся вместе с ним.</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Отмена</AlertDialogCancel>
          <AlertDialogAction
            disabled={del.isPending}
            onClick={() => del.mutate()}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            Удалить
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

function IssueCodesDialog({
  open,
  onOpenChange,
  catalogId,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  catalogId: number
}) {
  const [mode, setMode] = useState<"generate" | "explicit">("generate")
  const [count, setCount] = useState("10")
  const [prefix, setPrefix] = useState("")
  const [explicitCodes, setExplicitCodes] = useState("")
  const [maxUses, setMaxUses] = useState("1")
  const [validTo, setValidTo] = useState("")
  const qc = useQueryClient()

  const issue = useMutation({
    mutationFn: async () =>
      api.post("/v1/admin/promo/codes", {
        catalog_id: catalogId,
        codes: mode === "explicit" ? explicitCodes.split("\n").map((c) => c.trim()).filter(Boolean) : null,
        count: mode === "generate" ? Number(count) || 0 : 0,
        prefix,
        max_uses: maxUses ? Number(maxUses) : null,
        valid_to: validTo ? new Date(validTo).toISOString() : null,
      }),
    onSuccess: (res) => {
      const n = (res.data as unknown[]).length
      toastSuccess(`Выпущено кодов: ${n}`)
      onOpenChange(false)
      void qc.invalidateQueries({ queryKey: ["admin-promo-codes", catalogId] })
    },
    onError: (e: unknown) => toastError("Не удалось выпустить коды", errDetail(e)),
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Выпустить промокоды</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1">
            <Label>Способ</Label>
            <Select value={mode} onValueChange={(v) => setMode((v as "generate" | "explicit") ?? "generate")}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="generate">Сгенерировать случайные</SelectItem>
                <SelectItem value="explicit">Указать вручную</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {mode === "generate" ? (
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>Количество</Label>
                <Input type="number" min={1} max={10000} value={count} onChange={(e) => setCount(e.target.value)} />
              </div>
              <div className="space-y-1">
                <Label>Префикс</Label>
                <Input value={prefix} onChange={(e) => setPrefix(e.target.value)} maxLength={16} placeholder="NY2025" />
              </div>
            </div>
          ) : (
            <div className="space-y-1">
              <Label>Коды (по одному на строку)</Label>
              <Textarea
                className="font-mono text-xs"
                rows={5}
                value={explicitCodes}
                onChange={(e) => setExplicitCodes(e.target.value)}
              />
            </div>
          )}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label>Лимит активаций</Label>
              <Input type="number" min={1} value={maxUses} onChange={(e) => setMaxUses(e.target.value)} placeholder="без лимита" />
            </div>
            <div className="space-y-1">
              <Label>Действует до</Label>
              <Input type="date" value={validTo} onChange={(e) => setValidTo(e.target.value)} />
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Отмена
          </Button>
          <Button disabled={issue.isPending} onClick={() => issue.mutate()}>
            Выпустить
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function CatalogCodesPanel({ catalog }: { catalog: Catalog }) {
  const { can } = useAuth()
  const table = useDataTableQuery()
  const [issuing, setIssuing] = useState(false)
  const canCreate = can("promo.codes.create")
  const canEdit = can("promo.codes.edit")
  const qc = useQueryClient()

  const { data, isLoading, isError } = useQuery({
    queryKey: ["admin-promo-codes", catalog.id, table.limit, table.offset, table.sort, table.search],
    queryFn: async () =>
      (
        await api.get<Page<Code>>(`/v1/admin/promo/catalogs/${catalog.id}/codes`, {
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

  const toggle = useMutation({
    mutationFn: async (vars: { id: number; is_active: boolean }) =>
      api.patch(`/v1/admin/promo/codes/${vars.id}`, { is_active: vars.is_active }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["admin-promo-codes", catalog.id] }),
    onError: (e: unknown) => toastError("Не удалось изменить код", errDetail(e)),
  })

  const columns: DataTableColumn<Code>[] = [
    { key: "code", header: "Код", render: (c) => <span className="font-mono text-xs">{c.code}</span> },
    {
      header: "Активаций",
      render: (c) => `${c.used_count}${c.max_uses ? ` / ${c.max_uses}` : ""}`,
    },
    {
      header: "Срок",
      render: (c) => (c.valid_to ? new Date(c.valid_to).toLocaleDateString() : "бессрочно"),
    },
    {
      header: "Статус",
      render: (c) => <Badge variant={c.is_active ? "default" : "outline"}>{c.is_active ? "активен" : "выключен"}</Badge>,
    },
    ...(canEdit
      ? [
          {
            header: "",
            render: (c: Code) => (
              <Switch
                checked={c.is_active}
                onCheckedChange={(v) => toggle.mutate({ id: c.id, is_active: v })}
                onClick={(e) => e.stopPropagation()}
              />
            ),
          } satisfies DataTableColumn<Code>,
        ]
      : []),
  ]

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        {canCreate && (
          <Button size="sm" onClick={() => setIssuing(true)}>
            <Plus className="size-4" /> Выпустить коды
          </Button>
        )}
      </div>
      <DataTable
        columns={columns}
        data={data?.items ?? []}
        total={data?.total ?? 0}
        isLoading={isLoading}
        isError={isError}
        getRowId={(c) => c.id}
        sort={table.sort}
        onToggleSort={table.toggleSort}
        searchValue={table.searchInput}
        onSearchChange={table.setSearchInput}
        searchPlaceholder="Поиск по началу кода…"
        emptyMessage="Кодов пока нет"
        emptyHint="Выпустите первую пачку кодов для этого каталога."
        limit={table.limit}
        offset={table.offset}
        hasMore={data?.has_more ?? false}
        onLimitChange={table.changeLimit}
        onOffsetChange={table.setOffset}
      />
      <IssueCodesDialog open={issuing} onOpenChange={setIssuing} catalogId={catalog.id} />
    </div>
  )
}

export function PromoPage() {
  const { can } = useAuth()
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<Catalog | null>(null)
  const [deleting, setDeleting] = useState<Catalog | null>(null)
  const [expanded, setExpanded] = useState<number | null>(null)

  const canCreate = can("promo.catalogs.create")
  const canEdit = can("promo.catalogs.edit")
  const canDelete = can("promo.catalogs.delete")

  const { data: catalogs, isLoading } = useQuery({
    queryKey: ["admin-promo-catalogs"],
    queryFn: async () => (await api.get<Catalog[]>("/v1/admin/promo/catalogs")).data,
  })

  const { data: services } = useQuery({
    queryKey: ["admin-services-lookup"],
    queryFn: async () => (await api.get<Page<Service>>("/v1/admin/services", { params: { limit: 200 } })).data.items,
    staleTime: 30_000,
  })

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <h1 className="text-xl font-semibold">Промокоды</h1>
        {canCreate && (
          <Button size="sm" onClick={() => setCreating(true)}>
            <Plus className="size-4" /> Новый каталог
          </Button>
        )}
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Загрузка…</p>}
      {!isLoading && (catalogs?.length ?? 0) === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-2 py-10 text-center text-sm text-muted-foreground">
            <Ticket className="size-6" />
            Каталогов промокодов пока нет.
          </CardContent>
        </Card>
      )}

      <div className="grid gap-2">
        {catalogs?.map((c) => (
          <Card key={c.id}>
            <CardContent
              className="flex cursor-pointer items-center justify-between gap-3 py-3"
              onClick={() => setExpanded(expanded === c.id ? null : c.id)}
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="truncate font-medium">{c.name}</span>
                  <span className="font-mono text-xs text-muted-foreground">{c.slug}</span>
                  {!c.is_active && <Badge variant="destructive">неактивен</Badge>}
                </div>
                <div className="mt-0.5 text-xs text-muted-foreground">
                  {KIND_LABEL[c.kind]}
                  {c.kind === "bonus" && ` · +${c.value}`}
                  {c.kind === "discount" && ` · ${c.value}${c.discount_type === "percent" ? "%" : ""}`}
                  {c.per_user ? ` · лимит ${c.per_user} на пользователя` : ""}
                </div>
              </div>
              {(canEdit || canDelete) && (
                <DropdownMenu>
                  <DropdownMenuTrigger
                    render={
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-8 shrink-0"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <MoreHorizontal className="size-4" />
                      </Button>
                    }
                  />
                  <DropdownMenuContent align="end" onClick={(e) => e.stopPropagation()}>
                    {canEdit && <DropdownMenuItem onClick={() => setEditing(c)}>Изменить</DropdownMenuItem>}
                    {canDelete && (
                      <DropdownMenuItem variant="destructive" onClick={() => setDeleting(c)}>
                        <Trash2 className="size-4" /> Удалить
                      </DropdownMenuItem>
                    )}
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
            </CardContent>
            {expanded === c.id && (
              <CardContent className="border-t pt-3">
                <CatalogCodesPanel catalog={c} />
              </CardContent>
            )}
          </Card>
        ))}
      </div>

      <CatalogFormDialog open={creating} onOpenChange={setCreating} catalog={null} services={services} />
      {editing && (
        <CatalogFormDialog
          open={!!editing}
          onOpenChange={(v) => !v && setEditing(null)}
          catalog={editing}
          services={services}
        />
      )}
      {deleting && (
        <DeleteCatalogDialog catalog={deleting} open={!!deleting} onOpenChange={(v) => !v && setDeleting(null)} />
      )}
    </div>
  )
}
