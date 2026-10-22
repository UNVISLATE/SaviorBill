import { useEffect, useState } from "react"
import { Loader2 } from "lucide-react"

import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/shadsnui/card"
import { Switch } from "@/components/shadsnui/switch"
import { Label } from "@/components/shadsnui/label"
import { Button } from "@/components/shadsnui/button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/shadsnui/select"
import { Slider } from "@/components/shadsnui/slider"
import { Badge } from "@/components/shadsnui/badge"
import {
  useAdminUiSettings,
  useUpdateAdminUiSettings,
  type MediaDialogDefaultSettings,
} from "@/api/admin-ui-settings"
import { SettingsSection } from "./SettingsSection"
import { toastError, toastSuccess } from "@/lib/toast"
import { getErrorDetail } from "@/lib/api-error"

const DEFAULT_CONVERT_SETTINGS: MediaDialogDefaultSettings = {
  gif_format: "gif",
  video_format: "webm",
  video_codec: "libvpx-vp9",
  audio_codec: "libopus",
  scale: "original",
  poster_scale: "1080p",
  crf: 32,
  video_preset: "veryfast",
  audio_bitrate: "128k",
}

export function MediaSettingsPage() {
  const { data, isLoading } = useAdminUiSettings()
  const updateMutation = useUpdateAdminUiSettings()

  // Block 1: Modal switch
  const [modalEnabled, setModalEnabled] = useState<boolean>(true)
  const [savedModalEnabled, setSavedModalEnabled] = useState<boolean>(true)

  // Block 2: Default conversion settings
  const [defaults, setDefaults] = useState<MediaDialogDefaultSettings>(DEFAULT_CONVERT_SETTINGS)
  const [savedDefaults, setSavedDefaults] = useState<MediaDialogDefaultSettings>(DEFAULT_CONVERT_SETTINGS)

  useEffect(() => {
    if (data?.mediadialog) {
      const en = data.mediadialog.enabled ?? true
      setModalEnabled(en)
      setSavedModalEnabled(en)

      const def: MediaDialogDefaultSettings = {
        gif_format: data.mediadialog.default?.gif_format || "gif",
        video_format: data.mediadialog.default?.video_format || "webm",
        video_codec: data.mediadialog.default?.video_codec || "libvpx-vp9",
        audio_codec: data.mediadialog.default?.audio_codec || "libopus",
        scale: data.mediadialog.default?.scale || "original",
        poster_scale: data.mediadialog.default?.poster_scale || "1080p",
        crf: data.mediadialog.default?.crf ?? 32,
        video_preset: data.mediadialog.default?.video_preset || "veryfast",
        audio_bitrate: data.mediadialog.default?.audio_bitrate || "128k",
      }
      setDefaults(def)
      setSavedDefaults(def)
    }
  }, [data])

  const isModalDirty = modalEnabled !== savedModalEnabled

  const changedDefaultKeys = (Object.keys(DEFAULT_CONVERT_SETTINGS) as (keyof MediaDialogDefaultSettings)[]).filter(
    (k) => defaults[k] !== savedDefaults[k],
  )
  const isDefaultsDirty = changedDefaultKeys.length > 0

  const handleSaveModal = async () => {
    try {
      await updateMutation.mutateAsync({
        mediadialog: {
          enabled: modalEnabled,
          default: savedDefaults,
        },
      })
      setSavedModalEnabled(modalEnabled)
      toastSuccess("Настройка модального окна сохранена")
    } catch (e: unknown) {
      toastError("Не удалось сохранить настройку", getErrorDetail(e))
    }
  }

  const handleResetModal = () => {
    setModalEnabled(savedModalEnabled)
  }

  const handleSaveDefaults = async () => {
    try {
      await updateMutation.mutateAsync({
        mediadialog: {
          enabled: savedModalEnabled,
          default: defaults,
        },
      })
      setSavedDefaults(defaults)
      toastSuccess("Параметры конвертации по умолчанию сохранены")
    } catch (e: unknown) {
      toastError("Не удалось сохранить параметры", getErrorDetail(e))
    }
  }

  const handleResetDefaults = () => {
    setDefaults(savedDefaults)
  }

  return (
    <div className="columns-1 gap-4 xl:columns-2 [&>*]:break-inside-avoid">
      {/* Блок 1: Модальное окно загрузки медиа */}
      <Card className="mb-4 break-inside-avoid flex flex-col">
        <CardHeader>
          <CardTitle>Модальное окно загрузки медиа</CardTitle>
          <CardDescription>
            Управление отображением диалога параметров конвертации при загрузке видео и GIF.
          </CardDescription>
        </CardHeader>
        <CardContent className="divide-y">
          <div className="flex items-center justify-between gap-6 py-3 first:pt-0 last:pb-0">
            <div className="min-w-0">
              <Label htmlFor="modal-toggle" className="flex items-center gap-1.5 font-normal">
                Показывать модальное окно настроек
              </Label>
              <p className="text-xs text-muted-foreground mt-0.5">
                При отключении видео и GIF будут сразу конвертироваться с параметрами по умолчанию.
              </p>
            </div>
            <div className="w-full max-w-56 shrink-0 flex justify-end">
              <Switch
                id="modal-toggle"
                disabled={isLoading}
                checked={modalEnabled}
                onCheckedChange={setModalEnabled}
              />
            </div>
          </div>
        </CardContent>
        {isModalDirty && (
          <CardFooter className="flex-col items-stretch gap-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-xs text-muted-foreground">Изменено полей: 1</span>
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={handleResetModal}
                  disabled={updateMutation.isPending}
                >
                  Отменить
                </Button>
                <Button
                  size="sm"
                  onClick={handleSaveModal}
                  disabled={updateMutation.isPending}
                >
                  {updateMutation.isPending && <Loader2 className="size-4 animate-spin" />}
                  Сохранить
                </Button>
              </div>
            </div>
          </CardFooter>
        )}
      </Card>

      {/* Блок 2: Параметры конвертации по умолчанию */}
      <Card className="mb-4 break-inside-avoid flex flex-col">
        <CardHeader>
          <CardTitle>Параметры конвертации по умолчанию</CardTitle>
          <CardDescription>
            Начальные значения для диалога загрузки или параметры для фоновой автоматической конвертации.
          </CardDescription>
        </CardHeader>
        <CardContent className="divide-y">
          {/* GIF format */}
          <div className="flex items-center justify-between gap-6 py-3 first:pt-0 last:pb-0">
            <div className="min-w-0">
              <Label className="flex items-center gap-1.5 font-normal">
                Формат для GIF
              </Label>
              <p className="text-xs text-muted-foreground mt-0.5">
                Формат при загрузке анимированных GIF.
              </p>
            </div>
            <div className="w-full max-w-56 shrink-0">
              <Select
                value={defaults.gif_format}
                onValueChange={(val) => setDefaults((p) => ({ ...p, gif_format: val || "gif" }))}
              >
                <SelectTrigger className="w-full h-8 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="gif">Оставить GIF (исходная анимация)</SelectItem>
                  <SelectItem value="webm">WebM (эффективное видео)</SelectItem>
                  <SelectItem value="webp">WebP (статичное изображение)</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Video format */}
          <div className="flex items-center justify-between gap-6 py-3 first:pt-0 last:pb-0">
            <div className="min-w-0">
              <Label className="flex items-center gap-1.5 font-normal">
                Формат видео
              </Label>
              <p className="text-xs text-muted-foreground mt-0.5">
                Основной формат сохранения видеофайлов.
              </p>
            </div>
            <div className="w-full max-w-56 shrink-0">
              <Select
                value={defaults.video_format}
                onValueChange={(val) => setDefaults((p) => ({ ...p, video_format: val || "webm" }))}
              >
                <SelectTrigger className="w-full h-8 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="original">Оригинал (без пережатия / copy)</SelectItem>
                  <SelectItem value="webm">WebM (VP9)</SelectItem>
                  <SelectItem value="mp4">MP4 (H.264)</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Poster scale */}
          <div className="flex items-center justify-between gap-6 py-3 first:pt-0 last:pb-0">
            <div className="min-w-0">
              <Label className="flex items-center gap-1.5 font-normal">
                Разрешение постера
              </Label>
              <p className="text-xs text-muted-foreground mt-0.5">
                Разрешение генерируемой обложки видео.
              </p>
            </div>
            <div className="w-full max-w-56 shrink-0">
              <Select
                value={defaults.poster_scale}
                onValueChange={(val) => setDefaults((p) => ({ ...p, poster_scale: val || "1080p" }))}
              >
                <SelectTrigger className="w-full h-8 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="original">Оригинальное (до 4K/8K)</SelectItem>
                  <SelectItem value="2160p">2160p (4K UHD)</SelectItem>
                  <SelectItem value="1440p">1440p (2K QHD)</SelectItem>
                  <SelectItem value="1080p">1080p (Full HD)</SelectItem>
                  <SelectItem value="720p">720p (HD)</SelectItem>
                  <SelectItem value="480p">480p (SD)</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Video scale */}
          <div className="flex items-center justify-between gap-6 py-3 first:pt-0 last:pb-0">
            <div className="min-w-0">
              <Label className="flex items-center gap-1.5 font-normal">
                Разрешение видео
              </Label>
              <p className="text-xs text-muted-foreground mt-0.5">
                Ограничение максимального разрешения видео.
              </p>
            </div>
            <div className="w-full max-w-56 shrink-0">
              <Select
                value={defaults.scale}
                onValueChange={(val) => setDefaults((p) => ({ ...p, scale: val || "original" }))}
              >
                <SelectTrigger className="w-full h-8 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="original">Оригинальное (без масштабирования)</SelectItem>
                  <SelectItem value="2160p">2160p (4K UHD)</SelectItem>
                  <SelectItem value="1440p">1440p (2K QHD)</SelectItem>
                  <SelectItem value="1080p">1080p (Full HD)</SelectItem>
                  <SelectItem value="720p">720p (HD)</SelectItem>
                  <SelectItem value="480p">480p (SD)</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Video codec */}
          <div className="flex items-center justify-between gap-6 py-3 first:pt-0 last:pb-0">
            <div className="min-w-0">
              <Label className="flex items-center gap-1.5 font-normal">
                Видеокодек
              </Label>
              <p className="text-xs text-muted-foreground mt-0.5">
                Кодек для пережатия видеодорожки.
              </p>
            </div>
            <div className="w-full max-w-56 shrink-0">
              <Select
                value={defaults.video_codec}
                onValueChange={(val) => setDefaults((p) => ({ ...p, video_codec: val || "libvpx-vp9" }))}
              >
                <SelectTrigger className="w-full h-8 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="libvpx-vp9">VP9 (libvpx-vp9)</SelectItem>
                  <SelectItem value="libx264">H.264 (libx264)</SelectItem>
                  <SelectItem value="copy">Копировать без сжатия (copy)</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Audio codec */}
          <div className="flex items-center justify-between gap-6 py-3 first:pt-0 last:pb-0">
            <div className="min-w-0">
              <Label className="flex items-center gap-1.5 font-normal">
                Аудиокодек
              </Label>
              <p className="text-xs text-muted-foreground mt-0.5">
                Кодек для звуковой дорожки.
              </p>
            </div>
            <div className="w-full max-w-56 shrink-0">
              <Select
                value={defaults.audio_codec}
                onValueChange={(val) => setDefaults((p) => ({ ...p, audio_codec: val || "libopus" }))}
              >
                <SelectTrigger className="w-full h-8 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="libopus">Opus (libopus)</SelectItem>
                  <SelectItem value="aac">AAC (aac)</SelectItem>
                  <SelectItem value="copy">Копировать поток (copy)</SelectItem>
                  <SelectItem value="none">Без звука (удалить аудио)</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Video preset */}
          <div className="flex items-center justify-between gap-6 py-3 first:pt-0 last:pb-0">
            <div className="min-w-0">
              <Label className="flex items-center gap-1.5 font-normal">
                Пресет кодирования x264
              </Label>
              <p className="text-xs text-muted-foreground mt-0.5">
                Скорость сжатия видеопотока (влияет на нагрузку процессора).
              </p>
            </div>
            <div className="w-full max-w-56 shrink-0">
              <Select
                value={defaults.video_preset || "veryfast"}
                onValueChange={(val) => setDefaults((p) => ({ ...p, video_preset: val || "veryfast" }))}
              >
                <SelectTrigger className="w-full h-8 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="ultrafast">ultrafast (минимальная нагрузка)</SelectItem>
                  <SelectItem value="superfast">superfast</SelectItem>
                  <SelectItem value="veryfast">veryfast (рекомендуется)</SelectItem>
                  <SelectItem value="faster">faster</SelectItem>
                  <SelectItem value="fast">fast</SelectItem>
                  <SelectItem value="medium">medium (баланс)</SelectItem>
                  <SelectItem value="slow">slow (высокая плотность)</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Audio bitrate */}
          <div className="flex items-center justify-between gap-6 py-3 first:pt-0 last:pb-0">
            <div className="min-w-0">
              <Label className="flex items-center gap-1.5 font-normal">
                Битрейт аудио
              </Label>
              <p className="text-xs text-muted-foreground mt-0.5">
                Качество сжатия аудиодорожки (AAC/Opus).
              </p>
            </div>
            <div className="w-full max-w-56 shrink-0">
              <Select
                value={defaults.audio_bitrate || "128k"}
                onValueChange={(val) => setDefaults((p) => ({ ...p, audio_bitrate: val || "128k" }))}
              >
                <SelectTrigger className="w-full h-8 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="64k">64 kbps (речь/минимальный)</SelectItem>
                  <SelectItem value="96k">96 kbps</SelectItem>
                  <SelectItem value="128k">128 kbps (стандарт)</SelectItem>
                  <SelectItem value="192k">192 kbps (высокое качество)</SelectItem>
                  <SelectItem value="256k">256 kbps</SelectItem>
                  <SelectItem value="320k">320 kbps (максимальное)</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* CRF Quality Slider */}
          <div className="space-y-2 py-3 first:pt-0 last:pb-0">
            <div className="flex items-center justify-between">
              <div>
                <Label className="flex items-center gap-1.5 font-normal">
                  Качество сжатия (CRF)
                </Label>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Баланс между размером и качеством (меньше — выше качество, больше — меньше размер).
                </p>
              </div>
              <Badge variant="outline" className="font-mono text-xs">
                CRF {defaults.crf}
              </Badge>
            </div>
            <div className="pt-2">
              <Slider
                value={[defaults.crf]}
                min={18}
                max={38}
                step={1}
                onValueChange={(val) => {
                  const num = Array.isArray(val) ? val[0] : Number(val)
                  setDefaults((p) => ({ ...p, crf: num }))
                }}
              />
              <div className="flex justify-between text-[10px] text-muted-foreground pt-1.5">
                <span>18 (максимальное качество)</span>
                <span>28 (баланс)</span>
                <span>38 (максимальное сжатие)</span>
              </div>
            </div>
          </div>
        </CardContent>

        {isDefaultsDirty && (
          <CardFooter className="flex-col items-stretch gap-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-xs text-muted-foreground">
                Изменено полей: {changedDefaultKeys.length}
              </span>
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={handleResetDefaults}
                  disabled={updateMutation.isPending}
                >
                  Отменить
                </Button>
                <Button
                  size="sm"
                  onClick={handleSaveDefaults}
                  disabled={updateMutation.isPending}
                >
                  {updateMutation.isPending && <Loader2 className="size-4 animate-spin" />}
                  Сохранить
                </Button>
              </div>
            </div>
          </CardFooter>
        )}
      </Card>

      {/* Блок 3: Ограничения медиа (перенесено из /settings/general) */}
      <SettingsSection
        title="Ограничения медиа"
        description="Ограничения на загрузку и хранение файлов пользователями."
        fields={[
          {
            key: "media.quota.image_bytes",
            label: "Квота хранения (фото)",
            kind: "number",
            suffix: "байт",
            placeholder: "52428800",
            hint: "Суммарный объём файлов аккаунта без права media.upload.video. По умолчанию 50 MiB.",
          },
          {
            key: "media.quota.video_bytes",
            label: "Квота хранения (видео)",
            kind: "number",
            suffix: "байт",
            placeholder: "2147483648",
            hint: "То же для аккаунтов с правом media.upload.video. По умолчанию 2 GiB.",
          },
          {
            key: "media.small_max_bytes",
            label: "Размер файла (фото)",
            kind: "number",
            suffix: "байт",
            hint: "Потолок для одной загрузки без права media.upload.video.",
          },
          {
            key: "media.max_bytes",
            label: "Размер файла (видео)",
            kind: "number",
            suffix: "байт",
            hint: "Потолок для одной загрузки с правом media.upload.video.",
          },
          {
            key: "media.uploads_per_hour",
            label: "Загрузок в час",
            kind: "number",
            hint: "Не применяется к аккаунтам с правом media.upload.video.",
          },
          {
            key: "user.media.limit",
            label: "Файлов на аккаунт",
            kind: "number",
            hint: "Жёсткий отказ при превышении — старые файлы не удаляются автоматически.",
          },
        ]}
      />
    </div>
  )
}
