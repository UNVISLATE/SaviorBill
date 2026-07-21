import { useRef, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { ArrowLeft, Loader2, Plus, Trash2, Upload } from "lucide-react"

import { api } from "@/lib/api"
import { fmtDateTime, fmtSize, metaRows } from "@/lib/media-format"
import { Button } from "@/components/shadsnui/button"

interface MediaVariant {
  mime: string | null
  size: number | null
  url: string
}

export interface PreviewGalleryMedia {
  token: string
  kind: string
  mime: string | null
  size: number | null
  created_at: string
  thumb: MediaVariant | null
  previews: MediaVariant[]
  meta: Record<string, number>
}

const TERMINAL_OP_STATES = new Set(["ready", "failed", "stale", "cancelled"])

/** Подождать завершения фоновой операции mediaworker (thumb_replace/preview_add)
 * перед тем как считать мутацию выполненной. POST .../thumb и .../preview
 * возвращают 202 "processing" сразу — реальный результат (variants в БД biling)
 * появляется позже, когда mediaworker закончит конвертацию и billing обработает
 * событие результата. Без этого invalidate() после 202 просто перечитывал ещё
 * не обновлённые данные — карточка/подробности не менялись, будто запрос
 * ничего не сделал. */
async function waitForOp(token: string, op: string): Promise<void> {
  const deadline = Date.now() + 120_000
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 700))
    try {
      const { data } = await api.get<{ state: string }>(`/v1/media/${token}/ops/${op}/status`)
      if (TERMINAL_OP_STATES.has(data.state)) return
    } catch {
      // job-запись может ещё не появиться в первые доли секунды — продолжаем поллинг
    }
  }
}

interface MediaListLike {
  items: PreviewGalleryMedia[]
}

/** Дождаться, пока сам список медиа (не статус джобы) реально отразит
 * изменение. ``waitForOp`` только показывает, что worker_jobs (billing)
 * пометил операцию "ready" — но это отдельный стрим/консьюмер от того, что
 * пишет ``system_media.variants`` (``media_results`` в billing), порядок
 * обработки между ними не гарантирован. На практике "ready" по джобе иногда
 * приходит на 1 рефетч раньше, чем реально обновлённые ``variants`` — без
 * этой проверки redetail-страница один раз показывала старые данные, и
 * только следующий рефетч (например, при возврате в список и назад) —
 * актуальные. */
async function waitForListChange(
  qc: ReturnType<typeof useQueryClient>,
  queryKey: unknown[],
  token: string,
  isUpdated: (item: PreviewGalleryMedia) => boolean,
): Promise<void> {
  const deadline = Date.now() + 15_000
  while (Date.now() < deadline) {
    // Только refetchQueries — invalidateQueries на активном запросе сама
    // планирует свой рефетч, так что вызов обоих подряд на каждой итерации
    // давал двойной запрос за цикл (~60 запросов на весь 15с поллинг).
    const data = await qc.refetchQueries({ queryKey, exact: true, type: "active" })
      .then(() => qc.getQueryData<MediaListLike>(queryKey))
    const item = data?.items.find((i) => i.token === token)
    if (item && isUpdated(item)) return
    await new Promise((r) => setTimeout(r, 500))
  }
}

/**
 * "Подробности" видео (§5.6): thumb с заменой, панель технических метаданных
 * (§5.7) и список ``previews[]`` с перетаскиванием порядка, удалением и
 * добавлением нового кадра.
 *
 * Раньше это была отдельная модалка-портал поверх всего — по просьбе (см.
 * IMPLEMENTATION_PLAN.md) теперь это обычная страница внутри той же панели
 * профиля: заменяет список медиа на месте, назад — по стрелке в заголовке,
 * а не крестиком отдельного слоя.
 */
export function MediaPreviewGallery({
  media,
  queryKey,
  onClose,
}: {
  media: PreviewGalleryMedia
  queryKey: unknown[]
  onClose: () => void
}) {
  const qc = useQueryClient()
  const thumbInputRef = useRef<HTMLInputElement>(null)
  const previewInputRef = useRef<HTMLInputElement>(null)
  const [dragIndex, setDragIndex] = useState<number | null>(null)
  const [localOrder, setLocalOrder] = useState<MediaVariant[]>(media.previews)

  // ``useState(media.previews)`` только на монтирование — без этого локальный
  // порядок (для drag&drop) навечно замирал на исходном списке: после
  // добавления/удаления/замены превью и рефетча запроса компонент не
  // размонтируется (та же карточка "Подробности"), поэтому новые пропсы
  // приходили, а localOrder никогда не обновлялся. Синхронизация прямо в теле
  // рендера через сравнение с состоянием (а не ref — тот при рендере трогать
  // нельзя) — рекомендованный React-паттерн "adjusting state when a prop
  // changes", без каскадных ре-рендеров через эффект.
  const [previewsSource, setPreviewsSource] = useState(media.previews)
  if (previewsSource !== media.previews) {
    setPreviewsSource(media.previews)
    setLocalOrder(media.previews)
  }

  const invalidate = () => qc.invalidateQueries({ queryKey })

  // ``thumb.url`` стабилен и не меняется при замене (см. schemas/media.py —
  // это намеренный контракт), поэтому браузер не станет перезапрашивать
  // картинку сам просто из-за того, что пропсы обновились. Локальный
  // cache-buster даёт мгновенное обновление превью сразу после успешной
  // замены, не дожидаясь истечения Cache-Control на сервере (см. serve.py).
  const [thumbVersion, setThumbVersion] = useState(0)

  const replaceThumb = useMutation({
    mutationFn: async (file: File) => {
      const prevSize = media.thumb?.size ?? null
      await api.post(`/media/${media.token}/thumb`, file, {
        headers: { "Content-Type": file.type || "application/octet-stream" },
      })
      await waitForOp(media.token, "thumb_replace")
      await waitForListChange(qc, queryKey, media.token, (item) => (item.thumb?.size ?? null) !== prevSize)
    },
    onSuccess: () => setThumbVersion(Date.now()),
  })

  const addPreview = useMutation({
    mutationFn: async (file?: File) => {
      const prevCount = media.previews.length
      if (file) {
        await api.post(`/media/${media.token}/preview`, file, {
          headers: { "Content-Type": file.type || "application/octet-stream" },
        })
      } else {
        // Пустое тело -> mediaworker сам берёт случайный кадр из готового видео.
        await api.post(`/media/${media.token}/preview`, undefined, {
          headers: { "Content-Type": "application/octet-stream" },
        })
      }
      await waitForOp(media.token, "preview_add")
      await waitForListChange(qc, queryKey, media.token, (item) => item.previews.length > prevCount)
    },
  })

  const removePreview = useMutation({
    mutationFn: async (index: number) => {
      await api.delete(`/v1/media/${media.token}/previews/${index}`)
    },
    onSuccess: invalidate,
  })

  const reorderPreviews = useMutation({
    mutationFn: async (order: number[]) => {
      await api.patch(`/v1/media/${media.token}/previews/order`, { order })
    },
    onSuccess: invalidate,
  })

  function onDragStart(i: number) {
    setDragIndex(i)
  }
  function onDragOverItem(e: React.DragEvent, i: number) {
    e.preventDefault()
    if (dragIndex === null || dragIndex === i) return
    setLocalOrder((prev) => {
      const next = [...prev]
      const [moved] = next.splice(dragIndex, 1)
      next.splice(i, 0, moved)
      return next
    })
    setDragIndex(i)
  }
  function onDragEnd() {
    if (dragIndex === null) return
    setDragIndex(null)
    const order = localOrder.map((v) => media.previews.indexOf(v))
    if (order.some((v, i) => v !== i)) reorderPreviews.mutate(order)
  }

  const rows = metaRows(media.meta, media.kind)

  return (
    <div className="flex h-full flex-col gap-4">
      <div className="flex items-center gap-2">
        <Button type="button" size="icon-sm" variant="ghost" onClick={onClose} aria-label="Назад к списку медиа">
          <ArrowLeft className="size-4" />
        </Button>
        <span className="text-sm font-medium">Подробности файла</span>
      </div>

      <div className="flex-1 overflow-y-auto pr-1">
        <div className="flex items-center gap-3">
          <div className="relative size-24 shrink-0 overflow-hidden rounded-lg border bg-muted">
            {media.thumb ? (
              <img
                src={thumbVersion ? `${media.thumb.url}?v=${thumbVersion}` : media.thumb.url}
                alt=""
                className="size-full object-cover"
              />
            ) : (
              <div className="flex size-full items-center justify-center text-muted-foreground">
                <Upload className="size-5" />
              </div>
            )}
            {replaceThumb.isPending && (
              <div className="absolute inset-0 flex items-center justify-center bg-black/50">
                <Loader2 className="size-5 animate-spin text-white" />
              </div>
            )}
          </div>
          <div className="flex flex-1 flex-col gap-1">
            <span className="text-sm font-medium">Обложка (thumb)</span>
            <input
              ref={thumbInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) replaceThumb.mutate(f)
                e.target.value = ""
              }}
            />
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={replaceThumb.isPending}
              onClick={() => thumbInputRef.current?.click()}
              className="w-fit"
            >
              Заменить кадром со своего устройства
            </Button>
          </div>
        </div>

        {rows.length > 0 && (
          <div className="mt-4 grid grid-cols-2 gap-1.5 rounded-lg border p-2.5 text-xs">
            {rows.map((r) => (
              <div key={r.label} className="flex justify-between gap-2">
                <span className="text-muted-foreground">{r.label}</span>
                <span className="font-medium">{r.value}</span>
              </div>
            ))}
            <div className="flex justify-between gap-2">
              <span className="text-muted-foreground">Размер</span>
              <span className="font-medium">{fmtSize(media.size)}</span>
            </div>
            <div className="flex justify-between gap-2">
              <span className="text-muted-foreground">Загружено</span>
              <span className="font-medium">{fmtDateTime(media.created_at)}</span>
            </div>
          </div>
        )}

        <div className="mt-4 flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">Превью ({localOrder.length})</span>
            <input
              ref={previewInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) addPreview.mutate(f)
                e.target.value = ""
              }}
            />
            <div className="flex gap-1.5">
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={addPreview.isPending}
                onClick={() => previewInputRef.current?.click()}
              >
                Загрузить кадр
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={addPreview.isPending}
                onClick={() => addPreview.mutate(undefined)}
              >
                {addPreview.isPending ? <Loader2 className="size-3.5 animate-spin" /> : <Plus className="size-3.5" />}
                Случайный кадр
              </Button>
            </div>
          </div>

          {localOrder.length === 0 ? (
            <p className="rounded-lg border border-dashed p-3 text-center text-xs text-muted-foreground">
              Пока нет превью — добавьте кадр вручную или случайным выбором.
            </p>
          ) : (
            <div className="grid grid-cols-4 gap-2">
              {localOrder.map((p, i) => (
                <div
                  key={p.url}
                  draggable
                  onDragStart={() => onDragStart(i)}
                  onDragOver={(e) => onDragOverItem(e, i)}
                  onDragEnd={onDragEnd}
                  className="group relative aspect-square cursor-grab overflow-hidden rounded-md border active:cursor-grabbing"
                >
                  <img src={p.url} alt="" className="size-full object-cover" />
                  <Button
                    type="button"
                    size="icon-sm"
                    variant="destructive"
                    disabled={removePreview.isPending}
                    className="absolute top-1 right-1 opacity-0 transition-opacity group-hover:opacity-100"
                    onClick={() => removePreview.mutate(media.previews.indexOf(p))}
                  >
                    <Trash2 className="size-3" />
                  </Button>
                </div>
              ))}
            </div>
          )}
          <p className="text-[11px] text-muted-foreground">Перетаскивайте кадры, чтобы изменить порядок.</p>
        </div>
      </div>
    </div>
  )
}
