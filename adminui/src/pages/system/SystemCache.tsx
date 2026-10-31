import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  Activity,
  CheckCircle2,
  Database,
  HardDrive,
  Layers,
  RefreshCw,
  RotateCcw,
  Trash2,
  Zap,
} from "lucide-react"

import { api } from "@/api/api.ts"
import { useAuth } from "@/hooks/use-auth"
import { toastError, toastSuccess } from "@/lib/toast"
import { Badge } from "@/components/shadsnui/badge"
import { Button } from "@/components/shadsnui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/shadsnui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/shadsnui/table"

interface CacheNamespace {
  prefix: string
  label: string
  keys_count: number
}

interface CacheStats {
  hits: number
  misses: number
  hit_rate: number
  invalidations: number
  used_memory_bytes: number
  used_memory_human: string
  peak_memory_bytes: number
  peak_memory_human: string
  total_keys: number
  valkey_version: string
  uptime_seconds: number
  namespaces: CacheNamespace[]
}

interface FlushResponse {
  ok: boolean
  mode: string
  cleared_keys: number
  message?: string
  error?: string
}

export function SystemCache() {
  const { can } = useAuth()
  const qc = useQueryClient()
  const canManage = can("system.cache.manage") || can("system.cache.edit") || can("system")

  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["system-cache-stats"],
    queryFn: async () => (await api.get<CacheStats>("/v1/system/cache")).data,
    refetchInterval: 10000,
  })

  const flush = useMutation({
    mutationFn: async (mode: "catalog" | "all_cache" | "reset_stats") => {
      const res = await api.post<FlushResponse>("/v1/system/cache/flush", { mode })
      return res.data
    },
    onSuccess: (res) => {
      void qc.invalidateQueries({ queryKey: ["system-cache-stats"] })
      if (res.ok) {
        toastSuccess(res.message || "Операция успешно выполнена")
      } else {
        toastError(res.error || "Ошибка при очистке кэша")
      }
    },
    onError: () => toastError("Не удалось выполнить очистку кэша"),
  })

  const uptimeDays = data ? Math.floor(data.uptime_seconds / 86400) : 0
  const uptimeHours = data ? Math.floor((data.uptime_seconds % 86400) / 3600) : 0
  const uptimeMins = data ? Math.floor((data.uptime_seconds % 3600) / 60) : 0

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Database className="size-5 text-primary" />
            Кэширование и память Valkey
          </h2>
          <p className="text-sm text-muted-foreground">
            Метрики попадания в кэш (Hit Rate), распределение ключей по пространствам имён и
            управление сбросом кэша.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => refetch()}
            disabled={isFetching}
          >
            <RefreshCw className={`size-3.5 mr-1 ${isFetching ? "animate-spin" : ""}`} />
            Обновить
          </Button>

          {canManage && (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={() => flush.mutate("catalog")}
                disabled={flush.isPending}
              >
                <Layers className="size-3.5 mr-1" />
                Сбросить кэш каталога
              </Button>

              <Button
                variant="outline"
                size="sm"
                onClick={() => flush.mutate("reset_stats")}
                disabled={flush.isPending}
              >
                <RotateCcw className="size-3.5 mr-1" />
                Сбросить счётчики
              </Button>

              <Button
                variant="destructive"
                size="sm"
                onClick={() => {
                  if (confirm("Вы уверены, что хотите полностью очистить весь кэш Valkey?")) {
                    flush.mutate("all_cache")
                  }
                }}
                disabled={flush.isPending}
              >
                <Trash2 className="size-3.5 mr-1" />
                Очистить весь кэш
              </Button>
            </>
          )}
        </div>
      </div>

      {/* Метрики в карточках */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center justify-between text-xs font-medium">
              <span>Hit Rate (Попадания)</span>
              <Zap className="size-4 text-amber-500" />
            </CardDescription>
            <CardTitle className="text-2xl font-bold">
              {isLoading ? "…" : `${data?.hit_rate ?? 0}%`}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>Hits: {data?.hits ?? 0}</span>
              <span>Misses: {data?.misses ?? 0}</span>
            </div>
            <div className="mt-2 h-1.5 w-full bg-secondary rounded-full overflow-hidden">
              <div
                className="h-full bg-emerald-500 rounded-full transition-all duration-500"
                style={{ width: `${Math.min(100, Math.max(0, data?.hit_rate ?? 0))}%` }}
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center justify-between text-xs font-medium">
              <span>Память Valkey</span>
              <HardDrive className="size-4 text-blue-500" />
            </CardDescription>
            <CardTitle className="text-2xl font-bold">
              {isLoading ? "…" : data?.used_memory_human}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-xs text-muted-foreground">
              Пиковое потребление: {data?.peak_memory_human}
            </div>
            <div className="text-xs text-muted-foreground mt-1">
              Версия: <span className="font-mono">{data?.valkey_version}</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center justify-between text-xs font-medium">
              <span>Всего ключей в DB</span>
              <Database className="size-4 text-purple-500" />
            </CardDescription>
            <CardTitle className="text-2xl font-bold">
              {isLoading ? "…" : data?.total_keys ?? 0}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-xs text-muted-foreground">
              Инвалидаций каталога: {data?.invalidations ?? 0}
            </div>
            <div className="text-xs text-emerald-600 dark:text-emerald-400 mt-1 flex items-center gap-1">
              <CheckCircle2 className="size-3" />
              <span>Хранилище активно</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center justify-between text-xs font-medium">
              <span>Время работы (Uptime)</span>
              <Activity className="size-4 text-emerald-500" />
            </CardDescription>
            <CardTitle className="text-2xl font-bold">
              {isLoading ? "…" : uptimeDays > 0 ? `${uptimeDays}д ${uptimeHours}ч` : `${uptimeHours}ч ${uptimeMins}м`}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-xs text-muted-foreground">
              Всего секунд: {data?.uptime_seconds?.toLocaleString() ?? 0}
            </div>
            <div className="text-xs text-muted-foreground mt-1">
              Кластерный статус: Single Master
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Таблица пространств имён */}
      <div className="space-y-2">
        <h3 className="text-base font-semibold">Ключи по пространствам имён</h3>
        <div className="rounded-lg border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Префикс ключа</TableHead>
                <TableHead>Назначение данных</TableHead>
                <TableHead className="w-36 text-right">Количество ключей</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading && (
                <TableRow>
                  <TableCell colSpan={3} className="py-8 text-center text-sm text-muted-foreground">
                    Сканирование пространств имён…
                  </TableCell>
                </TableRow>
              )}
              {data?.namespaces.map((ns) => (
                <TableRow key={ns.prefix}>
                  <TableCell>
                    <code className="text-xs font-mono font-medium bg-muted px-1.5 py-0.5 rounded">
                      {ns.prefix}*
                    </code>
                  </TableCell>
                  <TableCell className="text-sm font-medium">{ns.label}</TableCell>
                  <TableCell className="text-right">
                    <Badge variant={ns.keys_count > 0 ? "secondary" : "outline"}>
                      {ns.keys_count}
                    </Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>
    </div>
  )
}
