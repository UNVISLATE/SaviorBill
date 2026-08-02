import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ImageOff, PlayCircle, Sparkles, Trash2, Video } from "lucide-react"

import { api } from "@/api/api.ts"
import { useAuth } from "@/hooks/use-auth"
import { useDataTableQuery } from "@/hooks/use-data-table"
import { DataTable, type DataTableColumn } from "@/components/data-table/DataTable"
import { MediaLightbox } from "@/components/profile/MediaLightbox"
import { Badge } from "@/components/shadsnui/badge"
import { Button } from "@/components/shadsnui/button"
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

const STATUS_LABEL: Record<string, string> = {
  ready: "готово",
  processing: "обработка",
  failed: "ошибка",
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

function Thumb({ m }: { m: MediaItem }) {
  const src = m.thumb?.url ?? (m.kind === "image" && m.status === "ready" ? m.url : null)
  return (
    <div className="flex size-10 shrink-0 items-center justify-center overflow-hidden rounded-md border bg-muted">
      {src ? (
        <img src={src} alt="" className="size-full object-cover" />
      ) : m.kind === "video" ? (
        <PlayCircle className="size-4 text-muted-foreground" />
      ) : (
        <ImageOff className="size-4 text-muted-foreground" />
      )}
    </div>
  )
}

export function MediaLibraryPage() {
  const { can } = useAuth()
  const table = useDataTableQuery()
  const [kindFilter, setKindFilter] = useState<string>("all")
  const [cleanupOpen, setCleanupOpen] = useState(false)
  const [previewIndex, setPreviewIndex] = useState<number | null>(null)
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
  const previewItem = previewIndex !== null ? items[previewIndex] : null

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

  const columns: DataTableColumn<MediaItem>[] = [
    {
      header: "",
      className: "w-14",
      render: (m) => <Thumb m={m} />,
    },
    {
      key: "tag",
      header: "Тег / ID",
      render: (m) => <span className="font-mono text-xs">{m.tag ?? `#${m.id}`}</span>,
    },
    {
      key: "kind",
      header: "Тип",
      render: (m) => (m.kind === "video" ? "видео" : "изображение"),
    },
    {
      key: "status",
      header: "Статус",
      render: (m) => <Badge variant={STATUS_VARIANT[m.status] ?? "outline"}>{STATUS_LABEL[m.status] ?? m.status}</Badge>,
    },
    { key: "size", header: "Размер", render: (m) => fmtBytes(m.size) },
    {
      header: "Владелец",
      render: (m) => (m.owner_id ? <span className="font-mono text-xs">#{m.owner_id}</span> : "—"),
    },
    {
      key: "created_at",
      header: "Загружено",
      render: (m) => new Date(m.created_at).toLocaleString(),
    },
    ...(canDelete
      ? [
          {
            header: "",
            render: (m: MediaItem) => (
              <Button
                variant="ghost"
                size="icon"
                className="size-8 text-destructive"
                onClick={(e) => {
                  e.stopPropagation()
                  del.mutate(m.id)
                }}
              >
                <Trash2 className="size-4" />
              </Button>
            ),
          } satisfies DataTableColumn<MediaItem>,
        ]
      : []),
  ]

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

      <DataTable
        columns={columns}
        data={items}
        total={data?.total ?? 0}
        isLoading={isLoading}
        isError={isError}
        getRowId={(m) => m.id}
        onRowClick={(m) => setPreviewIndex(items.findIndex((i) => i.id === m.id))}
        sort={table.sort}
        onToggleSort={table.toggleSort}
        searchValue={table.searchInput}
        onSearchChange={table.setSearchInput}
        searchPlaceholder="Поиск по тегу/mime…"
        emptyMessage="Ничего не найдено"
        emptyHint={table.search ? "Попробуйте изменить запрос." : "Здесь появятся загруженные файлы."}
        limit={table.limit}
        offset={table.offset}
        hasMore={data?.has_more ?? false}
        onLimitChange={table.changeLimit}
        onOffsetChange={table.setOffset}
        toolbarExtra={
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
        }
      />

      {previewItem && (
        <MediaLightbox
          onClose={() => setPreviewIndex(null)}
          onPrev={items.length > 1 ? () => setPreviewIndex((i) => ((i ?? 0) - 1 + items.length) % items.length) : undefined}
          onNext={items.length > 1 ? () => setPreviewIndex((i) => ((i ?? 0) + 1) % items.length) : undefined}
          caption={
            <>
              {STATUS_LABEL[previewItem.status] ?? previewItem.status} · {fmtBytes(previewItem.size)} ·{" "}
              {previewItem.mime ?? "—"} · загружено {new Date(previewItem.created_at).toLocaleString()}
            </>
          }
        >
          {previewItem.kind === "image" && previewItem.status === "ready" ? (
            <img src={previewItem.url} alt="" className="max-h-[75vh] max-w-full object-contain" />
          ) : previewItem.kind === "video" && previewItem.status === "ready" ? (
            <video src={previewItem.url} controls autoPlay className="max-h-[75vh] max-w-full" />
          ) : (
            <div className="flex h-64 w-64 items-center justify-center bg-muted text-muted-foreground">
              <Video className="size-8" />
            </div>
          )}
        </MediaLightbox>
      )}

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
