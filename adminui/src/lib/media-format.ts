/** Общие форматтеры для карточек/модалок медиа-галереи (§5, ProfileMediaSection). */

export const STATUS_VARIANT: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  ready: "default",
  processing: "secondary",
  queued: "secondary",
  failed: "destructive",
  error: "destructive",
}

export const STATUS_LABEL: Record<string, string> = {
  ready: "готово",
  processing: "обработка",
  queued: "в очереди",
  failed: "ошибка",
  error: "ошибка",
}

export function fmtSize(bytes: number | null | undefined): string {
  if (!bytes) return "—"
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} КБ`
  return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`
}

export function fmtDateTime(iso: string): string {
  return new Date(iso).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

/** Человекочитаемый ETA конвертации (секунды -> "≈2 мин 30 с"). */
export function fmtEta(sec: number | null | undefined): string | null {
  if (sec == null || !Number.isFinite(sec) || sec < 0) return null
  if (sec < 60) return `≈${Math.round(sec)} с`
  const m = Math.floor(sec / 60)
  const s = Math.round(sec % 60)
  return s > 0 ? `≈${m} мин ${s} с` : `≈${m} мин`
}

function fmtDuration(sec: number): string {
  const m = Math.floor(sec / 60)
  const s = Math.round(sec % 60)
  return m > 0 ? `${m}:${String(s).padStart(2, "0")}` : `${s} с`
}

/**
 * Технические метаданные (``system_media.meta``, см. §5.7) как готовые
 * пары "подпись/значение" для панели информации в модалке превью-галереи.
 * Только техническое — без EXIF/geo, см. решение по вопросам §5.7 в плане.
 */
export function metaRows(
  meta: Record<string, number> | null | undefined,
  kind: string,
): { label: string; value: string }[] {
  if (!meta) return []
  const rows: { label: string; value: string }[] = []
  if (meta.width && meta.height) {
    rows.push({ label: "Разрешение", value: `${meta.width}×${meta.height}` })
  }
  if (kind === "video") {
    if (meta.duration_sec != null) {
      rows.push({ label: "Длительность", value: fmtDuration(meta.duration_sec) })
    }
    if (meta.codec) rows.push({ label: "Кодек", value: String(meta.codec).toUpperCase() })
    if (meta.fps) rows.push({ label: "FPS", value: String(meta.fps) })
    if (meta.bitrate) rows.push({ label: "Битрейт", value: `${Math.round(meta.bitrate / 1000)} кбит/с` })
  }
  return rows
}
