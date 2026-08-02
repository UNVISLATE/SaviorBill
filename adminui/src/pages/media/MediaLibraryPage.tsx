import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ImageOff, PlayCircle, Sparkles, Trash2 } from "lucide-react"

import { api } from "@/api/api.ts"
import { useAuth } from "@/hooks/use-auth"
import { useDataTableQuery } from "@/hooks/use-data-table"
import { Badge } from "@/components/shadsnui/badge"
import { Button } from "@/components/shadsnui/button"
import { Input } from "@/components/shadsnui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/shadsnui/select"
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
import { toastError, toastSuccess } from "@/lib/toast"

interface MediaItem {
  id: number
  token: string
  kind: string
  tag: string | null
  status: string
  url: string
  backend: string
  mime: string | null
  size: number | null
  owner_id: number | null
  created_at: string
  thumb?: { url: string } | null
}

interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
  has_more: boolean
}

const STATUS_VARIANT: Record<string, "default" | "outline" | "destructive" | "secondary"> = {
  ready: "default",
  processing: "secondary",
  failed: "destructive",
}

function fmtBytes(n: number | null): string {
  if (n === null) return "—"
  if (n < 1024) return `${n} Б`
  const units = ["КБ", "МБ", "ГБ"]
  let v = n / 1024
  let i = 0
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i++
  }
  return `${v.toFixed(1)} ${units[i]}`
}

function errDetail(e: unknown): string | undefined {
  if (e && typeof e === "object" && "response" in e) {
    // @ts-expect-error — axios error shape
    const d = e.response?.data?.detail
    return typeof d === "string" ? d : undefined
  }
  return undefined
}

function MediaCard({ m, canDelete, onDelete }: { m: MediaItem; canDelete: boolean; onDelete: () => void }) {
  return (
    <div className="group relative overflow-hidden rounded-md border bg-muted">
      <div className="flex aspect-square items-center justify-center">
        {m.thumb?.url ? (
          <img src={m.thumb.url} alt={m.tag ?? ""} className="size-full object-cover" />
        ) : m.kind === "image" && m.status === "ready" ? (
          <img src={m.url} alt={m.tag ?? ""} className="size-full object-cover" />
        ) : m.kind === "video" ? (
          <PlayCircle className="size-8 text-muted-foreground" />
        ) : (
          <ImageOff className="size-8 text-muted-foreground" />
        )}
      </div>
      <div className="absolute inset-x-0 top-0 flex items-center justify-between gap-1 p-1">
        <Badge variant={STATUS_VARIANT[m.status] ?? "outline"} className="text-[10px]">
          {m.status}
        </Badge>
        {canDelete && (
          <Button
            variant="destructive"
            size="icon"
            className="size-6 opacity-0 transition-opacity group-hover:opacity-100"
            onClick={onDelete}
          >
            <Trash2 className="size-3" />
          </Button>
        )}
      </div>
      <div className="space-y-0.5 p-1.5 text-[11px]">
        <p className="truncate font-mono text-muted-foreground">{m.tag ?? `#${m.id}`}</p>
        <p className="text-muted-foreground">{fmtBytes(m.size)}{m.owner_id ? ` · #${m.owner_id}` : ""}</p>
      </div>
    </div>
  )
}

export function MediaLibraryPage() {
  const { can } = useAuth()
  const table = useDataTableQuery()
  const [kindFilter, setKindFilter] = useState<string>("all")
  const [cleanupOpen, setCleanupOpen] = useState(false)
  const canDelete = can("media.delete")
  const canCleanup = can("media.cleanup")
  const qc = useQueryClient()

  const { data, isLoading, isError } = useQuery({
    queryKey: ["admin-media", table.limit, table.offset, table.sort, table.search],
    queryFn: async () =>
      (
        await api.get<Page<MediaItem>>("/v1/admin/media", {
          params: {
            limit: table.limit,
            offset: table.offset,
            sort: table.sort ?? "-created_at",
            q: table.search || undefined,
          },
        })
      ).data,
    placeholderData: (prev) => prev,
  })

  const items = (data?.items ?? []).filter((m) => kindFilter === "all" || m.kind === kindFilter)

  const del = useMutation({
    mutationFn: async (id: number) => api.delete(`/v1/admin/media/${id}`),
    onSuccess: () => {
      toastSuccess("Медиа удалено")
      void qc.invalidateQueries({ queryKey: ["admin-media"] })
    },
    onError: (e: unknown) => toastError("Не удалось удалить медиа", errDetail(e)),
  })

  const cleanup = useMutation({
    mutationFn: async () => api.post("/v1/admin/media/cleanup"),
    onSuccess: (res) => {
      const n = (res.data as { deleted: number }).deleted
      toastSuccess(`Удалено неиспользуемых файлов: ${n}`)
      setCleanupOpen(false)
      void qc.invalidateQueries({ queryKey: ["admin-media"] })
    },
    onError: (e: unknown) => toastError("Не удалось выполнить очистку", errDetail(e)),
  })

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Медиатека</h1>
        {canCleanup && (
          <Button size="sm" variant="outline" onClick={() => setCleanupOpen(true)}>
            <Sparkles className="size-4" /> Очистить неиспользуемое
          </Button>
        )}
      </div>

      <div className="flex flex-wrap gap-2">
        <Input
          value={table.searchInput}
          onChange={(e) => table.setSearchInput(e.target.value)}
          placeholder="Поиск по тегу/mime…"
          className="max-w-xs"
        />
        <Select value={kindFilter} onValueChange={(v) => setKindFilter(v ?? "all")}>
          <SelectTrigger className="w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Все типы</SelectItem>
            <SelectItem value="image">Изображения</SelectItem>
            <SelectItem value="video">Видео</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Загрузка…</p>}
      {isError && <p className="text-sm text-destructive">Не удалось загрузить медиатеку.</p>}
      {!isLoading && !isError && items.length === 0 && (
        <p className="py-10 text-center text-sm text-muted-foreground">Ничего не найдено.</p>
      )}
      {!isLoading && items.length > 0 && (
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8">
          {items.map((m) => (
            <MediaCard key={m.id} m={m} canDelete={canDelete} onDelete={() => del.mutate(m.id)} />
          ))}
        </div>
      )}

      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <span>
          {data?.total ?? 0} всего · показано {items.length}
        </span>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={table.offset === 0}
            onClick={() => table.setOffset(Math.max(0, table.offset - table.limit))}
          >
            Назад
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={!data?.has_more}
            onClick={() => table.setOffset(table.offset + table.limit)}
          >
            Далее
          </Button>
        </div>
      </div>

      <AlertDialog open={cleanupOpen} onOpenChange={setCleanupOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Очистить неиспользуемые файлы?</AlertDialogTitle>
            <AlertDialogDescription>
              Удалятся медиа, не привязанные ни к вложениям услуг, ни к аватарам, старше периода
              хранения. Действие необратимо.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Отмена</AlertDialogCancel>
            <AlertDialogAction disabled={cleanup.isPending} onClick={() => cleanup.mutate()}>
              Очистить
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
