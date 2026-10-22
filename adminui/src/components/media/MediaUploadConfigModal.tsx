import { useState, useEffect } from "react"
import {
  Film,
  Video,
  FileImage,
  Zap,
  Sliders,
  Volume2,
  VolumeX,
  Tag,
  CheckCircle2,
  Layers,
} from "lucide-react"
import { Button } from "@/components/shadsnui/button"
import { Input } from "@/components/shadsnui/input"
import { Label } from "@/components/shadsnui/label"
import { Slider } from "@/components/shadsnui/slider"
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
import { Badge } from "@/components/shadsnui/badge"
import { fmtSize } from "@/api/media-format"
import { cn } from "@/lib/utils"
import { type MediaUploadConfig } from "@/api/media-upload"
import { useAdminUiSettings } from "@/api/admin-ui-settings"

export type { MediaUploadConfig }

export interface ConfiguredUploadItem {
  file: File
  config: MediaUploadConfig
}

export interface MediaUploadConfigModalProps {
  open: boolean
  file?: File | null
  files?: File[]
  initialTag?: string
  allowedTags?: { value: string; label: string }[]
  onConfirm?: (config: MediaUploadConfig) => void
  onConfirmBatch?: (items: ConfiguredUploadItem[]) => void
  onCancel: () => void
}

function checkIsGif(f: File): boolean {
  return f.type === "image/gif" || f.name.toLowerCase().endsWith(".gif")
}

function checkIsVideo(f: File): boolean {
  return f.type.startsWith("video/") || /\.(mp4|webm|mkv|mov|avi)$/i.test(f.name)
}

export function MediaUploadConfigModal({
  open,
  file,
  files,
  initialTag,
  allowedTags,
  onConfirm,
  onConfirmBatch,
  onCancel,
}: MediaUploadConfigModalProps) {
  const { data: adminSettings } = useAdminUiSettings()

  // GIF state
  const [gifChoice, setGifChoice] = useState<"keep_gif" | "to_webm" | "to_static">("keep_gif")

  // Video state: "original" (copy without re-encoding) vs "compress" (ffmpeg transcode)
  const [videoMode, setVideoMode] = useState<"original" | "compress">("original")
  const [videoFormat, setVideoFormat] = useState<"webm" | "mp4">("webm")
  const [videoScale, setVideoScale] = useState<string>("original")
  const [customScale, setCustomScale] = useState<string>("")
  const [posterScale, setPosterScale] = useState<string>("1080p")
  const [customPosterScale, setCustomPosterScale] = useState<string>("")
  const [videoPreset, setVideoPreset] = useState<string>("veryfast")
  const [audioBitrate, setAudioBitrate] = useState<string>("128k")
  const [videoCrf, setVideoCrf] = useState<number>(32)
  const [muteAudio, setMuteAudio] = useState<boolean>(false)

  // Tag / Placement
  const [tag, setTag] = useState<string>(initialTag ?? "")

  const allFiles = files && files.length > 0 ? files : file ? [file] : []
  const isBatch = allFiles.length > 1
  const gifFiles = allFiles.filter(checkIsGif)
  const videoFiles = allFiles.filter(checkIsVideo)
  const otherFiles = allFiles.filter((f) => !checkIsGif(f) && !checkIsVideo(f))

  const hasGifs = gifFiles.length > 0
  const hasVideos = videoFiles.length > 0

  useEffect(() => {
    if (open && adminSettings?.mediadialog?.default) {
      const def = adminSettings.mediadialog.default
      if (def.gif_format === "webm") setGifChoice("to_webm")
      else if (def.gif_format === "webp") setGifChoice("to_static")
      else setGifChoice("keep_gif")

      if (def.video_format === "original") {
        setVideoMode("original")
      } else {
        setVideoMode("compress")
        setVideoFormat(def.video_format === "mp4" ? "mp4" : "webm")
      }

      setVideoScale(def.scale || "original")
      setPosterScale(def.poster_scale || "1080p")
      setVideoPreset(def.video_preset || "veryfast")
      setAudioBitrate(def.audio_bitrate || "128k")
      setVideoCrf(def.crf ?? 32)
      setMuteAudio(def.audio_codec === "none")
    }
    if (initialTag !== undefined) {
      setTag(initialTag)
    }
  }, [open, adminSettings, initialTag])

  if (!open || allFiles.length === 0) return null

  const buildGifConfig = (): MediaUploadConfig => {
    if (gifChoice === "keep_gif") {
      return {
        format: "gif",
        keep_animation: true,
        video_codec: "copy",
        tag: tag.trim() || undefined,
      }
    }
    if (gifChoice === "to_webm") {
      return {
        format: "webm",
        video_codec: "libvpx-vp9",
        audio_codec: "none",
        crf: videoCrf,
        scale: videoScale,
        poster_scale: posterScale,
        tag: tag.trim() || undefined,
      }
    }
    return {
      format: "webp",
      keep_animation: false,
      tag: tag.trim() || undefined,
    }
  }

  const buildVideoConfig = (): MediaUploadConfig => {
    const effectiveScale =
      videoScale === "custom" ? customScale.trim() || "original" : videoScale
    const effectivePosterScale =
      posterScale === "custom" ? customPosterScale.trim() || "1080p" : posterScale

    if (videoMode === "original") {
      return {
        format: "original",
        video_codec: "copy",
        audio_codec: "copy",
        poster_scale: effectivePosterScale,
        tag: tag.trim() || undefined,
      }
    }
    return {
      format: videoFormat,
      video_codec: videoFormat === "mp4" ? "libx264" : "libvpx-vp9",
      audio_codec: muteAudio ? "none" : videoFormat === "mp4" ? "aac" : "libopus",
      scale: effectiveScale,
      poster_scale: effectivePosterScale,
      crf: videoCrf,
      video_preset: videoPreset,
      audio_bitrate: audioBitrate,
      tag: tag.trim() || undefined,
    }
  }

  const handleStart = () => {
    if (isBatch && onConfirmBatch) {
      const items: ConfiguredUploadItem[] = []
      for (const f of allFiles) {
        if (checkIsGif(f)) {
          items.push({ file: f, config: buildGifConfig() })
        } else if (checkIsVideo(f)) {
          items.push({ file: f, config: buildVideoConfig() })
        } else {
          items.push({
            file: f,
            config: { format: "webp", tag: tag.trim() || undefined },
          })
        }
      }
      onConfirmBatch(items)
      return
    }

    // Single file
    const first = allFiles[0]
    let config: MediaUploadConfig
    if (checkIsGif(first)) {
      config = buildGifConfig()
    } else if (checkIsVideo(first)) {
      config = buildVideoConfig()
    } else {
      config = { format: "webp", tag: tag.trim() || undefined }
    }

    if (onConfirmBatch) {
      onConfirmBatch([{ file: first, config }])
    } else if (onConfirm) {
      onConfirm(config)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onCancel()}>
      <DialogContent className="sm:max-w-[560px] max-h-[85vh] flex flex-col p-0 overflow-hidden shadow-2xl border-border/80">
        {/* Header (Pinned) */}
        <DialogHeader className="px-6 py-3.5 border-b border-border/60 bg-muted/30 shrink-0">
          <div className="flex items-center gap-3">
            <div className="flex size-9 items-center justify-center rounded-lg bg-primary/10 text-primary shrink-0 border border-primary/20">
              {isBatch ? (
                <Layers className="size-4.5 text-primary" />
              ) : hasGifs ? (
                <Film className="size-4.5 text-amber-500" />
              ) : hasVideos ? (
                <Video className="size-4.5 text-sky-500" />
              ) : (
                <FileImage className="size-4.5 text-emerald-500" />
              )}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <DialogTitle className="text-sm font-semibold">
                  {isBatch
                    ? `Пакетная загрузка (${allFiles.length} файлов)`
                    : hasGifs
                    ? "Загрузка анимации (GIF)"
                    : hasVideos
                    ? "Загрузка видео"
                    : "Загрузка медиа"}
                </DialogTitle>
                <Badge variant="outline" className="text-[10px] px-1.5 py-0 font-mono uppercase">
                  {isBatch
                    ? `${allFiles.length} шт`
                    : hasGifs
                    ? "GIF"
                    : hasVideos
                    ? "Видео"
                    : "Фото"}
                </Badge>
              </div>
              <p className="text-[11px] text-muted-foreground truncate mt-0.5">
                {isBatch ? (
                  <span>
                    Видео: {videoFiles.length}, GIF: {gifFiles.length}
                    {otherFiles.length > 0 ? `, Фото: ${otherFiles.length}` : ""}
                  </span>
                ) : (
                  <>
                    <span className="font-medium text-foreground">{allFiles[0].name}</span>
                    <span className="mx-1.5 text-muted-foreground/60">·</span>
                    <span>{fmtSize(allFiles[0].size)}</span>
                  </>
                )}
              </p>
            </div>
          </div>
        </DialogHeader>

        {/* Scrollable Content Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5 min-h-0">
          {/* File Pills List for Batch Mode */}
          {isBatch && (
            <div className="space-y-1.5">
              <Label className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                Список файлов в очереди ({allFiles.length})
              </Label>
              <div className="flex flex-wrap gap-1.5 max-h-24 overflow-y-auto p-2 rounded-lg border bg-muted/20">
                {allFiles.map((f, idx) => (
                  <Badge
                    key={idx}
                    variant="secondary"
                    className="text-[11px] py-0.5 font-normal flex items-center gap-1.5 max-w-[200px] truncate"
                  >
                    {checkIsGif(f) ? (
                      <Film className="size-3 text-amber-500 shrink-0" />
                    ) : checkIsVideo(f) ? (
                      <Video className="size-3 text-sky-500 shrink-0" />
                    ) : (
                      <FileImage className="size-3 text-emerald-500 shrink-0" />
                    )}
                    <span className="truncate">{f.name}</span>
                    <span className="text-[10px] text-muted-foreground font-mono">
                      ({fmtSize(f.size)})
                    </span>
                  </Badge>
                ))}
              </div>
            </div>
          )}

          {/* Optional Tag / Placement Selector */}
          {allowedTags && allowedTags.length > 0 && (
            <div className="flex items-center justify-between gap-3 p-3 rounded-lg border border-border/60 bg-card">
              <div className="flex items-center gap-2 text-xs font-medium">
                <Tag className="size-3.5 text-muted-foreground" />
                <span>Назначение (тег):</span>
              </div>
              <div className="w-44">
                <Select value={tag} onValueChange={(v) => { if (v) setTag(v) }}>
                  <SelectTrigger className="h-7 text-xs">
                    <SelectValue placeholder="Выберите" />
                  </SelectTrigger>
                  <SelectContent>
                    {allowedTags.map((t) => (
                      <SelectItem key={t.value} value={t.value} className="text-xs">
                        {t.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          )}

          {/* GIF Selection Cards */}
          {hasGifs && (
            <div className="space-y-2.5">
              <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {isBatch ? `Способ сохранения для GIF (${gifFiles.length} шт.)` : "Способ сохранения анимации"}
              </Label>
              <div className="grid grid-cols-1 gap-2">
                {[
                  {
                    id: "keep_gif" as const,
                    title: "Сохранить GIF (Оригинал)",
                    desc: "Анимация остаётся файлом .gif без потерь качества и перекодирования",
                  },
                  {
                    id: "to_webm" as const,
                    title: "Конвертировать в WebM",
                    desc: "Видео VP9: плавная анимация при размере в 5–10 раз меньше исходного GIF",
                  },
                  {
                    id: "to_static" as const,
                    title: "Статичное фото (WebP)",
                    desc: "Только первый кадр GIF в формате WebP",
                  },
                ].map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setGifChoice(item.id)}
                    className={cn(
                      "flex items-start justify-between p-3.5 rounded-xl border text-left transition-all cursor-pointer relative",
                      gifChoice === item.id
                        ? "border-amber-500 bg-amber-500/10 shadow-xs ring-1 ring-amber-500/30"
                        : "border-border/70 bg-card/60 hover:bg-muted/40 text-muted-foreground",
                    )}
                  >
                    <div className="space-y-0.5">
                      <div className="font-semibold text-xs text-foreground flex items-center gap-2">
                        <span>{item.title}</span>
                      </div>
                      <p className="text-[11px] text-muted-foreground leading-snug">
                        {item.desc}
                      </p>
                    </div>
                    {gifChoice === item.id && (
                      <CheckCircle2 className="size-4 text-amber-500 shrink-0 ml-2" />
                    )}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Video Controls */}
          {hasVideos && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  {isBatch ? `Параметры видео (${videoFiles.length} шт.)` : "Параметры видео"}
                </Label>
              </div>

              {/* Two simple modes: Original vs Compress */}
              <div className="grid grid-cols-2 gap-2.5">
                <button
                  type="button"
                  onClick={() => setVideoMode("original")}
                  className={cn(
                    "flex flex-col items-start p-3.5 rounded-xl border text-left transition-all cursor-pointer relative",
                    videoMode === "original"
                      ? "border-emerald-500 bg-emerald-500/10 shadow-xs ring-1 ring-emerald-500/30"
                      : "border-border/70 bg-card/60 hover:bg-muted/30 text-muted-foreground",
                  )}
                >
                  <div className="flex items-center justify-between w-full mb-1">
                    <div className="flex items-center gap-1.5 font-semibold text-xs text-foreground">
                      <Zap className="size-3.5 text-emerald-500" />
                      <span>Оригинал</span>
                    </div>
                    {videoMode === "original" && (
                      <CheckCircle2 className="size-3.5 text-emerald-500" />
                    )}
                  </div>
                  <p className="text-[11px] text-muted-foreground leading-snug">
                    Мгновенное сохранение без конвертации
                  </p>
                </button>

                <button
                  type="button"
                  onClick={() => setVideoMode("compress")}
                  className={cn(
                    "flex flex-col items-start p-3.5 rounded-xl border text-left transition-all cursor-pointer relative",
                    videoMode === "compress"
                      ? "border-sky-500 bg-sky-500/10 shadow-xs ring-1 ring-sky-500/30"
                      : "border-border/70 bg-card/60 hover:bg-muted/30 text-muted-foreground",
                  )}
                >
                  <div className="flex items-center justify-between w-full mb-1">
                    <div className="flex items-center gap-1.5 font-semibold text-xs text-foreground">
                      <Sliders className="size-3.5 text-sky-500" />
                      <span>Сжатие</span>
                    </div>
                    {videoMode === "compress" && (
                      <CheckCircle2 className="size-3.5 text-sky-500" />
                    )}
                  </div>
                  <p className="text-[11px] text-muted-foreground leading-snug">
                    Перекодирование в лёгкий WebM / MP4
                  </p>
                </button>
              </div>

              {/* Poster Scale Option (Available in both modes) */}
              <div className="p-3 rounded-xl border border-border/70 bg-muted/15 space-y-1.5">
                <div className="flex items-center justify-between">
                  <Label className="text-[11px] font-medium text-muted-foreground">
                    Разрешение постера (превью кадра)
                  </Label>
                  <span className="text-[10px] text-muted-foreground">
                    {posterScale === "1080p"
                      ? "1080p (мгновенно)"
                      : posterScale === "original"
                      ? "Оригинал (до 8K)"
                      : posterScale === "custom"
                      ? customPosterScale || "кастомное"
                      : posterScale}
                  </span>
                </div>
                <Select
                  value={posterScale}
                  onValueChange={(v) => { if (v) setPosterScale(v) }}
                >
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="1080p" className="text-xs">1080p (Рекомендуется, генерация &lt; 1 сек)</SelectItem>
                    <SelectItem value="original" className="text-xs">Оригинал кадра (вплоть до 8K)</SelectItem>
                    <SelectItem value="2160p" className="text-xs">2160p (4K UHD)</SelectItem>
                    <SelectItem value="1440p" className="text-xs">1440p (2K QHD)</SelectItem>
                    <SelectItem value="720p" className="text-xs">720p (HD)</SelectItem>
                    <SelectItem value="480p" className="text-xs">480p (SD)</SelectItem>
                    <SelectItem value="custom" className="text-xs">Своё разрешение…</SelectItem>
                  </SelectContent>
                </Select>
                {posterScale === "custom" && (
                  <div className="pt-1.5">
                    <Input
                      value={customPosterScale}
                      onChange={(e) => setCustomPosterScale(e.target.value)}
                      placeholder="Например: 1200p или 1920x1080"
                      className="h-7 text-xs font-mono"
                    />
                  </div>
                )}
              </div>

              {/* Advanced Technical Options when "compress" is active */}
              {videoMode === "compress" && (
                <div className="rounded-xl border border-border/80 bg-muted/20 p-4 space-y-4 animate-in fade-in-50 duration-200">
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1">
                      <Label className="text-[11px] font-medium text-muted-foreground">Формат контейнера</Label>
                      <Select
                        value={videoFormat}
                        onValueChange={(v) => { if (v) setVideoFormat(v as "webm" | "mp4") }}
                      >
                        <SelectTrigger className="h-8 text-xs">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="webm" className="text-xs">WebM (VP9 + Opus)</SelectItem>
                          <SelectItem value="mp4" className="text-xs">MP4 (H.264 + AAC)</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="space-y-1">
                      <Label className="text-[11px] font-medium text-muted-foreground">Разрешение видео</Label>
                      <Select
                        value={videoScale}
                        onValueChange={(v) => { if (v) setVideoScale(v) }}
                      >
                        <SelectTrigger className="h-8 text-xs">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="original" className="text-xs">Исходное (100%)</SelectItem>
                          <SelectItem value="2160p" className="text-xs">2160p (4K UHD)</SelectItem>
                          <SelectItem value="1440p" className="text-xs">1440p (2K QHD)</SelectItem>
                          <SelectItem value="1080p" className="text-xs">1080p (Full HD)</SelectItem>
                          <SelectItem value="720p" className="text-xs">720p (HD)</SelectItem>
                          <SelectItem value="480p" className="text-xs">480p (SD)</SelectItem>
                          <SelectItem value="360p" className="text-xs">360p (Mobile)</SelectItem>
                          <SelectItem value="custom" className="text-xs">Своё разрешение…</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  {videoScale === "custom" && (
                    <div className="space-y-1">
                      <Label className="text-[10px] text-muted-foreground">Кастомное разрешение видео</Label>
                      <Input
                        value={customScale}
                        onChange={(e) => setCustomScale(e.target.value)}
                        placeholder="Например: 1440p или 1280x720"
                        className="h-7 text-xs font-mono"
                      />
                    </div>
                  )}

                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1">
                      <Label className="text-[11px] font-medium text-muted-foreground">Скорость кодирования</Label>
                      <Select
                        value={videoPreset}
                        onValueChange={(v) => { if (v) setVideoPreset(v) }}
                      >
                        <SelectTrigger className="h-8 text-xs">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="ultrafast" className="text-xs">ultrafast (самый быстрый)</SelectItem>
                          <SelectItem value="superfast" className="text-xs">superfast</SelectItem>
                          <SelectItem value="veryfast" className="text-xs">veryfast (рекомендуется)</SelectItem>
                          <SelectItem value="faster" className="text-xs">faster</SelectItem>
                          <SelectItem value="fast" className="text-xs">fast</SelectItem>
                          <SelectItem value="medium" className="text-xs">medium (баланс)</SelectItem>
                          <SelectItem value="slow" className="text-xs">slow (макс. сжатие)</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="space-y-1">
                      <Label className="text-[11px] font-medium text-muted-foreground">Качество звука</Label>
                      <Select
                        value={audioBitrate}
                        onValueChange={(v) => { if (v) setAudioBitrate(v) }}
                        disabled={muteAudio}
                      >
                        <SelectTrigger className="h-8 text-xs">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="64k" className="text-xs">64 kbps (речь)</SelectItem>
                          <SelectItem value="96k" className="text-xs">96 kbps</SelectItem>
                          <SelectItem value="128k" className="text-xs">128 kbps (стандарт)</SelectItem>
                          <SelectItem value="192k" className="text-xs">192 kbps (высокое)</SelectItem>
                          <SelectItem value="256k" className="text-xs">256 kbps</SelectItem>
                          <SelectItem value="320k" className="text-xs">320 kbps (макс.)</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  {/* CRF Quality Slider */}
                  <div className="space-y-1.5 pt-1">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-medium">
                        Качество сжатия (CRF: <span className="font-mono font-semibold">{videoCrf}</span>)
                      </span>
                      <span className="text-[10px] text-muted-foreground font-mono">
                        {videoCrf <= 22 ? "высокое качество" : videoCrf <= 32 ? "оптимальный баланс" : "макс. сжатие"}
                      </span>
                    </div>
                    <Slider
                      value={[videoCrf]}
                      min={18}
                      max={38}
                      step={1}
                      onValueChange={(val) => {
                        const v = Array.isArray(val) ? val[0] : val
                        if (v != null) setVideoCrf(v)
                      }}
                      className="py-1"
                    />
                    <div className="flex justify-between text-[10px] text-muted-foreground font-mono">
                      <span>18 (тяжёлый)</span>
                      <span>32 (дефолт)</span>
                      <span>38 (легчайший)</span>
                    </div>
                  </div>

                  {/* Audio Mute Toggle */}
                  <div className="flex items-center justify-between pt-2 border-t border-border/40">
                    <div className="flex items-center gap-2 text-xs">
                      {muteAudio ? (
                        <VolumeX className="size-4 text-destructive" />
                      ) : (
                        <Volume2 className="size-4 text-muted-foreground" />
                      )}
                      <span>{muteAudio ? "Звук будет вырезан (Mute)" : "Аудиодорожка сохраняется"}</span>
                    </div>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="h-7 text-xs"
                      onClick={() => setMuteAudio(!muteAudio)}
                    >
                      {muteAudio ? "Включить звук" : "Вырезать звук"}
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer (Pinned to bottom) */}
        <div className="px-6 py-3.5 border-t border-border/60 bg-muted/40 shrink-0 flex items-center justify-between gap-3">
          <div className="text-[11px] text-muted-foreground truncate">
            {isBatch ? (
              <span>Всего файлов: <strong className="text-foreground">{allFiles.length}</strong></span>
            ) : hasGifs ? (
              <span>
                {gifChoice === "keep_gif"
                  ? "Оригинальный .gif"
                  : gifChoice === "to_webm"
                  ? "WebM видео"
                  : "WebP фото"}
              </span>
            ) : hasVideos ? (
              <span>
                {videoMode === "original"
                  ? `Оригинал (постер ${posterScale})`
                  : `${videoFormat.toUpperCase()} · ${videoScale} · CRF ${videoCrf}`}
              </span>
            ) : (
              <span>WebP</span>
            )}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <Button variant="ghost" size="sm" onClick={onCancel}>
              Отмена
            </Button>
            <Button size="sm" onClick={handleStart} className="gap-1.5 shadow-xs">
              <span>{isBatch ? `Загрузить все (${allFiles.length})` : "Загрузить"}</span>
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
