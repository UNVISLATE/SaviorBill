import { useState, useEffect } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Gift, MoreHorizontal, Plus, Ticket, Trash2 } from "lucide-react"

import { api } from "@/api/api.ts"
import { getErrorDetail } from "@/lib/api-error.ts"
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
import { TabbedDialog, type TabDefinition } from "@/components/common/TabbedDialog"
import { useInstanceCurrency } from "@/lib/currency"
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
  const { symbol: currencySymbol } = useInstanceCurrency()
  const [name, setName] = useState("")
  const [slug, setSlug] = useState("")
  const [kind, setKind] = useState<Catalog["kind"]>("bonus")
  const [value, setValue] = useState("0")
  const [discountType, setDiscountType] = useState<"percent" | "fixed">("percent")
  const [serviceId, setServiceId] = useState("")
  const [perUser, setPerUser] = useState("")
  const [isActive, setIsActive] = useState(true)
  const qc = useQueryClient()

  useEffect(() => {
    if (open) {
      setName(catalog?.name ?? "")
      setSlug(catalog?.slug ?? "")
      setKind(catalog?.kind ?? "bonus")
      setValue(catalog?.value ?? "0")
      setDiscountType(catalog?.discount_type ?? "percent")
      setServiceId(catalog?.service_id ? String(catalog.service_id) : "")
      setPerUser(catalog?.per_user ? String(catalog.per_user) : "")
      setIsActive(catalog?.is_active ?? true)
    }
  }, [open, catalog])

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
    onError: (e: unknown) => toastError(isEdit ? "Не удалось обновить каталог" : "Не удалось создать каталог", getErrorDetail(e)),
  })

  const tabs: TabDefinition[] = [
    {
      id: "general",
      label: "Параметры кампании",
      icon: Gift,
      content: (
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label className="text-xs">Название каталога промокодов</Label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Новогодняя акция 2025"
              className="text-xs"
              autoFocus
            />
          </div>

          {!isEdit && (
            <div className="space-y-1.5">
              <Label className="text-xs">Слаг каталога (уникальный ключ)</Label>
              <Input
                value={slug}
                onChange={(e) => setSlug(e.target.value)}
                placeholder="new-year-2025"
                className="font-mono text-xs"
              />
            </div>
          )}

          <div className="space-y-1.5">
            <Label className="text-xs">Тип действия промокода</Label>
            <Select value={kind} onValueChange={(v) => setKind((v as Catalog["kind"]) ?? "bonus")}>
              <SelectTrigger className="text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="bonus">Бонус на баланс аккаунта</SelectItem>
                <SelectItem value="discount">Скидка на заказ</SelectItem>
                <SelectItem value="service">Прямая выдача услуги</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {kind !== "service" && (
            <div className="space-y-1.5">
              <Label className="text-xs">{kind === "bonus" ? "Сумма начисляемого бонуса" : "Размер скидки"}</Label>
              <Input
                type="number"
                min={0}
                step="0.01"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                className="font-mono text-xs"
              />
            </div>
          )}

          {kind === "discount" && (
            <div className="space-y-1.5">
              <Label className="text-xs">Тип расчёта скидки</Label>
              <Select value={discountType} onValueChange={(v) => setDiscountType((v as "percent" | "fixed") ?? "percent")}>
                <SelectTrigger className="text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="percent">Процент от стоимости (%)</SelectItem>
                  <SelectItem value="fixed">Фиксированная сумма ({currencySymbol})</SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}

          {kind === "service" && (
            <div className="space-y-1.5">
              <Label className="text-xs">Услуга для выдачи</Label>
              <Select value={serviceId} onValueChange={(v) => setServiceId(v ?? "")}>
                <SelectTrigger className="text-xs">
                  <SelectValue placeholder="Выберите выдаваемую услугу" />
                </SelectTrigger>
                <SelectContent>
                  {services?.map((s) => (
                    <SelectItem key={s.id} value={String(s.id)} className="text-xs">
                      {s.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          <div className="space-y-1.5">
            <Label className="text-xs">Лимит активаций разных кодов на одного пользователя</Label>
            <Input
              type="number"
              min={1}
              value={perUser}
              onChange={(e) => setPerUser(e.target.value)}
              placeholder="без лимита"
              className="text-xs font-mono"
            />
          </div>

          <div className="flex h-9 items-center justify-between rounded-md border border-input bg-background px-3 py-1">
            <span className="text-xs text-muted-foreground">{isActive ? "Активен" : "Отключен"}</span>
            <Switch checked={isActive} onCheckedChange={setIsActive} />
          </div>
        </div>
      ),
    },
  ]

  return (
    <TabbedDialog
      open={open}
      onOpenChange={onOpenChange}
      title={isEdit ? `Каталог промокодов «${catalog?.name}»` : "Новый каталог промокодов"}
      description="Группа промокодов с едиными правилами начисления бонусов или скидок"
      tabs={tabs}
      primaryAction={{
        label: isEdit ? "Сохранить изменения" : "Создать каталог",
        onClick: () => save.mutate(),
        disabled: name.trim().length < 1 || (!isEdit && slug.trim().length < 2) || save.isPending,
        loading: save.isPending,
      }}
      secondaryAction={{
        label: "Отмена",
        onClick: () => onOpenChange(false),
      }}
    />
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
    onError: (e: unknown) => toastError("Не удалось удалить каталог", getErrorDetail(e)),
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
    onError: (e: unknown) => toastError("Не удалось выпустить коды", getErrorDetail(e)),
  })

  const tabs: TabDefinition[] = [
    {
      id: "issue",
      label: "Выпуск промокодов",
      icon: Ticket,
      content: (
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label className="text-xs">Способ генерации</Label>
            <Select value={mode} onValueChange={(v) => setMode((v as "generate" | "explicit") ?? "generate")}>
              <SelectTrigger className="text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="generate">Сгенерировать случайные коды автоматически</SelectItem>
                <SelectItem value="explicit">Задать список кодов вручную</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {mode === "generate" ? (
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label className="text-xs">Количество кодов</Label>
                <Input
                  type="number"
                  min={1}
                  max={10000}
                  value={count}
                  onChange={(e) => setCount(e.target.value)}
                  className="font-mono text-xs"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Префикс кодов</Label>
                <Input
                  value={prefix}
                  onChange={(e) => setPrefix(e.target.value)}
                  maxLength={16}
                  placeholder="NY2025"
                  className="font-mono text-xs uppercase"
                />
              </div>
            </div>
          ) : (
            <div className="space-y-1.5">
              <Label className="text-xs">Коды (по одному на строку)</Label>
              <Textarea
                className="font-mono text-xs"
                rows={5}
                value={explicitCodes}
                onChange={(e) => setExplicitCodes(e.target.value)}
                placeholder="PROMO-123&#10;PROMO-456&#10;PROMO-789"
              />
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Лимит использований на один код</Label>
              <Input
                type="number"
                min={1}
                value={maxUses}
                onChange={(e) => setMaxUses(e.target.value)}
                placeholder="без лимита"
                className="font-mono text-xs"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Срок действия (до даты)</Label>
              <Input
                type="date"
                value={validTo}
                onChange={(e) => setValidTo(e.target.value)}
                className="text-xs"
              />
            </div>
          </div>
        </div>
      ),
    },
  ]

  return (
    <TabbedDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Выпуск промокодов"
      description="Генерация уникальных кодов для выбранного промо-каталога"
      tabs={tabs}
      primaryAction={{
        label: "Выпустить коды",
        onClick: () => issue.mutate(),
        disabled: issue.isPending || (mode === "generate" ? !Number(count) : !explicitCodes.trim()),
        loading: issue.isPending,
      }}
      secondaryAction={{
        label: "Отмена",
        onClick: () => onOpenChange(false),
      }}
    />
  )
}

function CatalogCodesPanel({ catalog }: { catalog: Catalog }) {
  const table = useDataTableQuery()
  const [issuing, setIssuing] = useState(false)
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
    onError: (e: unknown) => toastError("Не удалось изменить код", getErrorDetail(e)),
  })

  const remove = useMutation({
    mutationFn: async (id: number) => api.delete(`/v1/admin/promo/codes/${id}`),
    onSuccess: () => {
      toastSuccess("Код удалён")
      void qc.invalidateQueries({ queryKey: ["admin-promo-codes", catalog.id] })
    },
    onError: (e: unknown) => toastError("Не удалось удалить код", getErrorDetail(e)),
  })

  const columns: DataTableColumn<Code>[] = [
    { key: "code", header: "Код", render: (c) => <span className="font-mono text-xs font-semibold">{c.code}</span> },
    {
      header: "Активаций",
      render: (c) => `${c.used_count}${c.max_uses ? ` / ${c.max_uses}` : ""}`,
    },
    {
      header: "Срок",
      render: (c) => (c.valid_to ? new Date(c.valid_to).toLocaleDateString() : "бессрочно"),
    },
    {
      header: "Активен",
      render: (c) => (
        <Switch
          checked={c.is_active}
          onCheckedChange={(val) => toggle.mutate({ id: c.id, is_active: val })}
        />
      ),
    },
    {
      header: "",
      className: "w-10 text-right",
      render: (c) => (
        <Button
          variant="ghost"
          size="icon"
          className="size-7 text-muted-foreground hover:text-destructive"
          onClick={() => remove.mutate(c.id)}
        >
          <Trash2 className="size-3.5" />
        </Button>
      ),
    },
  ]

  return (
    <div className="space-y-3 pt-2">
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">
          Список кодов каталога «{catalog.name}» (всего {data?.total ?? 0})
        </p>
        <Button size="sm" variant="outline" onClick={() => setIssuing(true)}>
          <Plus className="size-3.5" /> Выпустить ещё
        </Button>
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
  const { symbol: currencySymbol } = useInstanceCurrency()
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<Catalog | null>(null)
  const [deleting, setDeleting] = useState<Catalog | null>(null)
  const [selectedCatalog, setSelectedCatalog] = useState<Catalog | null>(null)

  const canCreate = can("promo.create")
  const canEdit = can("promo.edit")
  const canDelete = can("promo.delete")

  const { data: catalogs, isLoading } = useQuery({
    queryKey: ["admin-promo-catalogs"],
    queryFn: async () => (await api.get<Catalog[]>("/v1/admin/promo/catalogs")).data,
  })

  const { data: services } = useQuery({
    queryKey: ["admin-services-lookup"],
    queryFn: async () => (await api.get<Service[]>("/v1/admin/services")).data,
    staleTime: 60_000,
  })

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <div>
          <h1 className="text-xl font-semibold">Промокоды и акции</h1>
          <p className="text-sm text-muted-foreground">
            Каталоги промокодов: бонусы на баланс, скидки в процентах/суммах, выдача услуг.
          </p>
        </div>
        {canCreate && (
          <Button size="sm" onClick={() => setCreating(true)}>
            <Plus className="size-4" /> Добавить каталог
          </Button>
        )}
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Загрузка…</p>}
      {!isLoading && (catalogs?.length ?? 0) === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-2 py-10 text-center text-sm text-muted-foreground">
            <Ticket className="size-6 text-primary" />
            Каталогов промокодов ещё нет.
          </CardContent>
        </Card>
      )}

      <div className="grid gap-2">
        {catalogs?.map((c) => (
          <Card key={c.id}>
            <CardContent className="space-y-2 py-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{c.name}</span>
                    <span className="font-mono text-xs text-muted-foreground">{c.slug}</span>
                    <Badge variant="outline">{KIND_LABEL[c.kind]}</Badge>
                    <Badge variant={c.is_active ? "default" : "secondary"}>
                      {c.is_active ? "активен" : "скрыт"}
                    </Badge>
                  </div>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {c.kind === "bonus" && `Бонус: ${c.value} ${currencySymbol}`}
                    {c.kind === "discount" &&
                      `Скидка: ${c.value} ${c.discount_type === "percent" ? "%" : currencySymbol}`}
                    {c.kind === "service" && `Услуга #${c.service_id}`}
                    {c.per_user && ` · не более ${c.per_user} шт/пользователь`}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    variant={selectedCatalog?.id === c.id ? "secondary" : "outline"}
                    onClick={() => setSelectedCatalog(selectedCatalog?.id === c.id ? null : c)}
                  >
                    <Ticket className="size-3.5" /> Коды
                  </Button>
                  {(canEdit || canDelete) && (
                    <DropdownMenu>
                      <DropdownMenuTrigger
                        render={
                          <Button variant="ghost" size="icon" className="size-8">
                            <MoreHorizontal className="size-4" />
                          </Button>
                        }
                      />
                      <DropdownMenuContent align="end">
                        {canEdit && <DropdownMenuItem onClick={() => setEditing(c)}>Изменить</DropdownMenuItem>}
                        {canDelete && (
                          <DropdownMenuItem
                            onClick={() => setDeleting(c)}
                            className="text-destructive focus:text-destructive"
                          >
                            <Trash2 className="size-4 mr-1.5" /> Удалить
                          </DropdownMenuItem>
                        )}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  )}
                </div>
              </div>

              {selectedCatalog?.id === c.id && <CatalogCodesPanel catalog={c} />}
            </CardContent>
          </Card>
        ))}
      </div>

      <CatalogFormDialog
        open={creating}
        onOpenChange={setCreating}
        catalog={null}
        services={services}
      />

      {editing && (
        <CatalogFormDialog
          open={!!editing}
          onOpenChange={(v) => !v && setEditing(null)}
          catalog={editing}
          services={services}
        />
      )}

      {deleting && (
        <DeleteCatalogDialog
          catalog={deleting}
          open={!!deleting}
          onOpenChange={(v) => !v && setDeleting(null)}
        />
      )}
    </div>
  )
}
