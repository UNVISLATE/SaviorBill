import { useState } from "react"
import { AlertCircle, Loader2, RefreshCw, RotateCcw, ServerCrash } from "lucide-react"

import { Button } from "@/components/shadsnui/button"

export function BackendUnavailablePage({
  onRetry,
  errorMessage,
}: {
  onRetry?: () => void
  errorMessage?: string
}) {
  const [retrying, setRetrying] = useState(false)
  const [imgError, setImgError] = useState(false)

  const handleRetry = async () => {
    if (retrying) return
    setRetrying(true)
    try {
      if (onRetry) {
        await onRetry()
      } else {
        window.location.reload()
      }
    } finally {
      setTimeout(() => setRetrying(false), 800)
    }
  }

  return (
    <div className="relative flex min-h-svh w-full items-center justify-center overflow-hidden bg-background p-4 sm:p-6 select-none">
      {/* Background ambient glow */}
      <div
        className="pointer-events-none absolute -top-40 left-1/2 -translate-x-1/2 size-96 rounded-full bg-amber-500/10 blur-3xl"
        aria-hidden
      />

      <div className="relative flex w-full max-w-lg flex-col items-center rounded-2xl border bg-card/75 p-8 text-center shadow-2xl ring-1 ring-foreground/5 backdrop-blur-md sm:p-10">
        {/* Mascot / Icon container */}
        <div className="relative mb-6 flex size-44 items-center justify-center">
          <div
            className="absolute inset-2 rounded-full bg-amber-500/15 blur-2xl pointer-events-none"
            aria-hidden
          />
          {!imgError ? (
            <img
              src="/unvi/mascot/MaintenanceMascotUNVI.webp"
              alt="Бэкенд недоступен"
              onError={() => setImgError(true)}
              className="relative size-full object-contain drop-shadow-lg transition-transform duration-300 hover:scale-105"
            />
          ) : (
            <div className="relative flex size-28 items-center justify-center rounded-2xl border border-amber-500/30 bg-amber-500/10 text-amber-500 shadow-inner">
              <ServerCrash className="size-14 animate-pulse" />
            </div>
          )}
        </div>

        {/* Status Badge */}
        <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-amber-500/30 bg-amber-500/10 px-3.5 py-1 text-xs font-semibold text-amber-500 font-mono tracking-wide">
          <span className="size-2 rounded-full bg-amber-500 animate-ping" />
          <span>HTTP 503 · Связь с сервером потеряна</span>
        </div>

        {/* Title & Description */}
        <h1 className="mb-2 text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
          Сервис временно недоступен
        </h1>
        <p className="mb-6 max-w-md text-sm leading-relaxed text-muted-foreground">
          Не удалось связаться с API-сервером SaviorBill. Возможно, ведутся технические работы, обновляется система или перезапускается инстанс контейнера.
        </p>

        {/* Error message detail box */}
        {errorMessage && (
          <div className="mb-6 w-full max-w-md rounded-xl border border-destructive/25 bg-destructive/10 p-3.5 text-left text-xs text-destructive/90">
            <div className="flex items-center gap-1.5 font-semibold text-destructive mb-1">
              <AlertCircle className="size-3.5 shrink-0" />
              <span>Технические детали</span>
            </div>
            <p className="font-mono break-all leading-normal opacity-90">{errorMessage}</p>
          </div>
        )}

        {/* Action buttons */}
        <div className="flex flex-wrap items-center justify-center gap-3 w-full sm:w-auto">
          <Button
            size="default"
            onClick={handleRetry}
            disabled={retrying}
            className="w-full sm:w-auto gap-2 font-medium"
          >
            {retrying ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <RefreshCw className="size-4" />
            )}
            {retrying ? "Проверка связи…" : "Повторить подключение"}
          </Button>

          <Button
            size="default"
            variant="outline"
            onClick={() => window.location.reload()}
            className="w-full sm:w-auto gap-2"
          >
            <RotateCcw className="size-4" />
            Обновить страницу
          </Button>
        </div>
      </div>
    </div>
  )
}

export default BackendUnavailablePage
