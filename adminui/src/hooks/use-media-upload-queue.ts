import { useEffect, useRef, useState, useMemo } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { api } from "@/api/api.ts"
import { beginOwnMediaUpload, type UploadProgress } from "@/api/media-upload.ts"
import { useMediaStatusStream } from "@/hooks/use-media-status-ws"
import type { MediaUploadConfig } from "@/components/media/MediaUploadConfigModal"

export interface UploadJob {
  id: string
  file: File | null
  previewUrl: string | null
  fileName: string
  fileSize: number
  phase: "uploading" | "queued" | "processing" | "done" | "error"
  uploadPct: number
  token: string | null
  convertPct: number | null
  etaSec: number | null
  error: string | null
  mediaId?: number | null
  tag?: string | null
  config?: MediaUploadConfig | null
}

interface ActiveJobDto {
  token: string
  op: string
  state: string
  error: string | null
  percent: number | null
  eta_sec: number | null
}

interface UserMediaItem {
  id: number
  token: string
}

export interface UseMediaUploadQueueOptions {
  tag?: string
  autoRestoreJobs?: boolean
  queryKeysToInvalidate?: (string | unknown)[]
  onJobSuccess?: (job: UploadJob, mediaId?: number) => void | Promise<void>
}

let jobSeq = 0

export function useMediaUploadQueue(options: UseMediaUploadQueueOptions = {}) {
  const {
    tag: defaultTag,
    autoRestoreJobs = true,
    queryKeysToInvalidate,
    onJobSuccess,
  } = options

  const qc = useQueryClient()
  const [jobs, setJobs] = useState<UploadJob[]>([])
  const processedReadyTokens = useRef<Set<string>>(new Set())

  // Restore queued/processing jobs on mount / reload
  useEffect(() => {
    if (!autoRestoreJobs) return
    let cancelled = false
    api
      .get<ActiveJobDto[]>("/v1/user/media/jobs")
      .then(({ data: active }) => {
        if (cancelled) return
        const restored = active
          .filter((j) => j.op === "convert" && (j.state === "queued" || j.state === "processing"))
          .map<UploadJob>((j) => ({
            id: `restored:${j.token}`,
            file: null,
            previewUrl: null,
            fileName: `Медиа ${j.token.slice(0, 8)}`,
            fileSize: 0,
            phase: j.state === "queued" ? "queued" : "processing",
            uploadPct: 100,
            token: j.token,
            convertPct: j.percent,
            etaSec: j.eta_sec,
            error: j.error,
          }))

        if (restored.length === 0) return
        setJobs((prev) => {
          const knownTokens = new Set(prev.map((j) => j.token).filter(Boolean))
          const newJobs = restored.filter((j) => !knownTokens.has(j.token))
          return [...newJobs, ...prev]
        })
      })
      .catch(() => {
        // Best-effort restoration
      })

    return () => {
      cancelled = true
    }
  }, [autoRestoreJobs])

  // Extract pending tokens to feed into WebSocket
  const pendingTokens = useMemo(() => {
    return jobs
      .filter((j) => (j.phase === "processing" || j.phase === "queued") && j.token)
      .map((j) => j.token as string)
  }, [jobs])

  const statuses = useMediaStatusStream(pendingTokens)

  // Derive display jobs by applying real-time WebSocket progress snapshots
  const displayJobs: UploadJob[] = useMemo(() => {
    return jobs.map((j) => {
      if ((j.phase !== "processing" && j.phase !== "queued") || !j.token) return j
      const snap = statuses[j.token]
      if (!snap) return j

      if (snap.state === "ready") {
        return { ...j, phase: "done", convertPct: 100, etaSec: 0 }
      }
      if (snap.state === "error" || snap.state === "failed") {
        return {
          ...j,
          phase: "error",
          error: snap.error || "Не удалось обработать медиа",
        }
      }
      return {
        ...j,
        phase: snap.state === "queued" ? "queued" : "processing",
        convertPct: snap.percent != null ? Number(snap.percent) : j.convertPct,
        etaSec: snap.eta_sec != null ? Number(snap.eta_sec) : j.etaSec,
      }
    })
  }, [jobs, statuses])

  // Handle completions: invalidate queries & fire onJobSuccess callback
  const phaseKey = displayJobs.map((j) => `${j.id}:${j.phase}:${j.token}`).join(",")
  useEffect(() => {
    const readyJobs = displayJobs.filter((j) => j.phase === "done" && j.token)
    if (readyJobs.length === 0) return

    for (const job of readyJobs) {
      const tok = job.token!
      if (processedReadyTokens.current.has(tok)) continue
      processedReadyTokens.current.add(tok)

      // Query invalidation
      if (queryKeysToInvalidate) {
        queryKeysToInvalidate.forEach((qk) => {
          if (Array.isArray(qk)) {
            qc.invalidateQueries({ queryKey: qk })
          } else if (typeof qk === "string") {
            qc.invalidateQueries({ queryKey: [qk] })
          }
        })
      }
      qc.invalidateQueries({ queryKey: ["user-media"] })
      qc.invalidateQueries({ queryKey: ["admin-media"] })

      // If consumer wants a callback with mediaId
      if (onJobSuccess) {
        api
          .get<{ items: UserMediaItem[] }>("/v1/user/media", {
            params: { limit: 10, offset: 0 },
          })
          .then(({ data: page }) => {
            const found = page.items?.find((m) => m.token === tok)
            void onJobSuccess(job, found?.id)
          })
          .catch(() => {
            void onJobSuccess(job, undefined)
          })
      }
    }

    // Schedule cleanup of done jobs after a brief display so user sees 100%
    const doneIds = readyJobs.map((j) => j.id)
    const timer = setTimeout(() => {
      setJobs((prev) => prev.filter((j) => !doneIds.includes(j.id)))
    }, 1500)

    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phaseKey])

  // Start single file upload
  const uploadFile = (
    file: File,
    config?: MediaUploadConfig,
    customTag?: string,
  ): Promise<string> => {
    const id = `job_${Date.now()}_${++jobSeq}`
    const isImage = file.type.startsWith("image/")
    const previewUrl = isImage ? URL.createObjectURL(file) : null
    const tag = customTag ?? defaultTag

    const newJob: UploadJob = {
      id,
      file,
      previewUrl,
      fileName: file.name,
      fileSize: file.size,
      phase: "uploading",
      uploadPct: 0,
      token: null,
      convertPct: null,
      etaSec: null,
      error: null,
      tag,
      config,
    }

    setJobs((prev) => [newJob, ...prev])

    return new Promise((resolve, reject) => {
      beginOwnMediaUpload(file, {
        tag,
        video_codec: config?.video_codec,
        audio_codec: config?.audio_codec,
        format: config?.format,
        scale: config?.scale,
        poster_scale: config?.poster_scale,
        crf: config?.crf,
        keep_animation: config?.keep_animation,
        onProgress: (p: UploadProgress) => {
          const pct = p.total ? Math.round((p.loaded / p.total) * 100) : 0
          setJobs((prev) =>
            prev.map((j) => (j.id === id ? { ...j, uploadPct: pct } : j)),
          )
        },
      })
        .then(({ token }) => {
          setJobs((prev) =>
            prev.map((j) =>
              j.id === id ? { ...j, phase: "queued", token, uploadPct: 100 } : j,
            ),
          )
          resolve(token)
        })
        .catch((err) => {
          const msg =
            err?.response?.data?.detail ??
            err?.message ??
            "Не удалось загрузить файл"
          setJobs((prev) =>
            prev.map((j) =>
              j.id === id ? { ...j, phase: "error", error: String(msg) } : j,
            ),
          )
          reject(err)
        })
    })
  }

  // Start multiple uploads
  const uploadBatch = async (
    files: FileList | File[],
    config?: MediaUploadConfig,
    customTag?: string,
  ) => {
    const list = Array.from(files).filter(
      (f) => f.type.startsWith("image/") || f.type.startsWith("video/"),
    )
    const results: string[] = []
    for (const f of list) {
      try {
        const token = await uploadFile(f, config, customTag)
        results.push(token)
      } catch {
        // Individual error handled inside uploadFile
      }
    }
    return results
  }

  const retryJob = (id: string) => {
    const target = jobs.find((j) => j.id === id)
    if (!target || !target.file) return
    setJobs((prev) =>
      prev.map((j) =>
        j.id === id
          ? {
              ...j,
              phase: "uploading",
              uploadPct: 0,
              token: null,
              convertPct: null,
              etaSec: null,
              error: null,
            }
          : j,
      ),
    )
    void uploadFile(target.file, target.config ?? undefined, target.tag ?? undefined)
  }

  const removeJob = (id: string) => {
    setJobs((prev) => prev.filter((j) => j.id !== id))
  }

  const clearDone = () => {
    setJobs((prev) => prev.filter((j) => j.phase !== "done"))
  }

  const isBusy = displayJobs.some(
    (j) => j.phase === "uploading" || j.phase === "queued" || j.phase === "processing",
  )

  return {
    jobs: displayJobs,
    isBusy,
    uploadFile,
    uploadBatch,
    retryJob,
    removeJob,
    clearDone,
  }
}
