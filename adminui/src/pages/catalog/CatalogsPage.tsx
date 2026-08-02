import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { FolderTree, MoreHorizontal, Plus, Trash2 } from "lucide-react"

import { api } from "@/api/api.ts"
import { useAuth } from "@/hooks/use-auth"
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
import { Card, CardContent } from "@/components/shadsnui/card"
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

function errDetail(e: unknown): string | undefined {
  if (e && typeof e === "object" && "response" in e) {
    // @ts-expect-error — axios error shape
    const d = e.response?.data?.detail
    return typeof d === "string" ? d : undefined
  }
  return undefined
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
      toastError(isEdit ? "Не удалось обновить каталог" : "Не удалось создать каталог", errDetail(e)),
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
    onError: (e: unknown) => toastError("Не удалось удалить каталог", errDetail(e)),
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
 * потребностей; сортировка внутри каталога — полем `sort`. */
export function CatalogsPage() {
  const { can } = useAuth()
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<Catalog | null>(null)
  const [deleting, setDeleting] = useState<Catalog | null>(null)

  const canCreate = can("catalogs.create")
  const canEdit = can("catalogs.edit")
  const canDelete = can("catalogs.delete")

  const { data, isLoading } = useQuery({
    queryKey: ["admin-catalogs"],
    queryFn: async () => (await api.get<Catalog[]>("/v1/admin/catalogs")).data,
  })

  const byId = (id: number | null) => data?.find((c) => c.id === id)
  const sorted = [...(data ?? [])].sort((a, b) => a.sort - b.sort || a.id - b.id)

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

      {isLoading && <p className="text-sm text-muted-foreground">Загрузка…</p>}
      {!isLoading && sorted.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-2 py-10 text-center text-sm text-muted-foreground">
            <FolderTree className="size-6" />
            Каталогов пока нет — создайте первый, чтобы группировать услуги.
          </CardContent>
        </Card>
      )}
      {!isLoading && sorted.length > 0 && (
        <div className="grid gap-2">
          {sorted.map((c) => (
            <Card key={c.id}>
              <CardContent className="flex items-center justify-between gap-3 py-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="truncate font-medium">{c.name}</span>
                    <span className="font-mono text-xs text-muted-foreground">{c.slug}</span>
                    {!c.is_active && <Badge variant="destructive">неактивен</Badge>}
                  </div>
                  <div className="mt-0.5 text-xs text-muted-foreground">
                    {c.parent_id ? `Внутри: ${byId(c.parent_id)?.name ?? `#${c.parent_id}`}` : "Корневой каталог"}
                    {c.description ? ` · ${c.description}` : ""}
                  </div>
                </div>
                {(canEdit || canDelete) && (
                  <DropdownMenu>
                    <DropdownMenuTrigger
                      render={
                        <Button variant="ghost" size="icon" className="size-8 shrink-0">
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
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

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
