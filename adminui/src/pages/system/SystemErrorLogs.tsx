import React, { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import {
  Bug,
  Check,
  ChevronDown,
  ChevronRight,
  Clock,
  Copy,
  ExternalLink,
  FileCode2,
  Globe,
  RefreshCw,
  Search,
  Server,
  User,
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/shadsnui/dialog"

interface ErrorLogEntry {
  id: string
  trace_id: string
  ray_id?: string
  timestamp: string
  client_ip: string
  user_id: number | null
  user_login: string | null
  user_role?: string | null
  method: string
  path: string
  query_params?: string
  status_code: number
  duration_ms?: number
  user_agent?: string
  referer?: string
  exception_type?: string
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
  const [copiedTraceId, setCopiedTraceId] = useState<string | null>(null)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [modalEntry, setModalEntry] = useState<ErrorLogEntry | null>(null)

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

  const copyTraceId = (traceId: string) => {
    navigator.clipboard.writeText(traceId)
    setCopiedTraceId(traceId)
    setTimeout(() => setCopiedTraceId(null), 2000)
    toastSuccess("Trace ID скопирован")
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
            Фиксация сбоев и отклоненных запросов с привязкой к инстансу, задержке, IP-клиенту и
            сквозному Trace ID.
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
            placeholder="Поиск по пути, IP, Trace ID, пользователю или деталям..."
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
      <div className="rounded-lg border bg-card overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-10" />
              <TableHead>Время (UTC/МСК)</TableHead>
              <TableHead>Статус</TableHead>
              <TableHead>Метод и путь</TableHead>
              <TableHead>Клиент (IP)</TableHead>
              <TableHead>Пользователь</TableHead>
              <TableHead>Задержка</TableHead>
              <TableHead className="text-right">Trace ID</TableHead>
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
              const tid = err.trace_id || err.ray_id || ""

              return (
                <React.Fragment key={err.id}>
                  {/* Основная строка ошибки */}
                  <TableRow
                    className={`cursor-pointer transition-colors ${
                      isExpanded ? "bg-muted/40 font-medium" : "hover:bg-muted/50"
                    }`}
                    onClick={() => toggleExpand(err.id)}
                  >
                    <TableCell className="p-2 text-center text-muted-foreground">
                      {isExpanded ? (
                        <ChevronDown className="size-4 inline text-primary transition-transform" />
                      ) : (
                        <ChevronRight className="size-4 inline text-muted-foreground/60 transition-transform" />
                      )}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground whitespace-nowrap font-mono">
                      {new Date(err.timestamp).toLocaleString("ru-RU")}
                    </TableCell>
                    <TableCell>{getStatusBadge(err.status_code)}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="font-mono text-xs font-semibold px-1 py-0.5 rounded bg-muted">
                          {err.method}
                        </span>
                        <code className="text-xs font-mono font-medium text-foreground">{err.path}</code>
                        {err.query_params && (
                          <span className="text-[11px] text-muted-foreground font-mono truncate max-w-[150px]">
                            ?{err.query_params}
                          </span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      <span className="font-mono text-xs">{err.client_ip}</span>
                    </TableCell>
                    <TableCell>
                      {err.user_login ? (
                        <span className="text-xs font-medium">
                          {err.user_login}
                          {err.user_role && (
                            <Badge variant="outline" className="ml-1 text-[10px] py-0 px-1">
                              {err.user_role}
                            </Badge>
                          )}
                        </span>
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell>
                      {err.duration_ms !== undefined && err.duration_ms > 0 ? (
                        <span
                          className={`text-xs font-mono ${
                            err.duration_ms > 1000
                              ? "text-red-500 font-semibold"
                              : err.duration_ms > 300
                              ? "text-amber-500"
                              : "text-muted-foreground"
                          }`}
                        >
                          {err.duration_ms} мс
                        </span>
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                      {tid ? (
                        <button
                          type="button"
                          onClick={() => copyTraceId(tid)}
                          className="inline-flex items-center gap-1 font-mono text-[11px] bg-muted hover:bg-muted/80 px-1.5 py-0.5 rounded cursor-pointer transition-colors max-w-[130px] truncate"
                          title={`Нажмите для копирования Trace ID: ${tid}`}
                        >
                          <span className="truncate">{tid.slice(0, 8)}…{tid.slice(-6)}</span>
                          {copiedTraceId === tid ? (
                            <Check className="size-3 text-emerald-500 shrink-0" />
                          ) : (
                            <Copy className="size-3 text-muted-foreground shrink-0" />
                          )}
                        </button>
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </TableCell>
                  </TableRow>

                  {/* Вложенная строка деталей, раскрывающаяся ПРЯМО ПОД СТРОКОЙ */}
                  {isExpanded && (
                    <TableRow className="bg-muted/20 hover:bg-muted/20 border-b border-border">
                      <TableCell colSpan={8} className="p-0">
                        <div className="p-4 space-y-3 bg-muted/10 border-l-4 border-l-primary">
                          <div className="flex items-center justify-between flex-wrap gap-2">
                            <div className="flex items-center gap-2">
                              <FileCode2 className="size-4 text-primary" />
                              <span className="font-semibold text-sm">
                                Детали инцидента: <code className="font-mono text-xs">{tid}</code>
                              </span>
                              {err.exception_type && (
                                <Badge variant="destructive" className="font-mono text-xs">
                                  {err.exception_type}
                                </Badge>
                              )}
                            </div>
                            <div className="flex items-center gap-2">
                              <Button
                                variant="outline"
                                size="sm"
                                className="h-7 text-xs"
                                onClick={() => setModalEntry(err)}
                              >
                                <ExternalLink className="size-3 mr-1" />
                                Открыть в окне
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                className="h-7 text-xs"
                                onClick={() => setExpandedId(null)}
                              >
                                Свернуть
                              </Button>
                            </div>
                          </div>

                          {/* Сетка расширенных параметров запроса */}
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 p-3 rounded-lg bg-card text-xs border">
                            <div className="space-y-0.5">
                              <div className="text-muted-foreground flex items-center gap-1">
                                <Server className="size-3 text-blue-500" />
                                Инстанс / Контейнер:
                              </div>
                              <div className="font-mono font-medium">{err.instance_id}</div>
                            </div>

                            <div className="space-y-0.5">
                              <div className="text-muted-foreground flex items-center gap-1">
                                <Clock className="size-3 text-emerald-500" />
                                Длительность (Latency):
                              </div>
                              <div className="font-mono font-medium">
                                {err.duration_ms ? `${err.duration_ms} мс` : "Мгновенно (<1мс)"}
                              </div>
                            </div>

                            <div className="space-y-0.5">
                              <div className="text-muted-foreground flex items-center gap-1">
                                <Globe className="size-3 text-purple-500" />
                                IP клиента:
                              </div>
                              <div className="font-mono font-medium">{err.client_ip}</div>
                            </div>

                            <div className="space-y-0.5">
                              <div className="text-muted-foreground flex items-center gap-1">
                                <User className="size-3 text-amber-500" />
                                Пользователь:
                              </div>
                              <div className="font-medium">
                                {err.user_login ? `${err.user_login} (id: ${err.user_id})` : "Анонимный клиент"}
                              </div>
                            </div>

                            {err.query_params && (
                              <div className="col-span-2 space-y-0.5">
                                <div className="text-muted-foreground">Query параметры:</div>
                                <code className="font-mono text-[11px] block bg-muted p-1 rounded break-all">
                                  {err.query_params}
                                </code>
                              </div>
                            )}

                            {err.referer && (
                              <div className="col-span-2 space-y-0.5">
                                <div className="text-muted-foreground">Referer (Источник):</div>
                                <div className="font-mono text-[11px] truncate">{err.referer}</div>
                              </div>
                            )}

                            {err.user_agent && (
                              <div className="col-span-full space-y-0.5">
                                <div className="text-muted-foreground">User-Agent:</div>
                                <div className="font-mono text-[11px] text-muted-foreground break-all">
                                  {err.user_agent}
                                </div>
                              </div>
                            )}
                          </div>

                          {/* Тело ошибки / Сообщение */}
                          <div className="space-y-1">
                            <div className="text-xs text-muted-foreground font-medium">
                              Тело ответа / сообщение ошибки:
                            </div>
                            <pre className="p-3 rounded-lg bg-zinc-950 text-zinc-100 dark:bg-zinc-900 font-mono text-xs overflow-x-auto whitespace-pre-wrap max-h-56 overflow-y-auto">
                              {err.error_detail}
                            </pre>
                          </div>
                        </div>
                      </TableCell>
                    </TableRow>
                  )}
                </React.Fragment>
              )
            })}
          </TableBody>
        </Table>
      </div>

      {/* Модальное диалоговое окно для детального разбора ошибки */}
      <Dialog open={!!modalEntry} onOpenChange={(open) => !open && setModalEntry(null)}>
        {modalEntry && (
          <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
            <DialogHeader>
              <div className="flex items-center gap-2">
                <Bug className="size-5 text-destructive" />
                <DialogTitle>Ошибка API: HTTP {modalEntry.status_code}</DialogTitle>
                {modalEntry.exception_type && (
                  <Badge variant="destructive">{modalEntry.exception_type}</Badge>
                )}
              </div>
              <DialogDescription className="font-mono text-xs">
                Trace ID: {modalEntry.trace_id || modalEntry.ray_id}
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4 py-2 text-xs">
              {/* Сводка параметров */}
              <div className="grid grid-cols-2 gap-2 p-3 rounded-lg border bg-muted/40">
                <div>
                  <span className="text-muted-foreground">Метод и путь: </span>
                  <span className="font-mono font-semibold">{modalEntry.method} {modalEntry.path}</span>
                </div>
                <div>
                  <span className="text-muted-foreground">Время: </span>
                  <span className="font-mono">{new Date(modalEntry.timestamp).toLocaleString("ru-RU")}</span>
                </div>
                <div>
                  <span className="text-muted-foreground">Инстанс: </span>
                  <span className="font-mono">{modalEntry.instance_id}</span>
                </div>
                <div>
                  <span className="text-muted-foreground">Задержка: </span>
                  <span className="font-mono">{modalEntry.duration_ms ?? 0} мс</span>
                </div>
                <div>
                  <span className="text-muted-foreground">IP-клиент: </span>
                  <span className="font-mono">{modalEntry.client_ip}</span>
                </div>
                <div>
                  <span className="text-muted-foreground">Пользователь: </span>
                  <span>{modalEntry.user_login ? `${modalEntry.user_login} (${modalEntry.user_role || "user"})` : "Не авторизован"}</span>
                </div>
                {modalEntry.query_params && (
                  <div className="col-span-2">
                    <span className="text-muted-foreground">Query: </span>
                    <code className="font-mono break-all">{modalEntry.query_params}</code>
                  </div>
                )}
                {modalEntry.user_agent && (
                  <div className="col-span-2">
                    <span className="text-muted-foreground">User-Agent: </span>
                    <span className="font-mono text-[11px] break-all">{modalEntry.user_agent}</span>
                  </div>
                )}
              </div>

              {/* Тело ошибки */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-muted-foreground font-medium">
                  <span>Текст ошибки / стек вызовов:</span>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 text-[11px]"
                    onClick={() => {
                      navigator.clipboard.writeText(modalEntry.error_detail)
                      toastSuccess("Тело ошибки скопировано")
                    }}
                  >
                    <Copy className="size-3 mr-1" />
                    Скопировать
                  </Button>
                </div>
                <pre className="p-3 rounded-lg bg-zinc-950 text-zinc-100 dark:bg-zinc-900 font-mono text-xs overflow-x-auto whitespace-pre-wrap max-h-72 overflow-y-auto">
                  {modalEntry.error_detail}
                </pre>
              </div>
            </div>
          </DialogContent>
        )}
      </Dialog>
    </div>
  )
}
