import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import {
  Bug,
  Check,
  ChevronDown,
  ChevronRight,
  Copy,
  FileCode2,
  RefreshCw,
  Search,
  Server,
} from "lucide-react"

import { api } from "@/api/api.ts"
import { toastSuccess } from "@/lib/toast"
import { Badge } from "@/components/shadsnui/badge"
import { Button } from "@/components/shadsnui/button"
import { Input } from "@/components/shadsnui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/shadsnui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/shadsnui/table"

interface ErrorLogEntry {
  id: string
  ray_id: string
  timestamp: string
  client_ip: string
  user_id: number | null
  user_login: string | null
  method: string
  path: string
  status_code: number
  error_detail: string
  instance_id: string
}

function getStatusBadge(code: number) {
  if (code >= 500) {
    return <Badge variant="destructive" className="font-mono">{code}</Badge>
  }
  if (code === 404) {
    return <Badge variant="outline" className="font-mono text-muted-foreground border-dashed">{code}</Badge>
  }
  if (code === 401 || code === 403) {
    return <Badge variant="secondary" className="font-mono">{code}</Badge>
  }
  return <Badge variant="outline" className="font-mono">{code}</Badge>
}

export function SystemErrorLogs() {
  const [statusCodeFilter, setStatusCodeFilter] = useState<string>("all")
  const [search, setSearch] = useState("")
  const [limit, setLimit] = useState("100")
  const [copiedRayId, setCopiedRayId] = useState<string | null>(null)
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["system-error-logs", statusCodeFilter, limit, search],
    queryFn: async () => {
      const params = new URLSearchParams()
      params.set("limit", limit)
      if (statusCodeFilter !== "all") {
        params.set("status_code", statusCodeFilter)
      }
      if (search.trim()) {
        params.set("search", search.trim())
      }
      return (await api.get<ErrorLogEntry[]>(`/v1/system/errors?${params.toString()}`)).data
    },
    refetchInterval: 10000,
  })

  const copyRayId = (rayId: string) => {
    navigator.clipboard.writeText(rayId)
    setCopiedRayId(rayId)
    setTimeout(() => setCopiedRayId(null), 2000)
    toastSuccess("Ray ID скопирован")
  }

  const toggleExpand = (id: string) => {
    setExpandedId((prev) => (prev === id ? null : id))
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Bug className="size-5 text-destructive" />
            Журнал ошибок API (4xx / 5xx)
          </h2>
          <p className="text-sm text-muted-foreground">
            Фиксация сбоев и отклоненных запросов с привязкой к конкретному инстансу, IP-клиенту и
            сквозному идентификатору трассировки (Ray ID).
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
        </div>
      </div>

      {/* Панель фильтров */}
      <div className="flex flex-col sm:flex-row items-center gap-2">
        <div className="relative flex-1 w-full">
          <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
          <Input
            placeholder="Поиск по пути, IP, Ray ID, пользователю или деталям..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-8 h-9"
          />
        </div>

        <div className="w-full sm:w-44">
          <Select value={statusCodeFilter} onValueChange={(v) => v && setStatusCodeFilter(v)}>
            <SelectTrigger className="h-9">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Все статусы (4xx+5xx)</SelectItem>
              <SelectItem value="500">500 Server Error</SelectItem>
              <SelectItem value="404">404 Not Found</SelectItem>
              <SelectItem value="422">422 Validation Error</SelectItem>
              <SelectItem value="403">403 Forbidden</SelectItem>
              <SelectItem value="401">401 Unauthorized</SelectItem>
              <SelectItem value="429">429 Too Many Requests</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="w-full sm:w-32">
          <Select value={limit} onValueChange={(v) => v && setLimit(v)}>
            <SelectTrigger className="h-9">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="50">50 записей</SelectItem>
              <SelectItem value="100">100 записей</SelectItem>
              <SelectItem value="200">200 записей</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Таблица журнала ошибок */}
      <div className="rounded-lg border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-10" />
              <TableHead>Время (UTC/МСК)</TableHead>
              <TableHead>Статус</TableHead>
              <TableHead>Метод и путь</TableHead>
              <TableHead>Клиент (IP)</TableHead>
              <TableHead>Пользователь</TableHead>
              <TableHead>Инстанс</TableHead>
              <TableHead className="text-right">Ray ID</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={8} className="py-8 text-center text-sm text-muted-foreground">
                  Загрузка журнала ошибок…
                </TableCell>
              </TableRow>
            )}
            {data?.length === 0 && !isLoading && (
              <TableRow>
                <TableCell colSpan={8} className="py-8 text-center text-sm text-muted-foreground">
                  Ошибок с выбранными параметрами фильтрации не обнаружено.
                </TableCell>
              </TableRow>
            )}
            {data?.map((err) => {
              const isExpanded = expandedId === err.id

              return (
                <TableRow
                  key={err.id}
                  className="group cursor-pointer hover:bg-muted/50 transition-colors"
                  onClick={() => toggleExpand(err.id)}
                >
                  <TableCell className="p-2 text-center text-muted-foreground">
                    {isExpanded ? (
                      <ChevronDown className="size-4 inline" />
                    ) : (
                      <ChevronRight className="size-4 inline text-muted-foreground/60 group-hover:text-foreground" />
                    )}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                    {new Date(err.timestamp).toLocaleString("ru-RU")}
                  </TableCell>
                  <TableCell>
                    {getStatusBadge(err.status_code)}
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1.5">
                      <span className="font-mono text-xs font-semibold px-1 py-0.5 rounded bg-muted">
                        {err.method}
                      </span>
                      <code className="text-xs font-mono font-medium">{err.path}</code>
                    </div>
                  </TableCell>
                  <TableCell>
                    <span className="font-mono text-xs">{err.client_ip}</span>
                  </TableCell>
                  <TableCell>
                    {err.user_login ? (
                      <span className="text-xs font-medium">
                        {err.user_login} (id: {err.user_id})
                      </span>
                    ) : (
                      <span className="text-xs text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1 text-xs text-muted-foreground font-mono">
                      <Server className="size-3" />
                      <span>{err.instance_id}</span>
                    </div>
                  </TableCell>
                  <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                    <button
                      type="button"
                      onClick={() => copyRayId(err.ray_id)}
                      className="inline-flex items-center gap-1 font-mono text-[11px] bg-muted hover:bg-muted/80 px-1.5 py-0.5 rounded cursor-pointer transition-colors"
                      title="Нажмите для копирования Ray ID"
                    >
                      {err.ray_id}
                      {copiedRayId === err.ray_id ? (
                        <Check className="size-3 text-emerald-500" />
                      ) : (
                        <Copy className="size-3 text-muted-foreground" />
                      )}
                    </button>
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </div>

      {/* Детальный просмотр развернутой ошибки */}
      {expandedId && (
        (() => {
          const selected = data?.find((e) => e.id === expandedId)
          if (!selected) return null

          return (
            <div className="rounded-lg border bg-muted/30 p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <FileCode2 className="size-4 text-primary" />
                  <span className="font-semibold text-sm">Детали ошибки: {selected.ray_id}</span>
                  <Badge variant="outline" className="font-mono text-xs">
                    HTTP {selected.status_code}
                  </Badge>
                </div>
                <Button variant="ghost" size="sm" onClick={() => setExpandedId(null)}>
                  Закрыть
                </Button>
              </div>

              <div className="space-y-1.5">
                <div className="text-xs text-muted-foreground">Тело / сообщение ошибки:</div>
                <pre className="p-3 rounded bg-zinc-950 text-zinc-100 dark:bg-zinc-900 font-mono text-xs overflow-x-auto whitespace-pre-wrap max-h-60 overflow-y-auto">
                  {selected.error_detail}
                </pre>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs pt-1 text-muted-foreground border-t">
                <div>
                  <span className="font-medium text-foreground">Инстанс: </span>
                  {selected.instance_id}
                </div>
                <div>
                  <span className="font-medium text-foreground">Клиент IP: </span>
                  {selected.client_ip}
                </div>
                <div>
                  <span className="font-medium text-foreground">Метод: </span>
                  {selected.method}
                </div>
                <div>
                  <span className="font-medium text-foreground">Путь: </span>
                  {selected.path}
                </div>
              </div>
            </div>
          )
        })()
      )}
    </div>
  )
}
