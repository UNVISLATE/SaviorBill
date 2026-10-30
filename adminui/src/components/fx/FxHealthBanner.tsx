import { useQuery } from "@tanstack/react-query"
import { AlertTriangle, ArrowRight } from "lucide-react"
import { Link } from "react-router-dom"

import { api } from "@/api/api.ts"

interface FxHealth {
  has_errors: boolean
  count: number
  errors: Array<{
    id: number
    name: string
    provider: string | null
    error: string
    error_at: string | null
  }>
}

export function FxHealthBanner() {
  const { data: health } = useQuery({
    queryKey: ["admin-fx-health"],
    queryFn: async () => (await api.get<FxHealth>("/v1/admin/settings/fx/health")).data,
    refetchInterval: 30_000,
  })

  if (!health || !health.has_errors || health.count === 0) {
    return null
  }

  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-xs text-amber-600 dark:text-amber-400">
      <div className="flex items-center gap-2 min-w-0">
        <AlertTriangle className="size-4 shrink-0 text-amber-500" />
        <span className="truncate">
          <strong>Внимание:</strong> Не удалось обновить курсы некоторых валют ({health.count}{" "}
          {health.count === 1 ? "источник с ошибкой" : "источников с ошибками"}). Используются резервные данные.
        </span>
      </div>
      <Link
        to="/settings/currency"
        className="flex shrink-0 items-center gap-1 font-medium text-primary hover:underline"
      >
        Настройки курсов <ArrowRight className="size-3.5" />
      </Link>
    </div>
  )
}
