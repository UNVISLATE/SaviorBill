import { useState, useRef, type DragEvent } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import {
  ImagePlus,
  RotateCw,
  Trash2,
  Video,
  Upload,
  Check,
  Tag,
  X,
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
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/shadsnui/dialog"
import { MediaPickerDialog } from "@/components/media/MediaPickerDialog"
import { MediaUploadConfigModal } from "@/components/media/MediaUploadConfigModal"
import { isMediaConfigRequired, type MediaUploadConfig } from "@/api/media-upload"
import { useMediaUploadQueue } from "@/hooks/use-media-upload-queue"
import { MediaUploadQueueProgress } from "@/components/media/MediaUploadQueueProgress"
import { MediaContextMenu } from "@/components/media/MediaContextMenu"

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

  // Drag & drop
  const [isDragOver, setIsDragOver] = useState(false)

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

  // Мутация сохранения всех измененных тегов (Сохранить медиа)
  const saveAllPlacementsMutation = useMutation({
    mutationFn: async () => {
      const promises: Promise<unknown>[] = []
      for (const a of attachments) {
        const currentTag = tagMap[a.id] ?? a.tag ?? "gallery"
        if (currentTag !== a.tag) {
          promises.push(
            api.patch(`/v1/admin/services/${serviceId}/attachments/${a.id}`, {
              tag: currentTag,
            }),
          )
        }
      }
      await Promise.all(promises)
    },
    onSuccess: () => {
      toastSuccess("Медиа сохранено")
      onRefresh()
      void qc.invalidateQueries({ queryKey: ["admin-service-attachments", serviceId] })
      onOpenChange(false)
    },
    onError: (e: unknown) => {
      toastError("Ошибка сохранения медиа", getErrorDetail(e))
    },
  })

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
              {attachments.length} {attachments.length === 1 ? "файл" : "файлов"}
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

            {/* Attached Items List (Стиль Photo 2) */}
            <div className="space-y-2.5">
              {attachments.length === 0 ? (
                <div className="py-8 text-center text-xs text-muted-foreground/60 italic">
                  К этой услуге пока не прикреплено ни одного медиафайла
                </div>
              ) : (
                attachments.map((att) => {
                  const currentTag = tagMap[att.id] ?? att.tag ?? "gallery"
                  const isCustom = customTagActive[att.id] || !PRESET_PLACEMENTS.some((p) => p.value === currentTag)

                  return (
                    <MediaContextMenu
                      key={att.id}
                      item={{
                        id: att.id,
                        token: att.token,
                        url: att.url,
                        kind: att.kind,
                        status: att.status,
                        tag: currentTag,
                        mime: att.mime,
                      }}
                      placementOptions={PRESET_PLACEMENTS}
                      currentPlacement={currentTag}
                      onChangePlacement={(val) => {
                        setCustomTagActive((prev) => ({ ...prev, [att.id]: false }))
                        setTagMap((prev) => ({ ...prev, [att.id]: val }))
                      }}
                      onDelete={() => removeAttachmentMutation.mutate(att.id)}
                      canDelete={true}
                    >
                      <div
                        className="group flex items-center justify-between gap-3 rounded-xl border border-border/70 bg-card/60 p-2.5 transition-colors hover:bg-card hover:border-border cursor-context-menu"
                      >
                      {/* Thumbnail */}
                      <div className="relative size-12 shrink-0 overflow-hidden rounded-xl border border-border/80 bg-muted/30">
                        {att.kind === "image" ? (
                          <img
                            src={att.url}
                            alt={currentTag}
                            className="size-full object-cover"
                          />
                        ) : (
                          <div className="flex size-full items-center justify-center bg-muted/60 text-muted-foreground">
                            <Video className="size-5" />
                          </div>
                        )}
                        {att.kind === "video" && (
                          <div className="absolute right-1 bottom-1 rounded bg-black/70 px-1 py-0.5 text-[9px] text-white font-mono">
                            video
                          </div>
                        )}
                      </div>

                      {/* File Metadata */}
                      <div className="min-w-0 flex-1 space-y-0.5">
                        <p className="truncate font-mono text-xs font-medium text-foreground">
                          {att.token}.{att.mime?.split("/")[1] ?? (att.kind === "video" ? "webm" : "webp")}
                        </p>
                        <p className="text-[11px] text-muted-foreground capitalize">
                          {att.kind} {att.mime && `· ${att.mime}`}
                        </p>
                      </div>

                      {/* Placement Dropdown (or custom input) */}
                      <div className="flex items-center gap-1.5 shrink-0">
                        {isCustom ? (
                          <div className="flex items-center gap-1">
                            <Input
                              value={currentTag}
                              maxLength={16}
                              onChange={(e) =>
                                setTagMap((prev) => ({
                                  ...prev,
                                  [att.id]: e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, ""),
                                }))
                              }
                              placeholder="свой тег (до 16 симв)"
                              className="h-8 w-32 font-mono text-xs"
                              autoFocus
                            />
                            <Button
                              size="icon"
                              variant="ghost"
                              className="size-8 shrink-0 text-muted-foreground hover:text-foreground"
                              onClick={() => {
                                setCustomTagActive((prev) => ({ ...prev, [att.id]: false }))
                                setTagMap((prev) => ({ ...prev, [att.id]: "gallery" }))
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
                                setCustomTagActive((prev) => ({ ...prev, [att.id]: true }))
                              } else {
                                setTagMap((prev) => ({ ...prev, [att.id]: val ?? "gallery" }))
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

                        {/* Replace / Reload button */}
                        <Button
                          size="icon"
                          variant="ghost"
                          className="size-8 text-muted-foreground hover:text-foreground hover:bg-muted"
                          onClick={() => {
                            setPendingFile(null)
                            fileInputRef.current?.click()
                          }}
                          title="Заменить файл"
                        >
                          <RotateCw className="size-3.5" />
                        </Button>

                        {/* Delete button */}
                        <Button
                          size="icon"
                          variant="ghost"
                          className="size-8 text-muted-foreground hover:text-destructive hover:bg-destructive/10"
                          onClick={() => removeAttachmentMutation.mutate(att.id)}
                          disabled={removeAttachmentMutation.isPending}
                          title="Удалить файл"
                        >
                          <Trash2 className="size-3.5" />
                        </Button>
                      </div>
                    </div>
                  </MediaContextMenu>
                )
                })
              )}
            </div>
          </div>

          {/* Footer (Стиль Photo 2) */}
          <DialogFooter className="px-6 py-3.5 bg-muted/20 border-t border-border/60 flex items-center justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
              Отмена
            </Button>
            <Button
              size="sm"
              onClick={() => saveAllPlacementsMutation.mutate()}
              disabled={saveAllPlacementsMutation.isPending}
              className="gap-1.5 shadow-sm"
            >
              {saveAllPlacementsMutation.isPending ? (
                <RotateCw className="size-3.5 animate-spin" />
              ) : (
                <Check className="size-3.5" />
              )}
              <span>Сохранить медиа</span>
            </Button>
          </DialogFooter>
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
    </>
  )
}
