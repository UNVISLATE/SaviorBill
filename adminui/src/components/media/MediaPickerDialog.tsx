import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { ImageOff, Loader2, Upload } from "lucide-react"
import { useRef } from "react"
import { uploadOwnMedia } from "@/api/media-upload"
import { toastError, toastSuccess } from "@/lib/toast"
import { Button } from "@/components/shadsnui/button"
import { useQueryClient } from "@tanstack/react-query"

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
  const [uploading, setUploading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const qc = useQueryClient()

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      const { mediaId, token } = await uploadOwnMedia(file, { tag: "service" })
      toastSuccess("Файл успешно загружен")
      void qc.invalidateQueries({ queryKey: ["media-picker"] })
      onSelect({
        id: mediaId,
        token,
        kind: file.type.startsWith("video/") ? "video" : "image",
        tag: "service",
        status: "ready",
        url: `/api/media/${token}`,
        mime: file.type,
      })
      onOpenChange(false)
    } catch (err) {
      toastError("Ошибка при загрузке медиафайла", err instanceof Error ? err.message : String(err))
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ""
    }
  }

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
        <DialogHeader className="flex flex-row items-center justify-between space-y-0 pb-1">
          <DialogTitle>Выбрать или загрузить медиа</DialogTitle>
          <div className="flex items-center gap-2">
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileUpload}
              accept="image/*,video/*"
              className="hidden"
            />
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-8 text-xs gap-1.5"
              disabled={uploading}
              onClick={() => fileInputRef.current?.click()}
            >
              {uploading ? (
                <>
                  <Loader2 className="size-3.5 animate-spin" /> Загрузка…
                </>
              ) : (
                <>
                  <Upload className="size-3.5" /> Загрузить файл
                </>
              )}
            </Button>
          </div>
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
