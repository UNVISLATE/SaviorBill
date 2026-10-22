import { api } from "@/api/api.ts"

export interface UploadProgress {
  loaded: number
  total: number
}

interface InitiateResponse {
  upload_token: string
  expires_in: number
  upload_url: string
}

interface UploadStepResponse {
  token: string
  status: string
}

interface MediaStatusResponse {
  token: string
  state: string
  url: string | null
  mime: string | null
  tag: string | null
  error: string | null
}

interface MediaListItem {
  id: number
  token: string
  status: string
}

const POLL_INTERVAL_MS = 700
const POLL_TIMEOUT_MS = 60_000

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

export interface MediaUploadConfig {
  video_codec?: "copy" | "libvpx-vp9" | "libx264"
  audio_codec?: "copy" | "libopus" | "aac" | "none"
  format?: "original" | "webm" | "mp4" | "gif" | "webp"
  scale?: string
  poster_scale?: string
  crf?: number
  video_preset?: string
  audio_bitrate?: string
  keep_animation?: boolean
  tag?: string
}

export function isMediaConfigRequired(file: File): boolean {
  if (file.type === "image/gif" || file.name.toLowerCase().endsWith(".gif")) return true
  if (file.type.startsWith("video/") || /\.(mp4|webm|mkv|mov|avi)$/i.test(file.name)) return true
  return false
}

export interface BeginUploadOptions extends MediaUploadConfig {
  onProgress?: (p: UploadProgress) => void
  signal?: AbortSignal
}

function buildUploadParams(opts: BeginUploadOptions): Record<string, string | number | boolean> {
  const params: Record<string, string | number | boolean> = {}
  if (opts.tag) params.tag = opts.tag
  if (opts.video_codec) params.video_codec = opts.video_codec
  if (opts.audio_codec) params.audio_codec = opts.audio_codec
  if (opts.format) params.format = opts.format
  if (opts.scale) params.scale = opts.scale
  if (opts.poster_scale) params.poster_scale = opts.poster_scale
  if (opts.crf != null) params.crf = opts.crf
  if (opts.video_preset) params.video_preset = opts.video_preset
  if (opts.audio_bitrate) params.audio_bitrate = opts.audio_bitrate
  if (opts.keep_animation != null) params.keep_animation = opts.keep_animation
  return params
}

/**
 * Загрузить файл (шаги 1+2), не дожидаясь готовности конвертации — вернуть
 * сразу после приёма файла mediaworker'ом (``state: "queued"``).
 *
 * Используется там, где готовность отслеживается отдельно и параллельно для
 * нескольких файлов сразу (WS ``/api/media/mine``, см.
 * ``hooks/use-media-status-ws.ts``).
 */
export async function beginOwnMediaUpload(
  file: File,
  opts: BeginUploadOptions = {},
): Promise<{ token: string }> {
  const params = buildUploadParams(opts)

  const { data: initiate } = await api.post<InitiateResponse>("/media/upload", null, {
    params: Object.keys(params).length > 0 ? params : undefined,
  })
  const uploadPath = initiate.upload_url.replace(/^\/api/, "")
  const { data: uploaded } = await api.post<UploadStepResponse>(uploadPath, file, {
    headers: { "Content-Type": file.type || "application/octet-stream" },
    signal: opts.signal,
    onUploadProgress: (e) => {
      opts.onProgress?.({ loaded: e.loaded, total: e.total ?? file.size })
    },
  })
  return { token: uploaded.token }
}

export async function uploadOwnMedia(
  file: File,
  opts: BeginUploadOptions = {},
): Promise<{ mediaId: number; token: string }> {
  if (opts.tag === "avatar" && !file.type.startsWith("image/")) {
    throw new Error("для аватара нужна картинка (jpg/png/webp), не видео")
  }

  const params = buildUploadParams(opts)

  const { data: initiate } = await api.post<InitiateResponse>("/media/upload", null, {
    params: Object.keys(params).length > 0 ? params : undefined,
  })

  const uploadPath = initiate.upload_url.replace(/^\/api/, "")

  const { data: uploaded } = await api.post<UploadStepResponse>(uploadPath, file, {
    headers: { "Content-Type": file.type || "application/octet-stream" },
    signal: opts.signal,
    onUploadProgress: (e) => {
      opts.onProgress?.({ loaded: e.loaded, total: e.total ?? file.size })
    },
  })

  const mediaToken = uploaded.token
  const deadline = Date.now() + POLL_TIMEOUT_MS
  while (Date.now() < deadline) {
    const { data: st } = await api.get<MediaStatusResponse>(`/v1/media/status/${mediaToken}`)
    if (st.state === "ready") break
    if (st.state === "error" || st.state === "failed") {
      throw new Error(st.error || "не удалось обработать файл")
    }
    await sleep(POLL_INTERVAL_MS)
  }

  // Статус не отдаёт числовой id — берём его из списка собственных медиа.
  const { data: page } = await api.get<{ items: MediaListItem[] }>("/v1/user/media", {
    params: { limit: 10, offset: 0 },
  })
  const found = page.items.find((m) => m.token === mediaToken)
  if (!found) {
    throw new Error("файл обработан, но не найден в списке медиа")
  }
  return { mediaId: found.id, token: mediaToken }
}
