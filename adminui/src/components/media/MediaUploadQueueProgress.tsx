import {
  Clock,
  Loader2,
  RotateCcw,
  TriangleAlert,
  Video,
  FileImage,
  X,
  CheckCircle2,
} from "lucide-react"
import { Progress } from "@/components/shadsnui/progress"
import { Button } from "@/components/shadsnui/button"
import { Badge } from "@/components/shadsnui/badge"
import { fmtEta, fmtSize } from "@/api/media-format"
import type { UploadJob } from "@/hooks/use-media-upload-queue"
import { cn } from "@/lib/utils"

interface MediaUploadQueueProgressProps {
  jobs: UploadJob[]
  onRetry?: (id: string) => void
  onRemove?: (id: string) => void
  className?: string
  compact?: boolean
}

export function MediaUploadQueueProgress({
  jobs,
  onRetry,
  onRemove,
  className,
  compact = false,
}: MediaUploadQueueProgressProps) {
  if (jobs.length === 0) return null

  if (compact) {
    const activeCount = jobs.filter((j) => j.phase !== "done" && j.phase !== "error").length
    const errorCount = jobs.filter((j) => j.phase === "error").length
    const currentJob = jobs.find((j) => j.phase === "processing" || j.phase === "uploading") || jobs[0]
    const currentPct = currentJob.phase === "uploading" ? currentJob.uploadPct : (currentJob.convertPct ?? 0)

    return (
      <div
        className={cn(
          "flex items-center gap-3 px-3 py-2 rounded-lg border bg-card/90 text-xs shadow-sm",
          errorCount > 0 ? "border-destructive/40" : "border-primary/30",
          className,
        )}
      >
        <Loader2 className="size-3.5 animate-spin text-primary shrink-0" />
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex items-center justify-between gap-2">
            <span className="truncate font-medium">
              {currentJob.fileName}
            </span>
            <span className="shrink-0 font-mono text-[10px] text-muted-foreground">
              {Math.round(currentPct)}%
              {currentJob.etaSec != null && ` (${fmtEta(currentJob.etaSec)})`}
            </span>
          </div>
          <Progress value={currentPct} className="h-1.5" />
        </div>
        {activeCount > 1 && (
          <Badge variant="secondary" className="text-[10px] px-1.5 py-0 shrink-0">
            +{activeCount - 1}
          </Badge>
        )}
      </div>
    )
  }

  return (
    <div className={cn("space-y-2", className)}>
      {jobs.map((job) => {
        const isVideo =
          job.file?.type.startsWith("video/") ||
          /\.(mp4|webm|mkv|mov|avi)$/i.test(job.fileName)
        const pct =
          job.phase === "uploading"
            ? job.uploadPct
            : job.convertPct != null
              ? Math.round(job.convertPct)
              : job.phase === "done"
                ? 100
                : 0
        const eta = fmtEta(job.etaSec)

        return (
          <div
            key={job.id}
            className={cn(
              "flex items-center gap-3 p-2.5 rounded-xl border bg-card/75 text-xs transition-all shadow-xs",
              job.phase === "error"
                ? "border-destructive/40 bg-destructive/5"
                : job.phase === "done"
                  ? "border-emerald-500/30 bg-emerald-500/5"
                  : "border-border/70",
            )}
          >
            {/* Thumbnail / Icon */}
            <div className="relative size-10 rounded-lg overflow-hidden border bg-muted shrink-0 flex items-center justify-center">
              {job.previewUrl ? (
                <img src={job.previewUrl} alt="" className="size-full object-cover" />
              ) : isVideo ? (
                <Video className="size-5 text-muted-foreground" />
              ) : (
                <FileImage className="size-5 text-muted-foreground" />
              )}
              {job.phase === "processing" && (
                <div className="absolute inset-0 bg-black/40 flex items-center justify-center">
                  <Loader2 className="size-4 animate-spin text-white" />
                </div>
              )}
            </div>

            {/* Info and Progress bar */}
            <div className="min-w-0 flex-1 space-y-1.5">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate font-medium text-foreground" title={job.fileName}>
                  {job.fileName}
                </span>
                <span className="shrink-0 text-[11px] text-muted-foreground">
                  {fmtSize(job.fileSize)}
                </span>
              </div>

              {/* Status and ETA */}
              <div className="flex items-center justify-between gap-2 text-[11px]">
                <div className="flex items-center gap-1.5 truncate">
                  {job.phase === "uploading" && (
                    <>
                      <Loader2 className="size-3 animate-spin text-primary" />
                      <span className="text-primary font-medium">Загрузка файла ({job.uploadPct}%)</span>
                    </>
                  )}
                  {job.phase === "queued" && (
                    <>
                      <Clock className="size-3 text-amber-500" />
                      <span className="text-amber-500 font-medium">В очереди конвертации…</span>
                    </>
                  )}
                  {job.phase === "processing" && (
                    <>
                      <Loader2 className="size-3 animate-spin text-sky-500" />
                      <span className="text-sky-500 font-medium">
                        Конвертация ({pct}%)
                      </span>
                    </>
                  )}
                  {job.phase === "done" && (
                    <>
                      <CheckCircle2 className="size-3 text-emerald-500" />
                      <span className="text-emerald-500 font-medium">Готово</span>
                    </>
                  )}
                  {job.phase === "error" && (
                    <>
                      <TriangleAlert className="size-3 text-destructive" />
                      <span className="text-destructive font-medium truncate">
                        {job.error || "Ошибка конвертации"}
                      </span>
                    </>
                  )}
                </div>

                {job.phase === "processing" && eta && (
                  <span className="shrink-0 font-mono text-[10px] text-muted-foreground">
                    Осталось {eta}
                  </span>
                )}
              </div>

              {/* Progress bar */}
              {job.phase !== "error" && job.phase !== "done" && (
                <Progress value={pct} className="h-1.5" />
              )}
            </div>

            {/* Actions */}
            <div className="flex items-center gap-1 shrink-0">
              {job.phase === "error" && onRetry && job.file && (
                <Button
                  type="button"
                  variant="outline"
                  size="icon-xs"
                  onClick={() => onRetry(job.id)}
                  title="Повторить"
                >
                  <RotateCcw className="size-3" />
                </Button>
              )}
              {onRemove && (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-xs"
                  onClick={() => onRemove(job.id)}
                  title="Скрыть"
                >
                  <X className="size-3 text-muted-foreground" />
                </Button>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
