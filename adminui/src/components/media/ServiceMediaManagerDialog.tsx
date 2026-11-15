import { useState, useRef, useEffect, type DragEvent } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core"
import {
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
  useSortable,
} from "@dnd-kit/sortable"
import { CSS } from "@dnd-kit/utilities"
import {
  ImagePlus,
  RotateCw,
  Trash2,
  Upload,
  Tag,
  X,
  GripVertical,
  SlidersHorizontal,
} from "lucide-react"

import { api } from "@/api/api.ts"
import { toastError, toastSuccess } from "@/lib/toast.ts"
import { getErrorDetail } from "@/lib/api-error.ts"
import { Button } from "@/components/shadsnui/button"
import { Input } from "@/components/shadsnui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/shadsnui/select"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/shadsnui/dialog"
import { MediaPickerDialog } from "@/components/media/MediaPickerDialog"
import { MediaUploadConfigModal } from "@/components/media/MediaUploadConfigModal"
import { isMediaConfigRequired, type MediaUploadConfig } from "@/api/media-upload"
import { useMediaUploadQueue } from "@/hooks/use-media-upload-queue"
import { MediaUploadQueueProgress } from "@/components/media/MediaUploadQueueProgress"
import { MediaContextMenu } from "@/components/media/MediaContextMenu"
import {
  MediaPreviewGallery,
  type PreviewGalleryMedia,
  type MediaVariant,
} from "@/components/profile/MediaPreviewGallery"

export interface ServiceAttachmentItem {
  id: number
  media_id: number
  token: string
  kind: string
  tag: string | null
  position: number
  mime: string | null
  status: string
  url: string
  name?: string | null
  thumb?: MediaVariant | null
  previews?: MediaVariant[]
}

interface ServiceMediaManagerDialogProps {
  serviceId: number
  serviceName: string
  open: boolean
  onOpenChange: (open: boolean) => void
  attachments: ServiceAttachmentItem[]
  onRefresh: () => void
}

const PRESET_PLACEMENTS: { value: string; label: string }[] = [
  { value: "card", label: "Карточка" },
  { value: "banner", label: "Баннер" },
  { value: "preview", label: "Превью" },
  { value: "gallery", label: "Медиа" },
]

function SortableAttachmentItem({
  att,
  currentTag,
  isCustom,
  onOpenDetails,
  onChangePlacement,
  onDelete,
  onCustomTagActiveChange,
  setTagMapValue,
}: {
  att: ServiceAttachmentItem
  currentTag: string
  isCustom: boolean
  onOpenDetails?: () => void
  onChangePlacement: (val: string) => void
  onDelete: () => void
  onCustomTagActiveChange: (active: boolean) => void
  setTagMapValue: (val: string) => void
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: att.id })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    zIndex: isDragging ? 50 : undefined,
  }

  const thumbUrl = att.thumb?.url || (att.kind === "video" ? `/api/media/${att.token}.thumb` : att.url)

  return (
    <MediaContextMenu
      item={{
        id: att.id,
        token: att.token,
        url: att.url,
        kind: att.kind,
        status: att.status,
        tag: currentTag,
        mime: att.mime,
        name: att.name,
      }}
      placementOptions={PRESET_PLACEMENTS}
      currentPlacement={currentTag}
      onChangePlacement={onChangePlacement}
      onOpenDetails={onOpenDetails}
      onDelete={onDelete}
      canDelete={true}
    >
      <div
        ref={setNodeRef}
        style={style}
        className={`group flex items-center justify-between gap-3 rounded-xl border border-border/70 bg-card/60 p-2.5 transition-colors hover:bg-card hover:border-border cursor-context-menu ${
          isDragging ? "opacity-40 scale-[0.98] ring-2 ring-primary shadow-xl bg-card" : ""
        }`}
      >
        {/* Drag handle */}
        <button
          type="button"
          className="cursor-grab active:cursor-grabbing text-muted-foreground hover:text-foreground p-1 touch-none shrink-0"
          title="Перетащите для изменения порядка"
          {...attributes}
          {...listeners}
        >
          <GripVertical className="size-4" />
        </button>

        {/* Thumbnail */}
        <div className="relative size-12 shrink-0 overflow-hidden rounded-xl border border-border/80 bg-muted/30">
          <img
            src={thumbUrl}
            alt={currentTag}
            className="size-full object-cover"
            onError={(e) => {
              if (att.kind === "video") {
                (e.target as HTMLElement).style.display = "none"
              }
            }}
          />
          {att.kind === "video" && (
            <div className="absolute right-1 bottom-1 rounded bg-black/70 px-1 py-0.5 text-[9px] text-white font-mono">
              video
            </div>
          )}
        </div>

        {/* File Metadata */}
        <div className="min-w-0 flex-1 space-y-0.5">
          <p className="truncate font-mono text-xs font-medium text-foreground">
            {att.name || `${att.token}.${att.mime?.split("/")[1] ?? (att.kind === "video" ? "webm" : "webp")}`}
          </p>
          <p className="text-[11px] text-muted-foreground capitalize">
            {att.kind} {att.mime && `· ${att.mime}`}
          </p>
        </div>

        {/* Placement Dropdown (or custom input) */}
        <div className="flex items-center gap-1.5 shrink-0" onClick={(e) => e.stopPropagation()}>
          {isCustom ? (
            <div className="flex items-center gap-1">
              <Input
                value={currentTag}
                maxLength={16}
                onChange={(e) => {
                  const cleaned = e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, "")
                  setTagMapValue(cleaned)
                }}
                onBlur={() => {
                  if (currentTag.trim()) {
                    onChangePlacement(currentTag.trim())
                  }
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && currentTag.trim()) {
                    onChangePlacement(currentTag.trim())
                  }
                }}
                placeholder="свой тег (до 16 симв)"
                className="h-8 w-32 font-mono text-xs"
                autoFocus
              />
              <Button
                size="icon"
                variant="ghost"
                className="size-8 shrink-0 text-muted-foreground hover:text-foreground"
                onClick={() => {
                  onCustomTagActiveChange(false)
                  onChangePlacement("gallery")
                }}
                title="Вернуть пресеты"
              >
                <X className="size-3.5" />
              </Button>
            </div>
          ) : (
            <Select
              value={currentTag}
              onValueChange={(val) => {
                if (val === "__custom__") {
                  onCustomTagActiveChange(true)
                } else {
                  onChangePlacement(val ?? "gallery")
                }
              }}
            >
              <SelectTrigger className="h-8 w-32 text-xs font-medium bg-muted/30">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PRESET_PLACEMENTS.map((p) => (
                  <SelectItem key={p.value} value={p.value} className="text-xs">
                    {p.label}
                  </SelectItem>
                ))}
                <SelectItem value="__custom__" className="text-xs text-primary font-medium">
                  <span className="flex items-center gap-1.5">
                    <Tag className="size-3" /> Свой тег…
                  </span>
                </SelectItem>
              </SelectContent>
            </Select>
          )}

          {/* Details button for video */}
          {att.kind === "video" && onOpenDetails && (
            <Button
              size="icon"
              variant="ghost"
              className="size-8 text-muted-foreground hover:text-foreground hover:bg-muted"
              onClick={onOpenDetails}
              title="Подробнее (превью и обложка)"
            >
              <SlidersHorizontal className="size-3.5" />
            </Button>
          )}

          {/* Delete button */}
          <Button
            size="icon"
            variant="ghost"
            className="size-8 text-muted-foreground hover:text-destructive hover:bg-destructive/10"
            onClick={onDelete}
            title="Удалить файл"
          >
            <Trash2 className="size-3.5" />
          </Button>
        </div>
      </div>
    </MediaContextMenu>
  )
}

export function ServiceMediaManagerDialog({
  serviceId,
  serviceName,
  open,
  onOpenChange,
  attachments,
  onRefresh,
}: ServiceMediaManagerDialogProps) {
  const qc = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [localAttachments, setLocalAttachments] = useState<ServiceAttachmentItem[]>(attachments)
  useEffect(() => {
    setLocalAttachments(attachments)
  }, [attachments])

  // Локальное состояние тегов (placement) для каждого attachment
  const [tagMap, setTagMap] = useState<Record<number, string>>(() => {
    const map: Record<number, string> = {}
    for (const a of attachments) {
      map[a.id] = a.tag ?? "gallery"
    }
    return map
  })

  // Режим ввода своего тега для конкретного attachment
  const [customTagActive, setCustomTagActive] = useState<Record<number, boolean>>({})

  // Выбор из медиатеки
  const [pickerOpen, setPickerOpen] = useState(false)

  // Модалка настройки конвертации
  const [pendingFile, setPendingFile] = useState<File | null>(null)
  const [configModalOpen, setConfigModalOpen] = useState(false)
  const [selectedPlacement, setSelectedPlacement] = useState<string>("gallery")

  // Модалка подробностей видеофайла
  const [detailMedia, setDetailMedia] = useState<PreviewGalleryMedia | null>(null)

  // Drag & drop
  const [isDragOver, setIsDragOver] = useState(false)

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  // Мутация добавления вложения
  const addAttachmentMutation = useMutation({
    mutationFn: async ({ mediaId, tag }: { mediaId: number; tag?: string }) =>
      api.post(`/v1/admin/services/${serviceId}/attachments`, {
        media_id: mediaId,
        tag: tag ?? "gallery",
        position: attachments.length,
      }),
    onSuccess: () => {
      onRefresh()
      void qc.invalidateQueries({ queryKey: ["admin-service-attachments", serviceId] })
    },
    onError: (e: unknown) => {
      toastError("Ошибка прикрепления медиа", getErrorDetail(e))
    },
  })

  const {
    jobs: uploadJobs,
    uploadFile,
    retryJob,
    removeJob,
    isBusy: uploading,
  } = useMediaUploadQueue({
    tag: selectedPlacement,
    autoRestoreJobs: true,
    queryKeysToInvalidate: [["admin-service-attachments", serviceId]],
    onJobSuccess: async (job, mediaId) => {
      try {
        let resolvedId = mediaId
        if (!resolvedId && job.token) {
          const { data: page } = await api.get<{ items: { id: number; token: string }[] }>("/v1/user/media", {
            params: { limit: 10, offset: 0 },
          })
          const found = page.items?.find((m) => m.token === job.token)
          resolvedId = found?.id
        }
        if (resolvedId) {
          await addAttachmentMutation.mutateAsync({
            mediaId: resolvedId,
            tag: job.tag ?? selectedPlacement ?? "gallery",
          })
          toastSuccess(`Файл «${job.fileName}» добавлен к услуге`)
        }
      } catch (e: unknown) {
        toastError("Не удалось прикрепить файл к услуге", getErrorDetail(e))
      }
    },
  })

  // Мутация удаления вложения
  const removeAttachmentMutation = useMutation({
    mutationFn: async (attId: number) =>
      api.delete(`/v1/admin/services/${serviceId}/attachments/${attId}`),
    onSuccess: () => {
      onRefresh()
      void qc.invalidateQueries({ queryKey: ["admin-service-attachments", serviceId] })
      toastSuccess("Файл удалён из услуги")
    },
    onError: (e: unknown) => {
      toastError("Ошибка удаления", getErrorDetail(e))
    },
  })

  // Обработка мгновенного обновления тега (placement)
  const handleUpdatePlacement = async (attId: number, newTag: string) => {
    setTagMap((prev) => ({ ...prev, [attId]: newTag }))
    try {
      await api.patch(`/v1/admin/services/${serviceId}/attachments/${attId}`, { tag: newTag })
      toastSuccess("Назначение медиа сохранено")
      onRefresh()
      void qc.invalidateQueries({ queryKey: ["admin-service-attachments", serviceId] })
    } catch (e: unknown) {
      toastError("Ошибка обновления тега", getErrorDetail(e))
    }
  }

  // Обработка перетаскивания и сохранения сортировки
  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event
    if (!over || active.id === over.id) return
    const oldIndex = localAttachments.findIndex((a) => a.id === active.id)
    const newIndex = localAttachments.findIndex((a) => a.id === over.id)
    if (oldIndex === -1 || newIndex === -1 || oldIndex === newIndex) return
    const next = [...localAttachments]
    const [moved] = next.splice(oldIndex, 1)
    next.splice(newIndex, 0, moved)
    setLocalAttachments(next)

    try {
      await Promise.all(
        next.map((att, pos) =>
          api.patch(`/v1/admin/services/${serviceId}/attachments/${att.id}`, { position: pos })
        )
      )
      toastSuccess("Порядок медиа сохранён")
      onRefresh()
      void qc.invalidateQueries({ queryKey: ["admin-service-attachments", serviceId] })
    } catch (e: unknown) {
      toastError("Ошибка сохранения порядка", getErrorDetail(e))
    }
  }

  // Обработка выбора файла с диска
  const handleFileSelect = (file: File) => {
    if (!isMediaConfigRequired(file)) {
      void executeUpload(file)
    } else {
      setPendingFile(file)
      setConfigModalOpen(true)
    }
  }

  const executeUpload = async (file: File, config?: MediaUploadConfig) => {
    try {
      const tagToUse = config?.tag || selectedPlacement || "gallery"
      await uploadFile(file, config, tagToUse)
      toastSuccess(`Файл «${file.name}» поставлен в очередь конвертации`)
    } catch (e: unknown) {
      toastError("Ошибка загрузки", getErrorDetail(e))
    } finally {
      setPendingFile(null)
      setConfigModalOpen(false)
    }
  }

  const onDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragOver(true)
  }

  const onDragLeave = () => {
    setIsDragOver(false)
  }

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragOver(false)
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileSelect(e.dataTransfer.files[0])
    }
  }

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="w-full max-w-2xl sm:max-w-2xl p-0 overflow-hidden shadow-2xl border-border/80 h-[680px] flex flex-col">
          {/* Header */}
          <DialogHeader className="px-6 pt-5 pb-3 border-b border-border/60">
            <DialogTitle className="text-lg font-semibold truncate">
              Медиа для {serviceName}
            </DialogTitle>
            <p className="text-xs text-muted-foreground">
              {localAttachments.length} {localAttachments.length === 1 ? "файл" : "файлов"} · Изменения сохраняются автоматически
            </p>
          </DialogHeader>

          {/* Body */}
          <div className="flex-1 overflow-y-auto p-6 space-y-5 min-h-0">
            {/* Drag & Drop Upload Zone (Стиль Photo 2) */}
            <div
              onDragOver={onDragOver}
              onDragLeave={onDragLeave}
              onDrop={onDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`relative flex flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed p-6 text-center cursor-pointer transition-all ${
                isDragOver
                  ? "border-primary bg-primary/10 scale-[1.01]"
                  : "border-border/80 bg-muted/20 hover:border-border hover:bg-muted/30"
              }`}
            >
              <input
                ref={fileInputRef}
                type="file"
                className="hidden"
                accept="image/*,video/*"
                onChange={(e) => {
                  if (e.target.files && e.target.files[0]) {
                    handleFileSelect(e.target.files[0])
                  }
                }}
              />

              <div className="flex size-12 items-center justify-center rounded-2xl bg-muted text-muted-foreground shadow-xs">
                {uploading ? (
                  <RotateCw className="size-6 animate-spin text-primary" />
                ) : (
                  <ImagePlus className="size-6" />
                )}
              </div>

              <div className="text-sm">
                <span className="font-semibold text-foreground">Перетащите файлы сюда или </span>
                <span className="font-semibold text-primary underline underline-offset-4 hover:text-primary/80">
                  выберите
                </span>
              </div>
              <p className="text-xs text-muted-foreground">
                Изображения (JPG, PNG, WebP, GIF, SVG) и видео (MP4, WebM)
              </p>

              <div className="pt-1">
                <Button
                  type="button"
                  variant="secondary"
                  size="xs"
                  className="h-7 text-xs gap-1.5"
                  onClick={(e) => {
                    e.stopPropagation()
                    setPickerOpen(true)
                  }}
                >
                  <Upload className="size-3" />
                  <span>Выбрать из медиатеки</span>
                </Button>
              </div>
            </div>

            {/* Активная очередь загрузки и конвертации */}
            <MediaUploadQueueProgress
              jobs={uploadJobs}
              onRetry={retryJob}
              onRemove={removeJob}
            />

            {/* Attached Items List с Dnd-kit сортировкой */}
            <div className="space-y-2.5">
              {localAttachments.length === 0 ? (
                <div className="py-8 text-center text-xs text-muted-foreground/60 italic">
                  К этой услуге пока не прикреплено ни одного медиафайла
                </div>
              ) : (
                <DndContext
                  sensors={sensors}
                  collisionDetection={closestCenter}
                  onDragEnd={handleDragEnd}
                >
                  <SortableContext
                    items={localAttachments.map((a) => a.id)}
                    strategy={verticalListSortingStrategy}
                  >
                    {localAttachments.map((att) => {
                      const currentTag = tagMap[att.id] ?? att.tag ?? "gallery"
                      const isCustom = customTagActive[att.id] || !PRESET_PLACEMENTS.some((p) => p.value === currentTag)

                      return (
                        <SortableAttachmentItem
                          key={att.id}
                          att={att}
                          currentTag={currentTag}
                          isCustom={isCustom}
                          onChangePlacement={(val) => {
                            setCustomTagActive((prev) => ({ ...prev, [att.id]: false }))
                            void handleUpdatePlacement(att.id, val)
                          }}
                          onOpenDetails={
                            att.kind === "video"
                              ? () =>
                                  setDetailMedia({
                                    token: att.token,
                                    kind: att.kind,
                                    mime: att.mime,
                                    size: null,
                                    created_at: new Date().toISOString(),
                                    thumb: att.thumb ?? null,
                                    previews: att.previews ?? [],
                                    meta: {},
                                  })
                              : undefined
                          }
                          onDelete={() => removeAttachmentMutation.mutate(att.id)}
                          onCustomTagActiveChange={(active) =>
                            setCustomTagActive((prev) => ({ ...prev, [att.id]: active }))
                          }
                          setTagMapValue={(val) => setTagMap((prev) => ({ ...prev, [att.id]: val }))}
                        />
                      )
                    })}
                  </SortableContext>
                </DndContext>
              )}
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Выбор из медиатеки */}
      <MediaPickerDialog
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        onSelect={(media) => {
          addAttachmentMutation.mutate({ mediaId: media.id, tag: "gallery" })
          setPickerOpen(false)
        }}
      />

      {/* Настройка конвертации для видео и GIF */}
      <MediaUploadConfigModal
        open={configModalOpen}
        file={pendingFile}
        allowedTags={PRESET_PLACEMENTS}
        initialTag={selectedPlacement}
        onCancel={() => {
          setConfigModalOpen(false)
          setPendingFile(null)
        }}
        onConfirm={(config) => {
          if (config.tag) setSelectedPlacement(config.tag)
          if (pendingFile) {
            void executeUpload(pendingFile, config)
          }
        }}
      />

      {/* Диалог подробностей видеофайла (превью, обложка) */}
      <Dialog open={Boolean(detailMedia)} onOpenChange={(open) => !open && setDetailMedia(null)}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
          {detailMedia && (
            <MediaPreviewGallery
              media={detailMedia}
              queryKey={["admin-service-attachments", serviceId]}
              onClose={() => setDetailMedia(null)}
            />
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}
