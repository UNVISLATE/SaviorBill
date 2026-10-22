import { useState, useRef, useEffect, useMemo } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  ImageOff,
  Sparkles,
  Trash2,
  Video,
  Upload,
  RotateCw,
  PlayCircle,
  X,
  Pencil,
} from "lucide-react"
import { api } from "@/api/api.ts"
import { getErrorDetail } from "@/lib/api-error.ts"
import { useAuth } from "@/hooks/use-auth"
import { useDataTableQuery } from "@/hooks/use-data-table"
import { DataTable, type DataTableColumn } from "@/components/data-table/DataTable"
import { Button } from "@/components/shadsnui/button"
import { Badge } from "@/components/shadsnui/badge"
import { MediaLightbox } from "@/components/profile/MediaLightbox"
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
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/shadsnui/dialog"
import { Input } from "@/components/shadsnui/input"
import { Label } from "@/components/shadsnui/label"
import { toastError, toastSuccess } from "@/lib/toast"
import {
  useMediaUploadQueue,
  type UploadJob,
} from "@/hooks/use-media-upload-queue"
import { MediaUploadConfigModal } from "@/components/media/MediaUploadConfigModal"
import { isMediaConfigRequired, type MediaUploadConfig } from "@/api/media-upload"
import { MediaContextMenu } from "@/components/media/MediaContextMenu"
import { useAdminUiSettings } from "@/api/admin-ui-settings"

interface MediaItem {
  id: number
  token: string
  kind: string
  tag: string | null
  name?: string | null
  status: string
  url: string
  backend: string
  mime: string | null
  size: number | null
  owner_id: number | null
  created_at: string
  media?: { url: string } | null
  thumb?: { url: string } | null
  _isOptimistic?: boolean
  _job?: UploadJob
}

interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
  has_more: boolean
}

const STATUS_VARIANT: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  ready: "secondary",
  processing: "default",
  failed: "destructive",
}

const STATUS_LABEL: Record<string, string> = {
  ready: "готов",
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

function Thumb({ m }: { m: MediaItem }) {
  const [hasError, setHasError] = useState(false)
  const src = m.thumb?.url || (m.kind === "image" ? (m.media?.url || m.url) : null) || m._job?.previewUrl
  return (
    <div className="flex size-10 shrink-0 items-center justify-center overflow-hidden rounded-md border bg-muted">
      {src && !hasError ? (
        <img
          src={src}
          alt={m.name || m.token}
          onError={() => setHasError(true)}
          className="size-full object-cover"
        />
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
  const fileInputRef = useRef<HTMLInputElement>(null)
  const qc = useQueryClient()

  const [kindFilter, setKindFilter] = useState<string>("all")
  const [cleanupOpen, setCleanupOpen] = useState(false)
  const [previewIndex, setPreviewIndex] = useState<number | null>(null)

  // Settings for UI media modal & defaults
  const { data: adminSettings } = useAdminUiSettings()

  // Upload state (supports batch)
  const [pendingFiles, setPendingFiles] = useState<File[]>([])
  const [configModalOpen, setConfigModalOpen] = useState(false)
  const [isDragOver, setIsDragOver] = useState(false)

  // Rename state
  const [renameItem, setRenameItem] = useState<MediaItem | null>(null)
  const [newName, setNewName] = useState<string>("")

  const renameMutation = useMutation({
    mutationFn: async ({ id, name }: { id: number; name: string }) => {
      return api.put(`/v1/admin/media/${id}/name`, { name })
    },
    onSuccess: () => {
      toastSuccess("Имя файла обновлено")
      setRenameItem(null)
      void qc.invalidateQueries({ queryKey: ["admin-media"] })
    },
    onError: (e: unknown) => {
      toastError("Не удалось переименовать файл", getErrorDetail(e))
    },
  })

  const {
    jobs: uploadJobs,
    uploadFile,
    retryJob,
    removeJob,
    isBusy: uploading,
  } = useMediaUploadQueue({
    autoRestoreJobs: true,
    queryKeysToInvalidate: [["admin-media"]],
    onJobSuccess: (_job) => {
      toastSuccess(`Файл «${_job.fileName}» готов`)
      void qc.invalidateQueries({ queryKey: ["admin-media"] })
    },
  })

  const canDelete = can("media.delete")
  const canCleanup = can("media.cleanup")
  const canUpload = can("admin.media.upload") || can("media.upload.image") || can("media.upload.video")
  const canSetAvatar = can("admin.media.manage_any")

  const setAvatar = useMutation({
    mutationFn: async (item: MediaItem) => api.put("/v1/user/me/avatar", { media_id: item.id }),
    onSuccess: () => toastSuccess("Аватар обновлён"),
    onError: (e: unknown) => toastError("Не удалось установить аватар", getErrorDetail(e)),
  })

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

  const rawItems = (data?.items ?? []).filter((m) => kindFilter === "all" || m.kind === kindFilter)

  const executeUpload = async (file: File, config?: MediaUploadConfig) => {
    try {
      await uploadFile(file, config)
    } catch (e: unknown) {
      toastError("Ошибка загрузки", getErrorDetail(e))
    }
  }

  const getDefaultConfig = (file: File): MediaUploadConfig => {
    const isGif = file.type === "image/gif" || file.name.toLowerCase().endsWith(".gif")
    const isVideo = file.type.startsWith("video/") || /\.(mp4|webm|mkv|mov|avi)$/i.test(file.name)
    const def = adminSettings?.mediadialog?.default

    if (isGif) {
      const fmt = def?.gif_format || "gif"
      return {
        format: fmt as any,
        keep_animation: fmt === "gif",
        video_codec: fmt === "gif" ? "copy" : "libvpx-vp9",
        poster_scale: def?.poster_scale || "1080p",
      }
    }

    if (isVideo) {
      const isOriginal = (def?.video_format || "webm") === "original"
      if (isOriginal) {
        return {
          format: "original",
          video_codec: "copy",
          audio_codec: "copy",
          poster_scale: def?.poster_scale || "1080p",
        }
      }
      return {
        format: (def?.video_format as any) || "webm",
        video_codec: (def?.video_codec as any) || "libvpx-vp9",
        audio_codec: (def?.audio_codec as any) || "libopus",
        scale: (def?.scale as any) || "original",
        poster_scale: def?.poster_scale || "1080p",
        crf: def?.crf ?? 32,
      }
    }

    return { format: "webp" }
  }

  const handleFiles = (files: File[]) => {
    if (files.length === 0) return
    const isDialogEnabled = adminSettings?.mediadialog?.enabled ?? true

    if (!isDialogEnabled) {
      for (const file of files) {
        void executeUpload(file, getDefaultConfig(file))
      }
      return
    }

    const instantFiles: File[] = []
    const configurableFiles: File[] = []

    for (const f of files) {
      if (isMediaConfigRequired(f)) {
        configurableFiles.push(f)
      } else {
        instantFiles.push(f)
      }
    }

    for (const f of instantFiles) {
      void executeUpload(f)
    }

    if (configurableFiles.length > 0) {
      setPendingFiles(configurableFiles)
      setConfigModalOpen(true)
    }
  }

  // Full-window drag & drop overlay listener
  useEffect(() => {
    let dragCounter = 0
    const handleDragEnter = (e: DragEvent) => {
      e.preventDefault()
      dragCounter++
      if (e.dataTransfer?.types?.includes("Files")) {
        setIsDragOver(true)
      }
    }
    const handleDragOver = (e: DragEvent) => {
      e.preventDefault()
    }
    const handleDragLeave = (e: DragEvent) => {
      e.preventDefault()
      dragCounter--
      if (dragCounter <= 0) {
        dragCounter = 0
        setIsDragOver(false)
      }
    }
    const handleDrop = (e: DragEvent) => {
      e.preventDefault()
      dragCounter = 0
      setIsDragOver(false)
      if (e.dataTransfer?.files && e.dataTransfer.files.length > 0) {
        handleFiles(Array.from(e.dataTransfer.files))
      }
    }

    window.addEventListener("dragenter", handleDragEnter)
    window.addEventListener("dragover", handleDragOver)
    window.addEventListener("dragleave", handleDragLeave)
    window.addEventListener("drop", handleDrop)

    return () => {
      window.removeEventListener("dragenter", handleDragEnter)
      window.removeEventListener("dragover", handleDragOver)
      window.removeEventListener("dragleave", handleDragLeave)
      window.removeEventListener("drop", handleDrop)
    }
  }, [adminSettings])

  // Optimistic table rows for items currently uploading or converting
  const optimisticItems: MediaItem[] = useMemo(() => {
    return uploadJobs
      .filter((j) => j.phase !== "done" || !rawItems.some((m) => m.token === j.token))
      .map((job, idx) => ({
        id: -1000 - idx,
        token: job.token ?? job.id,
        kind:
          (job.file?.type ?? "").startsWith("video/") || /\.(mp4|webm|mkv|mov|avi)$/i.test(job.fileName)
            ? "video"
            : "image",
        tag: job.tag ?? null,
        status:
          job.phase === "uploading"
            ? "uploading"
            : job.phase === "processing"
              ? "processing"
              : job.phase === "error"
                ? "failed"
                : "queued",
        url: job.previewUrl ?? "",
        backend: "fs",
        mime: job.file?.type || null,
        size: job.fileSize ?? null,
        owner_id: null,
        created_at: new Date().toISOString(),
        thumb: job.previewUrl ? { url: job.previewUrl } : null,
        _isOptimistic: true,
        _job: job,
      }))
  }, [uploadJobs, rawItems])

  const items = useMemo(() => {
    return [
      ...optimisticItems,
      ...rawItems.filter((m) => !optimisticItems.some((o) => o.token === m.token)),
    ]
  }, [optimisticItems, rawItems])

  const previewItem = previewIndex !== null ? items[previewIndex] : null

  const del = useMutation({
    mutationFn: async (id: number) => api.delete(`/v1/admin/media/${id}`),
    onSuccess: () => {
      toastSuccess("Медиа удалено")
      void qc.invalidateQueries({ queryKey: ["admin-media"] })
    },
    onError: (e: unknown) => toastError("Не удалось удалить медиа", getErrorDetail(e)),
  })

  const cleanup = useMutation({
    mutationFn: async () => api.post<{ purged: number }>("/v1/admin/media/cleanup"),
    onSuccess: (res) => {
      toastSuccess(`Очищено файлов: ${res.data.purged}`)
      setCleanupOpen(false)
      void qc.invalidateQueries({ queryKey: ["admin-media"] })
    },
    onError: (e: unknown) => toastError("Не удалось выполнить очистку", getErrorDetail(e)),
  })

  const columns: DataTableColumn<MediaItem>[] = [
    {
      header: "",
      className: "w-[50px] min-w-[50px] max-w-[50px]",
      render: (m: MediaItem) => {
        if (m._isOptimistic) {
          const optSrc = m.thumb?.url || m._job?.previewUrl || (m.kind === "image" ? (m.media?.url || m.url) : null)
          return (
            <div className="relative flex size-10 shrink-0 items-center justify-center overflow-hidden rounded-md border bg-muted">
              {optSrc ? (
                <img src={optSrc} alt="" className="size-full object-cover opacity-80" />
              ) : m.kind === "video" ? (
                <PlayCircle className="size-4 text-muted-foreground" />
              ) : (
                <ImageOff className="size-4 text-muted-foreground" />
              )}
              {m._job && (m._job.phase === "uploading" || m._job.phase === "processing") && (
                <div className="absolute inset-0 bg-background/60 backdrop-blur-[1px] flex items-center justify-center">
                  <RotateCw className="size-4 animate-spin text-primary" />
                </div>
              )}
            </div>
          )
        }
        return <Thumb m={m} />
      },
    },
    {
      key: "token",
      header: "Файл / Токен",
      className: "w-[180px] min-w-[180px] max-w-[220px]",
      render: (m: MediaItem) => {
        if (m._isOptimistic) {
          return (
            <div className="flex flex-col min-w-0">
              <span className="text-xs font-semibold text-foreground truncate max-w-[170px]">
                {m._job?.fileName ?? m.name ?? m.token}
              </span>
              <span className="font-mono text-[10px] text-muted-foreground">
                {m.token.startsWith("job_") ? "подготовка…" : `${m.token.slice(0, 10)}…`}
              </span>
            </div>
          )
        }
        return (
          <div
            className="flex flex-col min-w-0"
            title={m.name ? `${m.name} (${m.token})` : m.token}
          >
            <span className="text-xs font-semibold text-foreground truncate max-w-[170px]">
              {m.name || `${m.token.slice(0, 12)}…`}
            </span>
            {m.name && (
              <span className="font-mono text-[10px] text-muted-foreground truncate max-w-[170px]">
                {m.token.slice(0, 12)}…
              </span>
            )}
          </div>
        )
      },
    },
    {
      key: "kind",
      header: "Тип",
      className: "w-[75px] min-w-[75px]",
      render: (m: MediaItem) => <span className="capitalize">{m.kind}</span>,
    },
    {
      key: "tag",
      header: "Тег",
      className: "w-[90px] min-w-[90px]",
      render: (m: MediaItem) =>
        m.tag ? (
          <Badge variant="outline" className="font-mono text-xs">
            {m.tag}
          </Badge>
        ) : (
          "—"
        ),
    },
    {
      key: "status",
      header: "Статус",
      className: "w-[190px] min-w-[190px] max-w-[190px]",
      render: (m: MediaItem) => {
        if (m._isOptimistic && m._job) {
          const j = m._job
          if (j.phase === "uploading") {
            const pct = Math.min(100, Math.max(0, j.uploadPct || 0))
            return (
              <Badge
                variant="outline"
                className="relative w-[175px] h-6 justify-center overflow-hidden border-sky-500/60 bg-sky-950/40 p-0 text-white"
              >
                <div
                  className="absolute inset-y-0 left-0 bg-sky-500 transition-[width] duration-300 ease-out"
                  style={{ width: `${pct}%` }}
                />
                <span className="relative z-10 flex items-center justify-center gap-1.5 font-mono tabular-nums text-xs font-semibold text-white drop-shadow-[0_1px_2px_rgba(0,0,0,0.9)]">
                  <Upload className="size-3 animate-bounce shrink-0 text-white" />
                  <span>Загрузка {j.uploadPct}%</span>
                </span>
              </Badge>
            )
          }
          if (j.phase === "processing") {
            const pct = Math.min(100, Math.max(0, j.convertPct ?? 0))
            return (
              <Badge
                variant="outline"
                className="relative w-[175px] h-6 justify-center overflow-hidden border-amber-500/60 bg-amber-950/40 p-0 text-white"
              >
                <div
                  className="absolute inset-y-0 left-0 bg-amber-500 transition-[width] duration-300 ease-out"
                  style={{ width: `${pct}%` }}
                />
                <span className="relative z-10 flex items-center justify-center gap-1.5 font-mono tabular-nums text-xs font-semibold text-white drop-shadow-[0_1px_2px_rgba(0,0,0,0.9)]">
                  <RotateCw className="size-3 animate-spin shrink-0 text-white" />
                  <span>
                    {j.convertPct != null ? `${j.convertPct}%` : "Сжатие"}
                    {j.etaSec != null ? ` (${j.etaSec}с)` : ""}
                  </span>
                </span>
              </Badge>
            )
          }
          if (j.phase === "queued") {
            return (
              <Badge variant="outline" className="w-[175px] justify-center text-muted-foreground border-border text-xs">
                <span>В очереди…</span>
              </Badge>
            )
          }
          if (j.phase === "error") {
            return (
              <Badge variant="destructive" className="w-[175px] justify-center text-xs">
                <span>Ошибка</span>
              </Badge>
            )
          }
        }
        return (
          <Badge variant={STATUS_VARIANT[m.status] ?? "outline"} className="w-[100px] justify-center text-xs">
            {STATUS_LABEL[m.status] ?? m.status}
          </Badge>
        )
      },
    },
    {
      key: "size",
      header: "Размер",
      className: "w-[85px] min-w-[85px] font-mono tabular-nums",
      render: (m: MediaItem) => fmtBytes(m.size),
    },
    {
      key: "mime",
      header: "MIME",
      className: "w-[120px] min-w-[120px] max-w-[120px] font-mono text-[11px] truncate",
      render: (m: MediaItem) => m.mime ?? "—",
    },
    {
      key: "created_at",
      header: "Загружен",
      className: "w-[140px] min-w-[140px] text-xs text-muted-foreground",
      render: (m: MediaItem) => (m._isOptimistic ? "Сейчас" : new Date(m.created_at).toLocaleString()),
    },
    {
      header: "",
      className: "w-[80px] min-w-[80px] text-right",
      render: (m: MediaItem) => {
        if (m._isOptimistic && m._job) {
          if (m._job.phase === "error") {
            return (
              <Button
                variant="ghost"
                size="sm"
                className="h-8 text-xs gap-1"
                onClick={() => retryJob(m._job!.id)}
              >
                <RotateCw className="size-3.5" />
                Повторить
              </Button>
            )
          }
          return (
            <Button
              variant="ghost"
              size="icon"
              className="size-8 text-muted-foreground"
              onClick={() => removeJob(m._job!.id)}
            >
              <X className="size-4" />
            </Button>
          )
        }
        return (
          <div className="flex items-center justify-end gap-1">
            <Button
              variant="ghost"
              size="icon"
              className="size-8 text-muted-foreground hover:text-foreground"
              title="Переименовать"
              onClick={(e) => {
                e.stopPropagation()
                e.preventDefault()
                setRenameItem(m)
                setNewName(m.name || "")
              }}
            >
              <Pencil className="size-3.5" />
            </Button>
            {canDelete && (
              <Button
                variant="ghost"
                size="icon"
                className="size-8 text-destructive hover:bg-destructive/10"
                title="Удалить"
                onClick={(e) => {
                  e.stopPropagation()
                  e.preventDefault()
                  del.mutate(m.id)
                }}
              >
                <Trash2 className="size-4" />
              </Button>
            )}
          </div>
        )
      },
    } satisfies DataTableColumn<MediaItem>,
  ]

  return (
    <div className="relative space-y-4">
      {/* Full-window Drag & Drop Backlight Overlay */}
      {isDragOver && (
        <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-background/80 backdrop-blur-md border-4 border-dashed border-primary animate-in fade-in-50 duration-200 pointer-events-none">
          <div className="p-6 rounded-2xl bg-card/90 shadow-2xl border border-primary/40 flex flex-col items-center gap-3 text-center max-w-sm">
            <div className="size-16 rounded-2xl bg-primary/10 flex items-center justify-center text-primary">
              <Upload className="size-8 animate-bounce" />
            </div>
            <div>
              <p className="text-base font-semibold text-foreground">Отпустите файлы для загрузки</p>
              <p className="text-xs text-muted-foreground mt-1">
                Файлы появятся прямо в таблице медиатеки и начнут конвертироваться
              </p>
            </div>
          </div>
        </div>
      )}

      <input
        ref={fileInputRef}
        type="file"
        multiple
        className="hidden"
        accept="image/*,video/*,.svg"
        onChange={(e) => {
          if (e.target.files && e.target.files.length > 0) {
            handleFiles(Array.from(e.target.files))
            e.target.value = ""
          }
        }}
      />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Медиатека</h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Архив загруженных файлов, медиа карточек товаров и аватаров.
          </p>
        </div>

        <div className="flex items-center gap-2">
          {canUpload && (
            <Button
              size="sm"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
              className="gap-1.5 shadow-xs"
            >
              {uploading ? (
                <RotateCw className="size-4 animate-spin" />
              ) : (
                <Upload className="size-4" />
              )}
              <span>Загрузить медиа</span>
            </Button>
          )}

          {canCleanup && (
            <Button size="sm" variant="outline" onClick={() => setCleanupOpen(true)}>
              <Sparkles className="size-4" /> Очистить неиспользуемое
            </Button>
          )}
        </div>
      </div>

      <DataTable
        columns={columns}
        data={items}
        total={(data?.total ?? 0) + optimisticItems.length}
        isLoading={isLoading}
        isError={isError}
        getRowId={(m: MediaItem) => m.id}
        renderRow={(row, rowElement) => {
          if (row._isOptimistic) return rowElement
          return (
            <MediaContextMenu
              key={row.id}
              item={row}
              asChild
              onOpenPreview={() => setPreviewIndex(items.findIndex((i) => i.id === row.id))}
              onRename={() => {
                setRenameItem(row)
                setNewName(row.name || "")
              }}
              onSetAvatar={canSetAvatar && row.kind === "image" ? () => setAvatar.mutate(row) : undefined}
              onDelete={canDelete ? () => del.mutate(row.id) : undefined}
              canDelete={canDelete}
              canSetAvatar={canSetAvatar}
            >
              {rowElement}
            </MediaContextMenu>
          )
        }}
        onRowClick={(m: MediaItem) => {
          if (!m._isOptimistic) {
            setPreviewIndex(items.findIndex((i) => i.id === m.id))
          }
        }}
        sort={table.sort}
        onToggleSort={table.toggleSort}
        searchValue={table.searchInput}
        onSearchChange={table.setSearchInput}
        searchPlaceholder="Поиск по названию, токену, тегу, MIME…"
        emptyMessage="Ничего не найдено"
        emptyHint={table.search ? "Попробуйте изменить запрос." : "Здесь появятся загруженные файлы."}
        limit={table.limit}
        offset={table.offset}
        hasMore={data?.has_more ?? false}
        onLimitChange={table.changeLimit}
        onOffsetChange={table.setOffset}
        toolbarExtra={
          <Select value={kindFilter} onValueChange={(v) => setKindFilter(v ?? "all")}>
            <SelectTrigger className="w-40 h-8 text-xs">
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

      {previewItem && !previewItem._isOptimistic && (
        <MediaLightbox
          onClose={() => setPreviewIndex(null)}
          onPrev={
            items.filter((i) => !i._isOptimistic).length > 1
              ? () => setPreviewIndex((i) => ((i ?? 0) - 1 + items.length) % items.length)
              : undefined
          }
          onNext={
            items.filter((i) => !i._isOptimistic).length > 1
              ? () => setPreviewIndex((i) => ((i ?? 0) + 1) % items.length)
              : undefined
          }
          mediaUrl={previewItem.url}
          onDelete={
            canDelete
              ? () => {
                  del.mutate(previewItem.id)
                  setPreviewIndex(null)
                }
              : undefined
          }
          caption={
            <>
              {STATUS_LABEL[previewItem.status] ?? previewItem.status} · {fmtBytes(previewItem.size)} ·{" "}
              {previewItem.mime ?? "—"} · загружено {new Date(previewItem.created_at).toLocaleString()}
            </>
          }
        >
          {previewItem.kind === "image" ? (
            <img src={previewItem.url} alt="" className="max-h-[75vh] max-w-full object-contain" />
          ) : previewItem.kind === "video" ? (
            <video src={previewItem.url} controls autoPlay className="max-h-[75vh] max-w-full" />
          ) : (
            <div className="flex h-64 w-64 items-center justify-center bg-muted text-muted-foreground">
              <Video className="size-8" />
            </div>
          )}
        </MediaLightbox>
      )}

      {/* Cleanup confirmation */}
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

      {/* Conversion config modal for Video and GIF (supports batch) */}
      <MediaUploadConfigModal
        open={configModalOpen}
        files={pendingFiles}
        onCancel={() => {
          setConfigModalOpen(false)
          setPendingFiles([])
        }}
        onConfirmBatch={(items) => {
          for (const it of items) {
            void executeUpload(it.file, it.config)
          }
          setConfigModalOpen(false)
          setPendingFiles([])
        }}
      />

      {/* Rename dialog */}
      <Dialog open={!!renameItem} onOpenChange={(open) => !open && setRenameItem(null)}>
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle className="text-base font-semibold">Переименовать медиа</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="space-y-1.5">
              <Label htmlFor="rename-input" className="text-xs font-medium">
                Название файла
              </Label>
              <Input
                id="rename-input"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Например: product_preview.gif"
                maxLength={255}
                autoFocus
                onKeyDown={(e) => {
                  if (e.key === "Enter" && newName.trim() && renameItem) {
                    renameMutation.mutate({ id: renameItem.id, name: newName.trim() })
                  }
                }}
              />
            </div>
            <p className="text-[11px] text-muted-foreground font-mono truncate">
              Токен: {renameItem?.token}
            </p>
          </div>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="ghost" size="sm" onClick={() => setRenameItem(null)}>
              Отмена
            </Button>
            <Button
              size="sm"
              disabled={!newName.trim() || renameMutation.isPending}
              onClick={() => {
                if (renameItem && newName.trim()) {
                  renameMutation.mutate({ id: renameItem.id, name: newName.trim() })
                }
              }}
            >
              {renameMutation.isPending && <RotateCw className="size-3.5 animate-spin mr-1.5" />}
              Сохранить
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
