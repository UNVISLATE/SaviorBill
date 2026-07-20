import { useState } from "react"
import { Eye, ImageOff, Loader2, Trash2, Video } from "lucide-react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"
import { useInvalidateUserProfile } from "@/hooks/use-user-profile"
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/shadsnui/dialog"
import { Empty, EmptyDescription, EmptyMedia, EmptyTitle } from "@/components/shadsnui/empty"
import { Skeleton } from "@/components/shadsnui/skeleton"

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

export function ProfileMediaSection() {
  const qc = useQueryClient()
  const invalidateProfile = useInvalidateUserProfile()
  const [preview, setPreview] = useState<MediaItem | null>(null)
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

  if (!data || data.items.length === 0) {
    return (
      <Empty>
        <EmptyMedia>
          <ImageOff className="size-8 text-muted-foreground" />
        </EmptyMedia>
        <EmptyTitle>Нет загруженных файлов</EmptyTitle>
        <EmptyDescription>
          Загруженные аватары и другие ваши файлы появятся здесь.
          {quotaLabel && ` Доступно: ${quotaLabel}.`}
        </EmptyDescription>
      </Empty>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground">Ваши загрузки</span>
        <Badge variant="outline" className="text-[11px] font-normal">
          {quotaLabel ?? `${data.total} · безлимит`}
        </Badge>
      </div>
      <div className="grid grid-cols-3 gap-3">
        {data.items.map((m) => {
          const preview = m.thumb?.url ?? (m.kind === "image" ? m.media?.url : null)
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
              {preview ? (
                <img src={preview} alt="" className="size-full object-cover transition-transform duration-200 group-hover:scale-105" />
              ) : (
                <div className="flex size-full items-center justify-center bg-muted">
                  <Video className="size-6 text-muted-foreground" />
                </div>
              )}
              {/* Затемнение по всей карточке при наведении — иначе яркие фото
                  перекрывают статус/размер и делают их нечитаемыми. */}
              <div className="absolute inset-0 bg-black/0 transition-colors duration-150 group-hover:bg-black/50" />
              <Eye className="absolute top-1/2 left-1/2 size-6 -translate-x-1/2 -translate-y-1/2 text-white opacity-0 transition-opacity group-hover:opacity-100" />
              <div className="absolute inset-x-0 bottom-0 flex flex-col gap-0.5 bg-gradient-to-t from-black/80 to-transparent p-1.5">
                <div className="flex items-center justify-between gap-1">
                  <Badge variant={STATUS_VARIANT[m.status] ?? "outline"} className="text-[10px]">
                    {STATUS_LABEL[m.status] ?? m.status}
                  </Badge>
                  <span className="text-[10px] text-white/80">{fmtSize(m.size)}</span>
                </div>
                <span className="text-[10px] text-white/70 opacity-0 transition-opacity group-hover:opacity-100">
                  {fmtDateTime(m.created_at)}
                </span>
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
      {del.isError && (
        <p className="text-xs text-destructive">
          Не удалось удалить — возможно, файл ещё используется в заказе.
        </p>
      )}

      <Dialog open={!!preview} onOpenChange={(open) => !open && setPreview(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Просмотр файла</DialogTitle>
            <DialogDescription>
              {preview && (
                <>
                  {STATUS_LABEL[preview.status] ?? preview.status} · {fmtSize(preview.size)} ·
                  {" "}
                  {preview.mime ?? "—"} · загружено {fmtDateTime(preview.created_at)}
                </>
              )}
            </DialogDescription>
          </DialogHeader>
          {preview && (
            <div className="flex max-h-[70vh] items-center justify-center overflow-hidden rounded-lg bg-black/5">
              {preview.kind === "image" && (preview.media?.url ?? preview.url) ? (
                <img
                  src={preview.media?.url ?? preview.url}
                  alt=""
                  className="max-h-[70vh] w-full object-contain"
                />
              ) : preview.kind === "video" && (preview.media?.url ?? preview.url) ? (
                <video
                  src={preview.media?.url ?? preview.url}
                  controls
                  className="max-h-[70vh] w-full"
                />
              ) : (
                <div className="flex h-64 w-full items-center justify-center text-muted-foreground">
                  <Video className="size-8" />
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
