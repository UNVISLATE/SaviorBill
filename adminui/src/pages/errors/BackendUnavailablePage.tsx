import { RefreshCw } from "lucide-react"

import { Button } from "@/components/shadsnui/button"

export function BackendUnavailablePage({
  onRetry,
  errorMessage,
}: {
  onRetry?: () => void
  errorMessage?: string
}) {
  return (
    <div className="flex min-h-svh flex-col items-center justify-center p-6 text-center select-none bg-background">
      <div className="flex max-w-md flex-col items-center gap-6">
        <div className="relative">
          <div
            className="absolute -inset-4 rounded-full bg-amber-500/10 blur-2xl pointer-events-none"
            aria-hidden
          />
          <img
            src="/unvi/mascot/MaintenanceMascotUNVI.webp"
            alt="Бэкенд недоступен"
            className="relative size-56 object-contain drop-shadow-md transition-transform hover:scale-105 duration-300"
          />
        </div>

        <div className="space-y-2">
          <span className="inline-block rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 font-mono text-xs font-semibold text-amber-500">
            Связь с сервером потеряна
          </span>
          <h1 className="text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
            Бэкенд недоступен
          </h1>
          <p className="text-sm text-muted-foreground">
            Не удалось установить соединение с API-сервером SaviorBill. Возможно, ведутся технические работы или перезапускается контейнер.
          </p>
          {errorMessage && (
            <p className="font-mono text-xs text-destructive/80 bg-destructive/10 p-2 rounded-lg border border-destructive/20 max-w-sm overflow-hidden text-ellipsis">
              {errorMessage}
            </p>
          )}
        </div>

        <div className="flex items-center gap-3">
          <Button
            size="sm"
            onClick={() => {
              if (onRetry) onRetry()
              else window.location.reload()
            }}
            className="gap-2"
          >
            <RefreshCw className="size-4" /> Повторить подключение
          </Button>
        </div>
      </div>
    </div>
  )
}

export default BackendUnavailablePage
