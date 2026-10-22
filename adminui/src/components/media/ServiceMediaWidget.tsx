import { useState } from "react"
import { ImagePlus, Video } from "lucide-react"
import { Button } from "@/components/shadsnui/button"
import {
  ServiceMediaManagerDialog,
  type ServiceAttachmentItem,
} from "@/components/media/ServiceMediaManagerDialog"

interface ServiceMediaWidgetProps {
  serviceId: number
  serviceName: string
  attachments: ServiceAttachmentItem[]
  onRefresh: () => void
  disabled?: boolean
}

export function ServiceMediaWidget({
  serviceId,
  serviceName,
  attachments,
  onRefresh,
  disabled,
}: ServiceMediaWidgetProps) {
  const [dialogOpen, setDialogOpen] = useState(false)

  // Первые 5 миниатюр
  const displayedAttachments = attachments.slice(0, 5)
  const remainingCount = attachments.length - displayedAttachments.length

  // Подсчёт статистики: файлы, изображения, видео
  const imageCount = attachments.filter((a) => a.kind === "image").length
  const videoCount = attachments.filter((a) => a.kind === "video").length

  const summaryParts: string[] = []
  if (attachments.length === 0) {
    summaryParts.push("НЕТ МЕДИАФАЙЛОВ")
  } else {
    summaryParts.push(`${attachments.length} ФАЙЛ${attachments.length === 1 ? "" : attachments.length < 5 ? "А" : "ОВ"}`)
    if (imageCount > 0) {
      summaryParts.push(`${imageCount} ИЗОБР.`)
    }
    if (videoCount > 0) {
      summaryParts.push(`${videoCount} ВИДЕО`)
    }
  }

  const summaryText = summaryParts.join(" · ")

  return (
    <div className="rounded-2xl border border-border/80 bg-card/60 p-4 space-y-4 shadow-2xs">
      {/* Верхний ряд: превью миниатюр */}
      <div className="flex items-center gap-2.5 overflow-x-auto pb-1">
        {attachments.length === 0 ? (
          <div className="flex h-16 flex-1 items-center justify-center rounded-xl border border-dashed border-border/70 bg-muted/20 text-xs text-muted-foreground gap-2">
            <ImagePlus className="size-4 opacity-50" />
            <span>Медиафайлы пока не добавлены</span>
          </div>
        ) : (
          <>
            {displayedAttachments.map((att) => (
              <div
                key={att.id}
                className="group relative size-16 shrink-0 overflow-hidden rounded-xl border border-border/80 bg-muted/30 shadow-2xs"
              >
                {att.kind === "image" ? (
                  <img
                    src={att.url}
                    alt={att.tag ?? ""}
                    className="size-full object-cover transition-transform group-hover:scale-105"
                  />
                ) : (
                  <div className="flex size-full items-center justify-center bg-muted/80 text-muted-foreground">
                    <Video className="size-6" />
                  </div>
                )}
                {att.tag && (
                  <div className="absolute left-1 bottom-1 rounded bg-black/70 px-1 py-0.5 text-[8px] font-mono text-white/90">
                    {att.tag}
                  </div>
                )}
              </div>
            ))}

            {remainingCount > 0 && (
              <div className="flex size-16 shrink-0 items-center justify-center rounded-xl border border-border/80 bg-muted/40 font-mono text-sm font-semibold text-foreground shadow-2xs">
                +{remainingCount}
              </div>
            )}
          </>
        )}
      </div>

      {/* Нижний ряд: статусная строка и кнопка управления */}
      <div className="flex items-center justify-between pt-1 border-t border-border/40">
        <span className="text-[11px] font-medium tracking-wider text-muted-foreground uppercase">
          {summaryText}
        </span>

        <Button
          type="button"
          size="sm"
          disabled={disabled}
          onClick={() => setDialogOpen(true)}
          className="h-8 rounded-lg px-4 text-xs font-semibold shadow-xs"
        >
          Управление медиа
        </Button>
      </div>

      {/* Полноразмерный диалог управления медиа (Стиль Photo 2) */}
      <ServiceMediaManagerDialog
        serviceId={serviceId}
        serviceName={serviceName}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        attachments={attachments}
        onRefresh={onRefresh}
      />
    </div>
  )
}
