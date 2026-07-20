import { api } from "@/lib/api"

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

/**
 * Загрузить файл как медиа текущего пользователя и дождаться готовности
 * (конвертация в mediaworker асинхронная — статус приходит по поллингу).
 *
 * Поток: mediaworker (`/api/media/upload`, отдельный сервис — см.
 * vite.config.ts и deploy/Caddyfile) выдаёт одноразовый upload_token → сам
 * файл льётся туда же по upload_url → billing (`/v1/media/status/{token}`)
 * знает о готовности по мере конвертации → как только `state === "ready"`,
 * находим числовой `media_id` по списку `/v1/user/media` (сам статус его не
 * возвращает) для `PUT /v1/user/me/avatar`.
 */
/**
 * Загрузить файл (шаги 1+2), не дожидаясь готовности конвертации — вернуть
 * сразу после приёма файла mediaworker'ом (``state: "queued"``).
 *
 * Используется там, где готовность отслеживается отдельно и параллельно для
 * нескольких файлов сразу (WS ``/apiws/v1/media/mine``, см.
 * ``hooks/use-media-status-ws.ts``) — в отличие от ``uploadOwnMedia()``,
 * которая гоняет REST-поллинг сама и ждёт синхронно один файл.
 */
export async function beginOwnMediaUpload(
  file: File,
  opts: { tag?: string; onProgress?: (p: UploadProgress) => void; signal?: AbortSignal } = {},
): Promise<{ token: string }> {
  const { data: initiate } = await api.post<InitiateResponse>("/media/upload", null, {
    params: opts.tag ? { tag: opts.tag } : undefined,
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
  opts: { tag?: string; onProgress?: (p: UploadProgress) => void; signal?: AbortSignal } = {},
): Promise<{ mediaId: number; token: string }> {
  if (opts.tag === "avatar" && !file.type.startsWith("image/")) {
    // Серверный set_avatar тоже это проверяет (kind !== "image" → 400), но
    // без этой проверки видео сначала долго конвертируется в mediaworker и
    // только потом отбрасывается — впустую тратим слот конвертации и время
    // пользователя на файл, который заведомо не подойдёт.
    throw new Error("для аватара нужна картинка (jpg/png/webp), не видео")
  }

  const { data: initiate } = await api.post<InitiateResponse>("/media/upload", null, {
    params: opts.tag ? { tag: opts.tag } : undefined,
  })

  // upload_url приходит абсолютным ("/api/media/upload/{token}") — у `api`
  // уже есть baseURL="/api", так что префикс нужно срезать, иначе получится
  // "/api/api/media/...".
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
