import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import {
  ChevronLeft,
  ChevronRight,
  Image as ImageIcon,
  Loader2,
  Search,
  SlidersHorizontal,
  Video,
} from "lucide-react"

import { api } from "@/api/api.ts"
import { Badge } from "@/components/shadsnui/badge"
import { Button } from "@/components/shadsnui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/shadsnui/dialog"
import { Input } from "@/components/shadsnui/input"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/shadsnui/table"
import {
  MediaPreviewGallery,
  type PreviewGalleryMedia,
  type MediaVariant,
} from "@/components/profile/MediaPreviewGallery"

export interface MediaPickerItem {
  id: number
  token: string
  kind: string
  tag: string | null
  name?: string | null
  status: string
  url: string
  mime: string | null
  created_at?: string
  size?: number | null
  thumb?: MediaVariant | null
  previews?: MediaVariant[]
  meta?: Record<string, number>
}

interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
  has_more: boolean
}

const PAGE_SIZE = 10

export function MediaPickerDialog({
  open,
  onOpenChange,
  onSelect,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  onSelect: (media: MediaPickerItem) => void
}) {
  const [search, setSearch] = useState("")
  const [page, setPage] = useState(1)
  const [detailMedia, setDetailMedia] = useState<PreviewGalleryMedia | null>(null)

  const offset = (page - 1) * PAGE_SIZE

  const { data, isLoading } = useQuery({
    queryKey: ["media-picker", search, page],
    queryFn: async () => {
      const res = await api.get<Page<MediaPickerItem>>("/v1/admin/media", {
        params: {
          limit: PAGE_SIZE,
          offset,
          q: search.trim() || undefined,
          sort: "-created_at",
        },
      })
      return res.data
    },
    enabled: open,
  })

  const items = data?.items || []
  const total = data?.total || 0
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const handleSearchChange = (val: string) => {
    setSearch(val)
    setPage(1)
  }

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="w-full max-w-3xl p-0 overflow-hidden shadow-2xl border-border/80 h-[640px] flex flex-col">
          <DialogHeader className="px-6 pt-5 pb-3 border-b border-border/60">
            <DialogTitle className="text-base font-semibold">
              Выбрать медиа из медиатеки
            </DialogTitle>
          </DialogHeader>

          {/* Search bar */}
          <div className="px-6 pt-4 pb-2">
            <div className="relative">
              <Search className="absolute left-3 top-2.5 size-4 text-muted-foreground" />
              <Input
                value={search}
                onChange={(e) => handleSearchChange(e.target.value)}
                placeholder="Поиск по названию или токену…"
                className="pl-9 text-xs h-9 bg-muted/20"
                autoFocus
              />
            </div>
          </div>

          {/* Table container */}
          <div className="flex-1 overflow-y-auto px-6 min-h-0">
            <div className="rounded-lg border overflow-hidden bg-card">
              <Table>
                <TableHeader>
                  <TableRow className="h-8 hover:bg-transparent">
                    <TableHead className="w-14 text-[11px]">Файл</TableHead>
                    <TableHead className="min-w-[180px] text-[11px]">Название / Токен</TableHead>
                    <TableHead className="w-24 text-[11px]">Тип</TableHead>
                    <TableHead className="w-28 text-[11px]">Тег</TableHead>
                    <TableHead className="w-32 text-right pr-4 text-[11px]">Действие</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {isLoading && (
                    <TableRow>
                      <TableCell colSpan={5} className="py-12 text-center text-xs text-muted-foreground">
                        <Loader2 className="size-5 animate-spin mx-auto mb-2 text-primary" />
                        Загрузка медиафайлов…
                      </TableCell>
                    </TableRow>
                  )}

                  {!isLoading && items.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={5} className="py-12 text-center text-xs text-muted-foreground">
                        {search ? "Ничего не найдено по текущему запросу." : "В медиатеке пока нет файлов."}
                      </TableCell>
                    </TableRow>
                  )}

                  {!isLoading &&
                    items.map((m) => {
                      const thumbUrl =
                        m.thumb?.url || (m.kind === "video" ? `/api/media/${m.token}.thumb` : m.url)

                      return (
                        <TableRow
                          key={m.id}
                          className="hover:bg-muted/40 cursor-pointer transition-colors"
                          onClick={() => {
                            onSelect(m)
                            onOpenChange(false)
                          }}
                        >
                          {/* Thumbnail */}
                          <TableCell className="py-2 pl-3">
                            <div className="relative size-10 shrink-0 overflow-hidden rounded-md border border-border/80 bg-muted/30">
                              <img
                                src={thumbUrl}
                                alt={m.name || m.token}
                                className="size-full object-cover"
                                onError={(e) => {
                                  if (m.kind === "video") {
                                    (e.target as HTMLElement).style.display = "none"
                                  }
                                }}
                              />
                              {m.kind === "video" && (
                                <div className="absolute right-0.5 bottom-0.5 rounded bg-black/70 px-1 py-0.2 text-[8px] text-white font-mono">
                                  video
                                </div>
                              )}
                            </div>
                          </TableCell>

                          {/* Name / Token */}
                          <TableCell className="py-2">
                            <div className="space-y-0.5 max-w-[220px]">
                              <p className="truncate text-xs font-medium text-foreground">
                                {m.name || m.token}
                              </p>
                              <p className="truncate font-mono text-[10px] text-muted-foreground">
                                {m.token}
                              </p>
                            </div>
                          </TableCell>

                          {/* Type */}
                          <TableCell className="py-2">
                            <Badge variant="outline" className="text-[10px] gap-1 px-1.5 py-0">
                              {m.kind === "video" ? (
                                <Video className="size-3 text-sky-400" />
                              ) : (
                                <ImageIcon className="size-3 text-emerald-400" />
                              )}
                              <span>{m.kind}</span>
                            </Badge>
                          </TableCell>

                          {/* Tag */}
                          <TableCell className="py-2">
                            {m.tag ? (
                              <Badge variant="secondary" className="font-mono text-[10px] px-1.5 py-0">
                                {m.tag}
                              </Badge>
                            ) : (
                              <span className="text-[11px] text-muted-foreground">—</span>
                            )}
                          </TableCell>

                          {/* Actions */}
                          <TableCell className="py-2 text-right pr-4" onClick={(e) => e.stopPropagation()}>
                            <div className="flex items-center justify-end gap-1.5">
                              {m.kind === "video" && (
                                <Button
                                  size="icon"
                                  variant="ghost"
                                  className="size-7 text-muted-foreground hover:text-foreground"
                                  onClick={() =>
                                    setDetailMedia({
                                      token: m.token,
                                      kind: m.kind,
                                      mime: m.mime,
                                      size: m.size ?? null,
                                      created_at: m.created_at || new Date().toISOString(),
                                      thumb: m.thumb ?? null,
                                      previews: m.previews ?? [],
                                      meta: m.meta ?? {},
                                    })
                                  }
                                  title="Подробнее (превью и обложка)"
                                >
                                  <SlidersHorizontal className="size-3.5" />
                                </Button>
                              )}
                              <Button
                                size="sm"
                                variant="outline"
                                className="h-7 text-xs px-2.5 font-medium"
                                onClick={() => {
                                  onSelect(m)
                                  onOpenChange(false)
                                }}
                              >
                                Выбрать
                              </Button>
                            </div>
                          </TableCell>
                        </TableRow>
                      )
                    })}
                </TableBody>
              </Table>
            </div>
          </div>

          {/* Pagination Footer */}
          <div className="px-6 py-3 bg-muted/20 border-t border-border/60 flex items-center justify-between text-xs text-muted-foreground">
            <span>
              Показано {items.length} из {total} файлов (по 10 на страницу)
            </span>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                className="h-7 text-xs px-2 gap-1"
                disabled={page <= 1 || isLoading}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                <ChevronLeft className="size-3.5" /> Назад
              </Button>
              <span className="text-xs font-mono font-medium text-foreground">
                {page} / {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                className="h-7 text-xs px-2 gap-1"
                disabled={page >= totalPages || isLoading}
                onClick={() => setPage((p) => p + 1)}
              >
                Вперёд <ChevronRight className="size-3.5" />
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Details modal for video */}
      <Dialog open={Boolean(detailMedia)} onOpenChange={(open) => !open && setDetailMedia(null)}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
          {detailMedia && (
            <MediaPreviewGallery
              media={detailMedia}
              queryKey={["media-picker", search, page]}
              onClose={() => setDetailMedia(null)}
            />
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}
