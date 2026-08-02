import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { ImageOff } from "lucide-react"

import { api } from "@/api/api.ts"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/shadsnui/dialog"
import { Input } from "@/components/shadsnui/input"
import { Badge } from "@/components/shadsnui/badge"

interface MediaItem {
  id: number
  token: string
  kind: string
  tag: string | null
  status: string
  url: string
  mime: string | null
  thumb?: { url: string } | null
}

interface Page<T> {
  items: T[]
}

/** Диалог выбора уже загруженного медиа для вложения к услуге — список с
 * поиском по тегу/mime и превью. Полноценная загрузка нового файла сюда не
 * входит: медиа сначала загружается через общий /media аплоадер (см. другие
 * страницы), здесь только привязка существующего к услуге. */
export function MediaPickerDialog({
  open,
  onOpenChange,
  onSelect,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  onSelect: (media: MediaItem) => void
}) {
  const [q, setQ] = useState("")

  const { data, isLoading } = useQuery({
    queryKey: ["media-picker", q],
    queryFn: async () =>
      (
        await api.get<Page<MediaItem>>("/v1/admin/media", {
          params: { limit: 60, q: q || undefined, sort: "-created_at" },
        })
      ).data.items,
    enabled: open,
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Выбрать медиа</DialogTitle>
        </DialogHeader>
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Поиск по тегу/mime…"
          autoFocus
        />
        <div className="grid max-h-[60vh] grid-cols-3 gap-2 overflow-y-auto sm:grid-cols-4">
          {isLoading && <p className="col-span-full text-sm text-muted-foreground">Загрузка…</p>}
          {!isLoading && (data?.length ?? 0) === 0 && (
            <p className="col-span-full py-8 text-center text-sm text-muted-foreground">
              Ничего не найдено. Загрузите медиа через страницу медиатеки.
            </p>
          )}
          {data?.map((m) => (
            <button
              key={m.id}
              type="button"
              onClick={() => {
                onSelect(m)
                onOpenChange(false)
              }}
              className="group relative flex aspect-square flex-col items-center justify-center overflow-hidden rounded-md border bg-muted transition hover:border-primary"
            >
              {m.thumb?.url || (m.kind === "image" && m.status === "ready") ? (
                <img
                  src={m.thumb?.url ?? m.url}
                  alt={m.tag ?? `media #${m.id}`}
                  className="size-full object-cover"
                />
              ) : (
                <ImageOff className="size-6 text-muted-foreground" />
              )}
              {m.tag && (
                <Badge variant="secondary" className="absolute bottom-1 left-1 text-[10px]">
                  {m.tag}
                </Badge>
              )}
            </button>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  )
}
