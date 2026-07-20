import { useEffect, useRef, useState } from "react"
import { ImageOff, Loader2, Plus, Trash2, TriangleAlert, Video } from "lucide-react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"
import { beginOwnMediaUpload, type UploadProgress } from "@/lib/media-upload"
import { useInvalidateUserProfile } from "@/hooks/use-user-profile"
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
import { MediaLightbox } from "./MediaLightbox"

interface MediaVariant {
  key: string
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
}

interface Page<T> {
  items: T[]
  total: number
  quota_limit?: number | null
}

/** Один локальный (ещё не в списке с сервера) файл в процессе загрузки/конвертации. */
interface UploadJob {
  id: string
  previewUrl: string | null
  phase: "uploading" | "processing" | "done" | "error"
  uploadPct: number
  token: string | null
  convertPct: string | null
  etaSec: string | null
  error: string | null
}

const STATUS_VARIANT: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  ready: "default",
  processing: "secondary",
  queued: "secondary",
  failed: "destructive",
  error: "destructive",
}

const STATUS_LABEL: Record<string, string> = {
  ready: "готово",
  processing: "обработка",
  queued: "в очереди",
  failed: "ошибка",
  error: "ошибка",
}

function fmtSize(bytes: number | null): string {
  if (!bytes) return "—"
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} КБ`
  return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`
}

function fmtDateTime(iso: string): string {
  return new Date(iso).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

let jobSeq = 0

export function ProfileMediaSection() {
  const qc = useQueryClient()
  const invalidateProfile = useInvalidateUserProfile()
  const [preview, setPreview] = useState<MediaItem | null>(null)
  const [jobs, setJobs] = useState<UploadJob[]>([])
  const [dragOver, setDragOver] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const { data, isLoading } = useQuery({
    queryKey: ["user-media"],
    queryFn: async () =>
      (await api.get<Page<MediaItem>>("/v1/user/media", { params: { limit: 50 } })).data,
  })

  const del = useMutation({
    mutationFn: async (token: string) => {
      await api.delete(`/v1/user/media/${token}`)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["user-media"] })
      // Удалённое медиа могло быть аватаром — сервер сам его отвязывает,
      // но кэш профиля про это не знает без явного invalidate.
      invalidateProfile()
    },
  })

  // Живой статус конвертации всех токенов, ещё не готовых — один WS вместо
  // REST-поллинга на каждую карточку (см. hooks/use-media-status-ws.ts).
  const pendingTokens = jobs
    .filter((j) => j.phase === "processing" && j.token)
    .map((j) => j.token as string)
  const statuses = useMediaStatusStream(pendingTokens)

  useEffect(() => {
    if (pendingTokens.length === 0) return
    setJobs((prev) =>
      prev.map((j) => {
        if (j.phase !== "processing" || !j.token) return j
        const snap = statuses[j.token]
        if (!snap) return j
        if (snap.state === "ready") {
          return { ...j, phase: "done", convertPct: "100" }
        }
        if (snap.state === "error" || snap.state === "failed") {
          return { ...j, phase: "error", error: "не удалось обработать файл" }
        }
        return { ...j, convertPct: snap.percent ?? j.convertPct, etaSec: snap.eta_sec ?? j.etaSec }
      }),
    )
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statuses])

  const phaseKey = jobs.map((j) => `${j.id}:${j.phase}`).join(",")
  // Как только файл готов — обновить список с сервера и через секунду убрать
  // временную плитку (за это время видно "готово" вместо мгновенного скачка).
  useEffect(() => {
    const doneIds = jobs.filter((j) => j.phase === "done").map((j) => j.id)
    if (doneIds.length === 0) return
    qc.invalidateQueries({ queryKey: ["user-media"] })
    const t = setTimeout(() => {
      setJobs((prev) => prev.filter((j) => !doneIds.includes(j.id)))
    }, 1200)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phaseKey])

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
      beginOwnMediaUpload(file, {
        onProgress: (p: UploadProgress) => {
          const pct = p.total ? Math.round((p.loaded / p.total) * 100) : 0
          setJobs((prev) => prev.map((j) => (j.id === id ? { ...j, uploadPct: pct } : j)))
        },
      })
        .then(({ token }) => {
          setJobs((prev) => prev.map((j) => (j.id === id ? { ...j, phase: "processing", token } : j)))
        })
        .catch((err) => {
          const msg =
            err?.response?.data?.detail ?? err?.message ?? "не удалось загрузить файл"
          setJobs((prev) => prev.map((j) => (j.id === id ? { ...j, phase: "error", error: String(msg) } : j)))
        })
    }
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragOver(false)
    if (e.dataTransfer.files?.length) startUploads(e.dataTransfer.files)
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
  const quotaReached = data?.quota_limit != null && data.total >= data.quota_limit

  const uploadTile = (
    <button
      type="button"
      onClick={() => !quotaReached && fileInputRef.current?.click()}
      disabled={quotaReached}
      className="group relative flex aspect-square flex-col items-center justify-center gap-1 rounded-lg border border-dashed text-muted-foreground transition-colors hover:border-foreground/40 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
    >
      <Plus className="size-5" />
      <span className="text-[10px]">Загрузить</span>
    </button>
  )

  const hasItems = !!data && data.items.length > 0
  const hasAnything = hasItems || jobs.length > 0

  return (
    <div className="space-y-3">
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

      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground">Ваши загрузки</span>
        <Badge variant={quotaReached ? "destructive" : "outline"} className="text-[11px] font-normal">
          {quotaLabel ?? `${data?.total ?? 0} · безлимит`}
        </Badge>
      </div>

      {!hasAnything ? (
        <div
          onDragOver={(e) => {
            e.preventDefault()
            setDragOver(true)
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          className={`rounded-lg border-2 border-dashed p-2 transition-colors ${dragOver ? "border-foreground/50 bg-foreground/5" : "border-transparent"}`}
        >
          <Empty>
            <EmptyMedia>
              <ImageOff className="size-8 text-muted-foreground" />
            </EmptyMedia>
            <EmptyTitle>Нет загруженных файлов</EmptyTitle>
            <EmptyDescription>
              Перетащите фото или видео сюда, либо нажмите ниже, чтобы выбрать файл.
            </EmptyDescription>
          </Empty>
          <div className="mx-auto mt-3 w-24">{uploadTile}</div>
        </div>
      ) : (
        <div
          onDragOver={(e) => {
            e.preventDefault()
            setDragOver(true)
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          className={`grid grid-cols-3 gap-3 rounded-lg p-1 transition-colors ${dragOver ? "bg-foreground/5 ring-2 ring-dashed ring-foreground/30" : ""}`}
        >
          {!quotaReached && uploadTile}

          {jobs.map((j) => (
            <div key={j.id} className="relative aspect-square overflow-hidden rounded-lg border bg-muted">
              {j.previewUrl ? (
                <img src={j.previewUrl} alt="" className="size-full object-cover opacity-60" />
              ) : (
                <div className="flex size-full items-center justify-center">
                  <Video className="size-6 text-muted-foreground" />
                </div>
              )}
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-1.5 bg-black/40 p-2 text-center text-white">
                {j.phase === "error" ? (
                  <>
                    <TriangleAlert className="size-5 text-destructive" />
                    <span className="line-clamp-2 text-[10px]">{j.error}</span>
                  </>
                ) : j.phase === "done" ? (
                  <span className="text-[11px] font-medium">Готово ✓</span>
                ) : (
                  <>
                    <Loader2 className="size-4 animate-spin" />
                    <span className="text-[10px]">
                      {j.phase === "uploading" ? `Загрузка ${j.uploadPct}%` : "Обработка…"}
                      {j.phase === "processing" && j.convertPct ? ` ${j.convertPct}%` : ""}
                    </span>
                    <Progress
                      value={j.phase === "uploading" ? j.uploadPct : Number(j.convertPct ?? 0)}
                      className="w-full px-1"
                    />
                    {j.phase === "processing" && j.etaSec && (
                      <span className="text-[9px] text-white/70">≈{j.etaSec}с</span>
                    )}
                  </>
                )}
              </div>
            </div>
          ))}

          {data?.items.map((m) => {
            const thumbUrl = m.thumb?.url ?? (m.kind === "image" ? m.media?.url : null)
            const deleting = del.isPending && del.variables === m.token
            return (
              <div
                key={m.id}
                role="button"
                tabIndex={0}
                onClick={() => setPreview(m)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") setPreview(m)
                }}
                className="group relative aspect-square cursor-pointer overflow-hidden rounded-lg border text-left"
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
                {/* Затемнение по всей карточке при наведении — иначе яркие фото
                    перекрывают статус/размер и делают их нечитаемыми. */}
                <div className="absolute inset-0 bg-black/0 transition-colors duration-150 group-hover:bg-black/50" />
                {/* Низ карточки — единая панель без резервирования пустого места:
                    строка даты раскрывается по max-height только на hover, чтобы
                    в покое бейдж/размер не "висели" выше нижнего края с зазором. */}
                <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/85 via-black/40 to-transparent px-1.5 pt-4 pb-1.5">
                  <span className="block max-h-0 overflow-hidden text-[10px] text-white/70 opacity-0 transition-all duration-150 group-hover:mb-1 group-hover:max-h-4 group-hover:opacity-100">
                    {fmtDateTime(m.created_at)}
                  </span>
                  <div className="flex items-center justify-between gap-1">
                    <Badge variant={STATUS_VARIANT[m.status] ?? "outline"} className="text-[10px]">
                      {STATUS_LABEL[m.status] ?? m.status}
                    </Badge>
                    <span className="text-[10px] text-white/80">{fmtSize(m.size)}</span>
                  </div>
                </div>
                <AlertDialog>
                  <AlertDialogTrigger
                    render={
                      <Button
                        type="button"
                        size="icon-sm"
                        variant="destructive"
                        className="absolute top-1.5 right-1.5 opacity-0 transition-opacity group-hover:opacity-100"
                        disabled={deleting}
                        onClick={(e) => e.stopPropagation()}
                      >
                        {deleting ? (
                          <Loader2 className="size-3.5 animate-spin" />
                        ) : (
                          <Trash2 className="size-3.5" />
                        )}
                      </Button>
                    }
                  />
                  <AlertDialogContent onClick={(e) => e.stopPropagation()}>
                    <AlertDialogHeader>
                      <AlertDialogTitle>Удалить файл?</AlertDialogTitle>
                      <AlertDialogDescription>
                        Файл будет удалён без возможности восстановления. Если он используется
                        как аватар — аватар будет сброшен.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>Отмена</AlertDialogCancel>
                      <AlertDialogAction onClick={() => del.mutate(m.token)}>
                        Удалить
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              </div>
            )
          })}
        </div>
      )}

      {del.isError && (
        <p className="text-xs text-destructive">
          Не удалось удалить — возможно, файл ещё используется в заказе.
        </p>
      )}

      {preview && (
        <MediaLightbox
          onClose={() => setPreview(null)}
          caption={
            <>
              {STATUS_LABEL[preview.status] ?? preview.status} · {fmtSize(preview.size)} ·{" "}
              {preview.mime ?? "—"} · загружено {fmtDateTime(preview.created_at)}
            </>
          }
        >
          {preview.kind === "image" && (preview.media?.url ?? preview.url) ? (
            <img
              src={preview.media?.url ?? preview.url}
              alt=""
              className="max-h-[75vh] max-w-full object-contain"
            />
          ) : preview.kind === "video" && (preview.media?.url ?? preview.url) ? (
            <video
              src={preview.media?.url ?? preview.url}
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
}
