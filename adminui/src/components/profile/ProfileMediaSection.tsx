import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react"
import {
  Check,
  Clock,
  Copy,
  Download,
  Eye,
  ImageOff,
  Images,
  Loader2,
  Plus,
  PlayCircle,
  RotateCcw,
  ShieldOff,
  Trash2,
  TriangleAlert,
  Video,
  X,
} from "lucide-react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"
import { beginOwnMediaUpload, type UploadProgress } from "@/lib/media-upload"
import { fmtDateTime, fmtEta, fmtSize, STATUS_LABEL, STATUS_VARIANT } from "@/lib/media-format"
import { useInvalidateUserProfile } from "@/hooks/use-user-profile"
import { useAuth } from "@/hooks/use-auth"
import { useMediaStatusStream } from "@/hooks/use-media-status-ws"
import { Badge } from "@/components/shadsnui/badge"
import { Button } from "@/components/shadsnui/button"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/shadsnui/alert-dialog"
import { Progress } from "@/components/shadsnui/progress"
import { Empty, EmptyDescription, EmptyMedia, EmptyTitle } from "@/components/shadsnui/empty"
import { Skeleton } from "@/components/shadsnui/skeleton"
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuTrigger,
} from "@/components/shadsnui/context-menu"
import { MediaLightbox } from "./MediaLightbox"
import { MediaPreviewGallery } from "./MediaPreviewGallery"

interface MediaVariant {
  mime: string | null
  size: number | null
  url: string
}

interface MediaItem {
  id: number
  token: string
  kind: string
  tag: string | null
  status: string
  url: string
  mime: string | null
  size: number | null
  created_at: string
  media: MediaVariant | null
  thumb: MediaVariant | null
  previews: MediaVariant[]
  meta: Record<string, number>
}

interface Page<T> {
  items: T[]
  total: number
  quota_limit?: number | null
}

/** Один локальный (ещё не в списке с сервера) файл в процессе загрузки/конвертации.
 * ``file: null`` — джоба восстановлена после перезагрузки страницы из
 * ``GET /v1/user/media/jobs`` (см. эффект восстановления ниже): исходного
 * File-объекта у нас уже нет, поэтому повторная загрузка для такой джобы
 * недоступна (см. ``UploadPlaceholder`` — кнопка "Повторить" скрыта). */
interface UploadJob {
  id: string
  file: File | null
  previewUrl: string | null
  phase: "uploading" | "queued" | "processing" | "done" | "error"
  uploadPct: number
  token: string | null
  convertPct: number | null
  etaSec: number | null
  error: string | null
}

let jobSeq = 0

/** Ячейка объединённого грида (§5.2) — либо ещё загружаемый job, либо готовый item, либо и то, и то. */
interface Cell {
  key: string
  job?: UploadJob
  item?: MediaItem
}

/** Джоба из GET /v1/user/media/jobs (см. src/api/v1/user/media.py). */
interface ActiveJobDto {
  token: string
  op: string
  state: string
  error: string | null
  percent: number | null
  eta_sec: number | null
}

/** Императивный хендл секции — drag&drop живёт на уровне всего диалога
 * профиля (ProfileDialogHost), а не только над этим блоком, поэтому хост
 * должен уметь передать сюда файлы из глобального onDrop. */
export interface MediaSectionHandle {
  startUploads: (files: FileList | File[]) => void
}

export const ProfileMediaSection = forwardRef<MediaSectionHandle, { mode: "own" | "view"; userId?: number }>(
  function ProfileMediaSection({ mode, userId }, ref) {
  const isOwn = mode === "own"
  const qc = useQueryClient()
  const { can } = useAuth()
  const invalidateProfile = useInvalidateUserProfile()
  const [previewIndex, setPreviewIndex] = useState<number | null>(null)
  const [galleryToken, setGalleryToken] = useState<string | null>(null)
  const [jobs, setJobs] = useState<UploadJob[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const fileInputRef = useRef<HTMLInputElement>(null)
  const longPressTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const canRead = isOwn || can("media.read")
  const canDelete = isOwn || can("media.delete")
  const mediaQueryKey = isOwn ? ["user-media"] : ["admin-user-media", userId]

  const { data, isLoading } = useQuery({
    queryKey: mediaQueryKey,
    queryFn: async () =>
      (
        await api.get<Page<MediaItem>>(isOwn ? "/v1/user/media" : "/v1/admin/media", {
          params: isOwn ? { limit: 50 } : { limit: 50, owner_id: userId },
        })
      ).data,
    enabled: canRead,
  })

  const del = useMutation({
    mutationFn: async (item: MediaItem) => {
      if (isOwn) {
        await api.delete(`/v1/user/media/${item.token}`)
      } else {
        await api.delete(`/v1/admin/media/${item.id}`)
      }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: mediaQueryKey })
      // Удалённое медиа могло быть аватаром — сервер сам его отвязывает,
      // но кэш профиля про это не знает без явного invalidate.
      if (isOwn) invalidateProfile()
    },
  })

  const bulkDelete = useMutation({
    mutationFn: async (items: MediaItem[]) => {
      await Promise.all(
        items.map((item) =>
          isOwn ? api.delete(`/v1/user/media/${item.token}`) : api.delete(`/v1/admin/media/${item.id}`),
        ),
      )
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: mediaQueryKey })
      if (isOwn) invalidateProfile()
      setSelected(new Set())
    },
  })

  // Живой статус конвертации всех токенов, ещё не готовых — один WS вместо
  // REST-поллинга на каждую карточку (см. hooks/use-media-status-ws.ts).
  // В режиме просмотра чужого профиля загрузок не бывает (нет
  // "загрузить за другого"), поэтому jobs всегда пуст — стрим не открывается.
  const pendingTokens = jobs
    .filter((j) => (j.phase === "processing" || j.phase === "queued") && j.token)
    .map((j) => j.token as string)
  const statuses = useMediaStatusStream(pendingTokens)

  // Наложение live-статуса из WS на локальные джобы — производное значение,
  // считается прямо при рендере, а не через setState в эффекте (см.
  // react-hooks/set-state-in-effect: запись состояния синхронно в эффекте
  // даёт каскадные ре-рендеры). Базовое ``jobs`` при этом не мутируется —
  // сравнение фаз/прогресса ниже (phaseKey, doneIds) идёт уже по этой,
  // производной, версии.
  const displayJobs: UploadJob[] = jobs.map((j) => {
    if ((j.phase !== "processing" && j.phase !== "queued") || !j.token) return j
    const snap = statuses[j.token]
    if (!snap) return j
    if (snap.state === "ready") {
      return { ...j, phase: "done", convertPct: 100 }
    }
    if (snap.state === "error" || snap.state === "failed") {
      return { ...j, phase: "error", error: "не удалось обработать файл" }
    }
    return {
      ...j,
      // Мы переводим job в "processing" сразу после успешной загрузки
      // (см. runUpload), но воркер мог ещё не забрать задачу из очереди —
      // реальная фаза (queued/processing) приходит именно из snap.state.
      phase: snap.state === "queued" ? "queued" : "processing",
      convertPct: snap.percent != null ? Number(snap.percent) : j.convertPct,
      etaSec: snap.eta_sec != null ? Number(snap.eta_sec) : j.etaSec,
    }
  })

  const phaseKey = displayJobs.map((j) => `${j.id}:${j.phase}`).join(",")
  // Как только файл готов — обновить список с сервера и через секунду убрать
  // временную джобу (реальная карточка к этому моменту уже отрисована по
  // тому же токену — см. cells ниже, поэтому визуально ничего не "прыгает").
  useEffect(() => {
    const doneIds = displayJobs.filter((j) => j.phase === "done").map((j) => j.id)
    if (doneIds.length === 0) return
    qc.invalidateQueries({ queryKey: mediaQueryKey })
    const t = setTimeout(() => {
      setJobs((prev) => prev.filter((j) => !doneIds.includes(j.id)))
    }, 1200)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phaseKey])

  // Восстановление карточек "в обработке" после перезагрузки страницы —
  // WS /api/media/mine покрывает только live-обновления в рамках одной
  // сессии вкладки, само по себе не переживает reload (см. §3.Д).
  useEffect(() => {
    if (!isOwn) return
    let cancelled = false
    api
      .get<ActiveJobDto[]>("/v1/user/media/jobs")
      .then(({ data: active }) => {
        if (cancelled) return
        const restored = active
          .filter((j) => j.op === "convert" && (j.state === "queued" || j.state === "processing"))
          .map<UploadJob>((j) => ({
            id: `restored:${j.token}`,
            file: null,
            previewUrl: null,
            phase: j.state === "queued" ? "queued" : "processing",
            uploadPct: 100,
            token: j.token,
            convertPct: j.percent,
            etaSec: j.eta_sec,
            error: j.error,
          }))
        if (restored.length === 0) return
        setJobs((prev) => {
          const known = new Set(prev.map((j) => j.token).filter(Boolean))
          return [...restored.filter((j) => !known.has(j.token)), ...prev]
        })
      })
      .catch(() => {
        // восстановление — best-effort, не ломаем страницу, если джобы не отдались
      })
    return () => {
      cancelled = true
    }
  }, [isOwn])

  function startUploads(files: FileList | File[]) {
    const list = Array.from(files).filter(
      (f) => f.type.startsWith("image/") || f.type.startsWith("video/"),
    )
    for (const file of list) {
      const id = `up${++jobSeq}`
      const previewUrl = file.type.startsWith("image/") ? URL.createObjectURL(file) : null
      setJobs((prev) => [
        {
          id,
          file,
          previewUrl,
          phase: "uploading",
          uploadPct: 0,
          token: null,
          convertPct: null,
          etaSec: null,
          error: null,
        },
        ...prev,
      ])
      runUpload(id, file)
    }
  }

  useImperativeHandle(ref, () => ({ startUploads }))

  function runUpload(id: string, file: File) {
    beginOwnMediaUpload(file, {
      onProgress: (p: UploadProgress) => {
        const pct = p.total ? Math.round((p.loaded / p.total) * 100) : 0
        setJobs((prev) => prev.map((j) => (j.id === id ? { ...j, uploadPct: pct } : j)))
      },
    })
      .then(({ token }) => {
        setJobs((prev) => prev.map((j) => (j.id === id ? { ...j, phase: "queued", token } : j)))
      })
      .catch((err) => {
        const msg = err?.response?.data?.detail ?? err?.message ?? "не удалось загрузить файл"
        setJobs((prev) => prev.map((j) => (j.id === id ? { ...j, phase: "error", error: String(msg) } : j)))
      })
  }

  function retryJob(job: UploadJob) {
    if (!job.file) return
    setJobs((prev) =>
      prev.map((j) =>
        j.id === job.id ? { ...j, phase: "uploading", uploadPct: 0, token: null, error: null } : j,
      ),
    )
    runUpload(job.id, job.file)
  }

  function toggleSelect(token: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(token)) next.delete(token)
      else next.add(token)
      return next
    })
  }

  function onCardPointerDown(token: string) {
    if (!canDelete) return
    longPressTimer.current = setTimeout(() => toggleSelect(token), 500)
  }
  function onCardPointerUp() {
    if (longPressTimer.current) clearTimeout(longPressTimer.current)
  }

  async function copyLink(item: MediaItem) {
    const url = item.media?.url ?? item.url
    await navigator.clipboard.writeText(`${location.origin}${url}`)
  }

  // §5.2 — один источник ячеек грида вместо двух параллельных списков
  // (jobs / data.items): токен, покрытый активной джобой, не рендерится
  // отдельным элементом из data.items — иначе на время до её угасания файл
  // виден дважды и потом "прыгает" на новое место.
  // ВАЖНО: хук должен идти до ранних `return` ниже (Rules of Hooks) — иначе
  // при переходе isLoading true -> false число вызванных хуков меняется
  // между рендерами, и React рушит всё дерево без ErrorBoundary (чёрный экран).
  const cells: Cell[] = useMemo(() => {
    const coveredTokens = new Set(displayJobs.filter((j) => j.token).map((j) => j.token as string))
    const byToken = new Map((data?.items ?? []).map((m) => [m.token, m]))
    const jobCells: Cell[] = displayJobs.map((j) => ({
      key: j.id,
      job: j,
      item: j.token ? byToken.get(j.token) : undefined,
    }))
    const itemCells: Cell[] = (data?.items ?? [])
      .filter((m) => !coveredTokens.has(m.token))
      .map((m) => ({ key: `item:${m.token}`, item: m }))
    return [...jobCells, ...itemCells]
  }, [displayJobs, data])

  if (!canRead) {
    return (
      <Empty>
        <EmptyMedia>
          <ShieldOff className="size-8 text-muted-foreground" />
        </EmptyMedia>
        <EmptyTitle>Недостаточно прав</EmptyTitle>
        <EmptyDescription>Нужно право media.read, чтобы смотреть чужие медиа.</EmptyDescription>
      </Empty>
    )
  }

  if (isLoading) {
    return (
      <div className="grid grid-cols-3 gap-3">
        <Skeleton className="aspect-square w-full rounded-lg" />
        <Skeleton className="aspect-square w-full rounded-lg" />
        <Skeleton className="aspect-square w-full rounded-lg" />
      </div>
    )
  }

  const quotaLabel =
    data && data.quota_limit != null ? `${data.total} / ${data.quota_limit}` : null
  const quotaReached = isOwn && data?.quota_limit != null && data.total >= data.quota_limit

  const readyItems = (data?.items ?? []).filter((m) => m.status === "ready")
  const previewItem = previewIndex != null ? readyItems[previewIndex] : null

  const uploadTile = isOwn ? (
    <button
      type="button"
      onClick={() => !quotaReached && fileInputRef.current?.click()}
      disabled={quotaReached}
      className="group relative flex aspect-square flex-col items-center justify-center gap-1 rounded-lg border border-dashed text-muted-foreground transition-colors hover:border-foreground/40 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
    >
      <Plus className="size-5" />
      <span className="text-[10px]">Загрузить</span>
    </button>
  ) : null

  const hasAnything = cells.length > 0

  // §5.1 — "Подробности" видео открывается как страница на месте списка
  // медиа (с возвратом по стрелке назад), а не отдельным слоем-просмотром.
  const galleryMedia = galleryToken ? (data?.items ?? []).find((it) => it.token === galleryToken) ?? null : null
  if (galleryMedia) {
    return (
      <div className="flex h-full min-h-[320px] flex-col">
        <MediaPreviewGallery
          media={galleryMedia}
          queryKey={mediaQueryKey}
          onClose={() => setGalleryToken(null)}
        />
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-[320px] flex-col space-y-3">
      {isOwn && (
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*,video/*"
          multiple
          className="hidden"
          onChange={(e) => {
            if (e.target.files?.length) startUploads(e.target.files)
            e.target.value = ""
          }}
        />
      )}

      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground">
          {selected.size > 0
            ? `Выбрано: ${selected.size}`
            : isOwn
              ? "Ваши загрузки"
              : "Загрузки пользователя"}
        </span>
        <div className="flex items-center gap-1.5">
          {selected.size > 0 ? (
            <>
              <AlertDialog>
                <AlertDialogTrigger
                  render={
                    <Button type="button" size="sm" variant="destructive" disabled={bulkDelete.isPending}>
                      {bulkDelete.isPending ? (
                        <Loader2 className="size-3.5 animate-spin" />
                      ) : (
                        <Trash2 className="size-3.5" />
                      )}
                      Удалить выбранные
                    </Button>
                  }
                />
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Удалить {selected.size} файлов?</AlertDialogTitle>
                    <AlertDialogDescription>
                      Файлы будут удалены без возможности восстановления.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Отмена</AlertDialogCancel>
                    <AlertDialogAction
                      onClick={() =>
                        bulkDelete.mutate(
                          (data?.items ?? []).filter((m) => selected.has(m.token)),
                        )
                      }
                    >
                      Удалить
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
              <Button type="button" size="icon-sm" variant="ghost" onClick={() => setSelected(new Set())}>
                <X className="size-3.5" />
              </Button>
            </>
          ) : (
            <Badge variant={quotaReached ? "destructive" : "outline"} className="text-[11px] font-normal">
              {quotaLabel ?? `${data?.total ?? 0}${isOwn ? " · безлимит" : ""}`}
            </Badge>
          )}
        </div>
      </div>

      {/* Drag&drop теперь висит на всём диалоге профиля (см.
          ProfileDialogHost) — на этой панели больше нет своих
          onDragOver/onDrop, только flex-1, чтобы дочерний Empty корректно
          центрировался на всю доступную высоту. */}
      <div className="relative flex-1 min-h-[220px] rounded-lg">
        <div className="flex h-full flex-col gap-3 p-1">
          {(isOwn || cells.length > 0) && (
            <div className="grid grid-cols-3 gap-3">
              {!quotaReached && uploadTile}
              {cells.map((cell) => (
                <MediaCard
                  key={cell.key}
                  cell={cell}
                  canDelete={canDelete}
                  deleting={del.isPending && del.variables?.token === cell.item?.token}
                  selected={cell.item ? selected.has(cell.item.token) : false}
                  selectMode={selected.size > 0}
                  onOpen={() => {
                    if (!cell.item || cell.item.status !== "ready") return
                    const idx = readyItems.findIndex((m) => m.token === cell.item!.token)
                    if (idx >= 0) setPreviewIndex(idx)
                  }}
                  onToggleSelect={() => cell.item && toggleSelect(cell.item.token)}
                  onPointerDown={() => cell.item && onCardPointerDown(cell.item.token)}
                  onPointerUp={onCardPointerUp}
                  onDelete={() => cell.item && del.mutate(cell.item)}
                  onRetry={() => cell.job && retryJob(cell.job)}
                  onOpenGallery={() => cell.item && setGalleryToken(cell.item.token)}
                  onCopyLink={() => cell.item && copyLink(cell.item)}
                />
              ))}
            </div>
          )}

          {/* §5.1 — то же пустое состояние, что и на остальных вкладках
              профиля (Empty/EmptyMedia/EmptyTitle/EmptyDescription), просто
              центрированное в оставшемся месте, а не отдельная плитка в гриде. */}
          {!hasAnything && (
            <div className="flex flex-1 items-center justify-center">
              <Empty>
                <EmptyMedia>
                  <ImageOff className="size-8 text-muted-foreground" />
                </EmptyMedia>
                <EmptyTitle>Нет файлов</EmptyTitle>
                <EmptyDescription>
                  {isOwn
                    ? "Перетащите файл сюда или нажмите «Загрузить»"
                    : "У пользователя нет загруженных файлов"}
                </EmptyDescription>
              </Empty>
            </div>
          )}
        </div>
      </div>

      {del.isError && (
        <p className="text-xs text-destructive">
          Не удалось удалить — возможно, файл ещё используется в заказе.
        </p>
      )}

      {previewItem && (
        <MediaLightbox
          onClose={() => setPreviewIndex(null)}
          onPrev={
            readyItems.length > 1
              ? () => setPreviewIndex((i) => ((i ?? 0) - 1 + readyItems.length) % readyItems.length)
              : undefined
          }
          onNext={
            readyItems.length > 1 ? () => setPreviewIndex((i) => ((i ?? 0) + 1) % readyItems.length) : undefined
          }
          caption={
            <>
              {STATUS_LABEL[previewItem.status] ?? previewItem.status} · {fmtSize(previewItem.size)} ·{" "}
              {previewItem.mime ?? "—"} · загружено {fmtDateTime(previewItem.created_at)}
            </>
          }
        >
          {previewItem.kind === "image" && (previewItem.media?.url ?? previewItem.url) ? (
            <img
              src={previewItem.media?.url ?? previewItem.url}
              alt=""
              className="max-h-[75vh] max-w-full object-contain"
            />
          ) : previewItem.kind === "video" && (previewItem.media?.url ?? previewItem.url) ? (
            <video
              src={previewItem.media?.url ?? previewItem.url}
              controls
              autoPlay
              className="max-h-[75vh] max-w-full"
            />
          ) : (
            <div className="flex h-64 w-64 items-center justify-center bg-muted text-muted-foreground">
              <Video className="size-8" />
            </div>
          )}
        </MediaLightbox>
      )}
    </div>
  )
})

ProfileMediaSection.displayName = "ProfileMediaSection"

function MediaCard({
  cell,
  canDelete,
  deleting,
  selected,
  selectMode,
  onOpen,
  onToggleSelect,
  onPointerDown,
  onPointerUp,
  onDelete,
  onRetry,
  onOpenGallery,
  onCopyLink,
}: {
  cell: Cell
  canDelete: boolean
  deleting: boolean
  selected: boolean
  selectMode: boolean
  onOpen: () => void
  onToggleSelect: () => void
  onPointerDown: () => void
  onPointerUp: () => void
  onDelete: () => void
  onRetry: () => void
  onOpenGallery: () => void
  onCopyLink: () => void
}) {
  const { job, item } = cell
  const [confirmOpen, setConfirmOpen] = useState(false)

  // Джоба ещё без токена/данных из /media — временная плитка-заглушка
  // (единственный оставшийся случай отдельного рендера, см. §5.2).
  if (job && !item) {
    return <UploadPlaceholder job={job} onRetry={onRetry} />
  }
  if (!item) return null

  const thumbUrl = item.thumb?.url ?? (item.kind === "image" ? item.media?.url : null)
  const isVideo = item.kind === "video"
  const showOverlay = job && job.phase !== "done"

  const card = (
    <div
      role="button"
      tabIndex={0}
      onClick={() => {
        if (selectMode) onToggleSelect()
        else onOpen()
      }}
      onKeyDown={(e) => {
        if (e.key !== "Enter" && e.key !== " ") return
        if (selectMode) onToggleSelect()
        else onOpen()
      }}
      onPointerDown={onPointerDown}
      onPointerUp={onPointerUp}
      onPointerLeave={onPointerUp}
      className="group relative aspect-square cursor-pointer overflow-hidden rounded-lg border text-left select-none"
    >
      {thumbUrl ? (
        <img
          src={thumbUrl}
          alt=""
          className="size-full object-cover transition-transform duration-200 group-hover:scale-105"
        />
      ) : (
        <div className="flex size-full items-center justify-center bg-muted">
          <Video className="size-6 text-muted-foreground" />
        </div>
      )}

      {/* §5.5 — постоянный бейдж "это видео" независимо от наличия thumb. */}
      {isVideo && (
        <span className="absolute top-1.5 left-1.5 flex items-center gap-0.5 rounded-md bg-black/60 px-1 py-0.5 text-white">
          <Video className="size-3" />
        </span>
      )}

      {/* Затемнение по всей карточке при наведении — иначе яркие фото
          перекрывают статус/размер и делают их нечитаемыми. */}
      <div className="absolute inset-0 bg-black/0 transition-colors duration-150 group-hover:bg-black/50" />

      {/* §5.5 — иконка действия на hover, разная для видео/фото. */}
      {!selectMode && (
        <div className="absolute inset-0 flex items-center justify-center opacity-0 transition-opacity group-hover:opacity-100">
          {isVideo ? (
            <PlayCircle className="size-8 text-white drop-shadow" />
          ) : (
            <Eye className="size-7 text-white drop-shadow" />
          )}
        </div>
      )}

      {/* Низ карточки — единая панель без резервирования пустого места:
          строка даты раскрывается по max-height только на hover, чтобы
          в покое бейдж/размер не "висели" выше нижнего края с зазором. */}
      <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/85 via-black/40 to-transparent px-1.5 pt-4 pb-1.5">
        <span className="block max-h-0 overflow-hidden text-[10px] text-white/70 opacity-0 transition-all duration-150 group-hover:mb-1 group-hover:max-h-4 group-hover:opacity-100">
          {fmtDateTime(item.created_at)}
        </span>
        <div className="flex items-center justify-between gap-1">
          <Badge variant={STATUS_VARIANT[item.status] ?? "outline"} className="text-[10px]">
            {STATUS_LABEL[item.status] ?? item.status}
          </Badge>
          <span className="text-[10px] text-white/80">{fmtSize(item.size)}</span>
        </div>
      </div>

      {canDelete && (
        <button
          type="button"
          aria-label={selected ? "Убрать выделение" : "Выделить"}
          onClick={(e) => {
            e.stopPropagation()
            onToggleSelect()
          }}
          className={`absolute top-1.5 right-1.5 flex size-5 items-center justify-center rounded-md border transition-opacity ${selected ? "border-primary bg-primary text-primary-foreground opacity-100" : "border-white/60 bg-black/40 text-transparent opacity-0 group-hover:opacity-100"}`}
        >
          <Check className="size-3" />
        </button>
      )}

      {showOverlay && (
        <ProgressOverlay convertPct={job!.convertPct} etaSec={job!.etaSec} phase={job!.phase} error={job!.error} />
      )}
    </div>
  )

  return (
    <>
      <ContextMenu>
        <ContextMenuTrigger>{card}</ContextMenuTrigger>
        <ContextMenuContent>
          {isVideo && (
            <ContextMenuItem onClick={onOpenGallery}>
              <Images className="size-4" />
              Подробности
            </ContextMenuItem>
          )}
          <ContextMenuItem
            onClick={() => {
              const a = document.createElement("a")
              a.href = item.media?.url ?? item.url
              a.download = ""
              a.click()
            }}
          >
            <Download className="size-4" />
            Скачать
          </ContextMenuItem>
          <ContextMenuItem onClick={onCopyLink}>
            <Copy className="size-4" />
            Скопировать ссылку
          </ContextMenuItem>
          {canDelete && (
            <>
              <ContextMenuSeparator />
              <ContextMenuItem variant="destructive" onClick={() => setConfirmOpen(true)}>
                <Trash2 className="size-4" />
                Удалить
              </ContextMenuItem>
            </>
          )}
        </ContextMenuContent>
      </ContextMenu>

      {canDelete && (
        <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Удалить файл?</AlertDialogTitle>
              <AlertDialogDescription>
                Файл будет удалён без возможности восстановления. Если он используется
                как аватар — аватар будет сброшен.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Отмена</AlertDialogCancel>
              <AlertDialogAction disabled={deleting} onClick={onDelete}>
                {deleting ? <Loader2 className="size-3.5 animate-spin" /> : "Удалить"}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      )}
    </>
  )
}

function UploadPlaceholder({ job, onRetry }: { job: UploadJob; onRetry: () => void }) {
  return (
    <div className="relative aspect-square overflow-hidden rounded-lg border bg-muted">
      {job.previewUrl ? (
        <img src={job.previewUrl} alt="" className="size-full object-cover opacity-60" />
      ) : (
        <div className="flex size-full items-center justify-center">
          <Video className="size-6 text-muted-foreground" />
        </div>
      )}
      <div className="absolute inset-0 flex flex-col items-center justify-center gap-1.5 bg-black/40 p-2 text-center text-white">
        {job.phase === "error" ? (
          <>
            <TriangleAlert className="size-5 text-destructive" />
            <span className="line-clamp-2 text-[10px]">{job.error}</span>
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="mt-1 h-6 px-2 text-[10px]"
              onClick={onRetry}
            >
              <RotateCcw className="size-3" />
              Повторить
            </Button>
          </>
        ) : (
          <ProgressOverlayBody
            convertPct={job.convertPct}
            etaSec={job.etaSec}
            phase={job.phase}
            error={job.error}
            uploadPct={job.uploadPct}
          />
        )}
      </div>
    </div>
  )
}

function ProgressOverlayBody({
  phase,
  uploadPct,
  convertPct,
  etaSec,
  error,
}: {
  phase: UploadJob["phase"]
  uploadPct?: number
  convertPct: number | null
  etaSec: number | null
  error: string | null
}) {
  const eta = fmtEta(etaSec)
  if (phase === "error") {
    return (
      <>
        <TriangleAlert className="size-5 text-destructive" />
        <span className="line-clamp-2 text-[10px]">{error}</span>
      </>
    )
  }
  if (phase === "done") {
    return <span className="text-[11px] font-medium">Готово ✓</span>
  }
  if (phase === "queued") {
    return (
      <>
        <Clock className="size-4" />
        <span className="text-[10px]">В очереди…</span>
      </>
    )
  }
  return (
    <>
      <Loader2 className="size-4 animate-spin" />
      <span className="text-[10px]">
        {phase === "uploading" ? `Загрузка ${uploadPct ?? 0}%` : "Обработка…"}
        {phase === "processing" && convertPct != null ? ` ${Math.round(convertPct)}%` : ""}
      </span>
      <Progress value={phase === "uploading" ? uploadPct ?? 0 : convertPct ?? 0} className="w-full px-1" />
      {phase === "processing" && eta && <span className="text-[9px] text-white/70">{eta}</span>}
    </>
  )
}

function ProgressOverlay(props: {
  phase: UploadJob["phase"]
  convertPct: number | null
  etaSec: number | null
  error: string | null
}) {
  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center gap-1.5 bg-black/40 p-2 text-center text-white">
      <ProgressOverlayBody {...props} />
    </div>
  )
}
