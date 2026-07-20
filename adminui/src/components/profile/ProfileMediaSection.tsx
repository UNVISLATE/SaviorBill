import { ImageOff, Loader2, Trash2, Video } from "lucide-react"
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
  media: MediaVariant | null
  thumb: MediaVariant | null
}

interface Page<T> {
  items: T[]
  total: number
}

const STATUS_VARIANT: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  ready: "default",
  processing: "secondary",
  queued: "secondary",
  failed: "destructive",
  error: "destructive",
}

function fmtSize(bytes: number | null): string {
  if (!bytes) return "—"
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} КБ`
  return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`
}

export function ProfileMediaSection() {
  const qc = useQueryClient()
  const invalidateProfile = useInvalidateUserProfile()
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

  if (!data || data.items.length === 0) {
    return (
      <Empty>
        <EmptyMedia>
          <ImageOff className="size-8 text-muted-foreground" />
        </EmptyMedia>
        <EmptyTitle>Нет загруженных файлов</EmptyTitle>
        <EmptyDescription>
          Загруженные аватары и другие ваши файлы появятся здесь.
        </EmptyDescription>
      </Empty>
    )
  }

  return (
    <div className="grid grid-cols-3 gap-3">
      {data.items.map((m) => {
        const preview = m.thumb?.url ?? (m.kind === "image" ? m.media?.url : null)
        const deleting = del.isPending && del.variables === m.token
        return (
          <div key={m.id} className="group relative aspect-square overflow-hidden rounded-lg border">
            {preview ? (
              <img src={preview} alt="" className="size-full object-cover" />
            ) : (
              <div className="flex size-full items-center justify-center bg-muted">
                <Video className="size-6 text-muted-foreground" />
              </div>
            )}
            <div className="absolute inset-x-0 bottom-0 flex items-center justify-between gap-1 bg-gradient-to-t from-black/70 to-transparent p-1.5">
              <Badge variant={STATUS_VARIANT[m.status] ?? "outline"} className="text-[10px]">
                {m.status}
              </Badge>
              <span className="text-[10px] text-white/80">{fmtSize(m.size)}</span>
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
                  >
                    {deleting ? (
                      <Loader2 className="size-3.5 animate-spin" />
                    ) : (
                      <Trash2 className="size-3.5" />
                    )}
                  </Button>
                }
              />
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
                  <AlertDialogAction onClick={() => del.mutate(m.token)}>
                    Удалить
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        )
      })}
      {del.isError && (
        <p className="col-span-3 text-xs text-destructive">
          Не удалось удалить — возможно, файл ещё используется в заказе.
        </p>
      )}
    </div>
  )
}
