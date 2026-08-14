import { useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { MoreHorizontal, Plus, Trash2 } from "lucide-react"

import { api } from "@/api/api.ts"
import { getErrorDetail } from "@/lib/api-error.ts"
import { useAuth } from "@/hooks/use-auth"
import { DataTable, type DataTableColumn } from "@/components/data-table/DataTable"
import { Button } from "@/components/shadsnui/button"
import { Input } from "@/components/shadsnui/input"
import { Label } from "@/components/shadsnui/label"
import { Switch } from "@/components/shadsnui/switch"
import { Badge } from "@/components/shadsnui/badge"
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
  parent_id: number | null
  description: string | null
  icon: string | null
  sort: number
  is_active: boolean
}

function CatalogFormDialog({
  open,
  onOpenChange,
  catalog,
  catalogs,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  catalog: Catalog | null
  catalogs: Catalog[]
}) {
  const isEdit = !!catalog
  const [name, setName] = useState(catalog?.name ?? "")
  const [slug, setSlug] = useState(catalog?.slug ?? "")
  const [parentId, setParentId] = useState<string>(catalog?.parent_id ? String(catalog.parent_id) : "")
  const [description, setDescription] = useState(catalog?.description ?? "")
  const [sort, setSort] = useState(String(catalog?.sort ?? 0))
  const [isActive, setIsActive] = useState(catalog?.is_active ?? true)
  const qc = useQueryClient()

  const options = catalogs.filter((c) => c.id !== catalog?.id)

  const save = useMutation({
    mutationFn: async () => {
      const body = {
        name,
        slug,
        parent_id: parentId ? Number(parentId) : null,
        description: description || null,
        sort: Number(sort) || 0,
        is_active: isActive,
      }
      if (isEdit) return api.patch(`/v1/admin/catalogs/${catalog!.id}`, body)
      return api.post("/v1/admin/catalogs", body)
    },
    onSuccess: () => {
      toastSuccess(isEdit ? "Каталог обновлён" : "Каталог создан")
      onOpenChange(false)
      void qc.invalidateQueries({ queryKey: ["admin-catalogs"] })
    },
    onError: (e: unknown) =>
      toastError(isEdit ? "Не удалось обновить каталог" : "Не удалось создать каталог", getErrorDetail(e)),
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEdit ? "Изменить каталог" : "Новый каталог"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1">
            <Label>Название</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} autoFocus />
          </div>
          <div className="space-y-1">
            <Label>Слаг</Label>
            <Input value={slug} onChange={(e) => setSlug(e.target.value)} placeholder="vpn-servers" />
          </div>
          <div className="space-y-1">
            <Label>Родительский каталог</Label>
            <Select value={parentId || "root"} onValueChange={(v) => setParentId(v === "root" ? "" : v ?? "")}>
              <SelectTrigger>
                <SelectValue placeholder="Корень" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="root">— Корень —</SelectItem>
                {options.map((c) => (
                  <SelectItem key={c.id} value={String(c.id)}>
                    {c.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label>Описание</Label>
            <Input value={description} onChange={(e) => setDescription(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label>Порядок сортировки</Label>
            <Input type="number" value={sort} onChange={(e) => setSort(e.target.value)} />
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
            disabled={name.trim().length < 1 || slug.trim().length < 2 || save.isPending}
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
    mutationFn: async () => api.delete(`/v1/admin/catalogs/${catalog.id}`),
    onSuccess: () => {
      toastSuccess(`Каталог «${catalog.name}» удалён`)
      onOpenChange(false)
      void qc.invalidateQueries({ queryKey: ["admin-catalogs"] })
    },
    onError: (e: unknown) => toastError("Не удалось удалить каталог", getErrorDetail(e)),
  })

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Удалить каталог «{catalog.name}»?</AlertDialogTitle>
          <AlertDialogDescription>
            Услуги внутри каталога не удалятся, но потеряют привязку к нему.
          </AlertDialogDescription>
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

/** Плоский список каталогов с указанием родителя — иерархия у нас неглубокая
 * (1-2 уровня), полноценное дерево с drag&drop избыточно для текущих
 * потребностей. Таблица вместо карточек: список каталогов обычно длиннее
 * экрана и карточки не несли доп. функционала — только занимали место.
 * Пагинация не нужна — backend отдаёт каталоги одним списком, сортировка и
 * поиск здесь чисто клиентские. */
export function CatalogsPage() {
  const { can } = useAuth()
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<Catalog | null>(null)
  const [deleting, setDeleting] = useState<Catalog | null>(null)
  const [search, setSearch] = useState("")
  const [sort, setSort] = useState<string | null>(null)

  const canCreate = can("catalogs.create")
  const canEdit = can("catalogs.edit")
  const canDelete = can("catalogs.delete")

  const { data, isLoading, isError } = useQuery({
    queryKey: ["admin-catalogs"],
    queryFn: async () => (await api.get<Catalog[]>("/v1/admin/catalogs")).data,
  })

  const byId = (id: number | null) => data?.find((c) => c.id === id)

  const toggleSort = (field: string) => {
    setSort((prev) => {
      if (prev === field) return `-${field}`
      if (prev === `-${field}`) return null
      return field
    })
  }

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    let list = data ?? []
    if (q) {
      list = list.filter(
        (c) => c.name.toLowerCase().includes(q) || c.slug.toLowerCase().includes(q),
      )
    }
    const field = sort?.replace(/^-/, "") ?? "sort"
    const dir = sort?.startsWith("-") ? -1 : 1
    const sorted = [...list].sort((a, b) => {
      const cmp =
        field === "name"
          ? a.name.localeCompare(b.name)
          : field === "slug"
            ? a.slug.localeCompare(b.slug)
            : a.sort - b.sort
      return cmp !== 0 ? cmp * dir : a.id - b.id
    })
    return sorted
  }, [data, search, sort])

  const columns: DataTableColumn<Catalog>[] = [
    {
      key: "name",
      header: "Название",
      render: (c) => (
        <div className="flex items-center gap-2">
          <span className="font-medium">{c.name}</span>
          {!c.is_active && <Badge variant="destructive">неактивен</Badge>}
        </div>
      ),
    },
    { key: "slug", header: "Слаг", render: (c) => <span className="font-mono text-xs">{c.slug}</span> },
    {
      header: "Родитель",
      render: (c) => (c.parent_id ? byId(c.parent_id)?.name ?? `#${c.parent_id}` : "— корень —"),
    },
    { header: "Описание", render: (c) => c.description ?? "—" },
    { key: "sort", header: "Сортировка", render: (c) => c.sort },
    {
      header: "",
      className: "w-10",
      render: (c) =>
        (canEdit || canDelete) && (
          <DropdownMenu>
            <DropdownMenuTrigger
              render={
                <Button variant="ghost" size="icon" className="size-8 shrink-0" onClick={(e) => e.stopPropagation()}>
                  <MoreHorizontal className="size-4" />
                </Button>
              }
            />
            <DropdownMenuContent align="end">
              {canEdit && <DropdownMenuItem onClick={() => setEditing(c)}>Изменить</DropdownMenuItem>}
              {canDelete && (
                <DropdownMenuItem variant="destructive" onClick={() => setDeleting(c)}>
                  <Trash2 className="size-4" /> Удалить
                </DropdownMenuItem>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        ),
    },
  ]

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <h1 className="text-xl font-semibold">Каталоги услуг</h1>
        {canCreate && (
          <Button size="sm" onClick={() => setCreating(true)}>
            <Plus className="size-4" /> Создать
          </Button>
        )}
      </div>

      <DataTable
        columns={columns}
        data={filtered}
        total={filtered.length}
        isLoading={isLoading}
        isError={isError}
        getRowId={(c) => c.id}
        onRowClick={canEdit ? (c) => setEditing(c) : undefined}
        sort={sort}
        onToggleSort={toggleSort}
        searchValue={search}
        onSearchChange={setSearch}
        searchPlaceholder="Поиск по названию/слагу…"
        emptyMessage="Каталогов не найдено"
        emptyHint={search ? "Попробуйте изменить запрос." : "Создайте первый каталог, чтобы группировать услуги."}
        limit={filtered.length || 1}
        offset={0}
        hasMore={false}
        onLimitChange={() => {}}
        onOffsetChange={() => {}}
      />

      <CatalogFormDialog open={creating} onOpenChange={setCreating} catalog={null} catalogs={data ?? []} />
      {editing && (
        <CatalogFormDialog
          open={!!editing}
          onOpenChange={(v) => !v && setEditing(null)}
          catalog={editing}
          catalogs={data ?? []}
        />
      )}
      {deleting && (
        <DeleteCatalogDialog catalog={deleting} open={!!deleting} onOpenChange={(v) => !v && setDeleting(null)} />
      )}
    </div>
  )
}
