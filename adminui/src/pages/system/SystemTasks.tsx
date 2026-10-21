import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Activity, AlertCircle, Clock, Copy, FileText, Search } from "lucide-react"

import { api } from "@/api/api.ts"
import { Badge } from "@/components/shadsnui/badge"
import { Button } from "@/components/shadsnui/button"
import { Input } from "@/components/shadsnui/input"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/shadsnui/tabs"
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
import { toastSuccess } from "@/lib/toast"

interface TaskLogEntry {
  kind: string
  op: string
  token_or_cid: string
  state: string
  detail: string | null
  owner_id: number | null
  ts: number
}

interface ArchivedTaskListItem {
  id: number
  task_id: string
  kind: string
  operation: string
  status: string
  created_at: string
  started_at: string | null
  finished_at: string | null
  duration_ms: number | null
  initiator_type: string | null
  initiator_id: string | null
  error_message: string | null
}

interface ArchivedTaskDetail extends ArchivedTaskListItem {
  logs: unknown[] | null
  meta: Record<string, unknown> | null
}

interface ArchivedTaskPage {
  items: ArchivedTaskListItem[]
  total: number
  page: number
  page_size: number
}

const STATE_VARIANT: Record<string, "outline" | "secondary" | "destructive" | "default"> = {
  ready: "outline",
  processing: "secondary",
  queued: "secondary",
  running: "secondary",
  success: "default",
  failed: "destructive",
  error: "destructive",
  timeout: "destructive",
}

function TaskDetailDialog({
  taskId,
  open,
  onOpenChange,
}: {
  taskId: string | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { data: task, isLoading } = useQuery({
    queryKey: ["admin-task-detail", taskId],
    queryFn: async () => (await api.get<ArchivedTaskDetail>(`/v1/admin/tasks/archive/${taskId}`)).data,
    enabled: !!taskId && open,
  })

  const copyLogs = () => {
    if (!task?.logs) return
    const text = typeof task.logs === "string" ? task.logs : JSON.stringify(task.logs, null, 2)
    void navigator.clipboard.writeText(text)
    toastSuccess("Логи скопированы в буфер обмена")
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] max-w-3xl overflow-y-auto">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <DialogTitle className="font-mono text-base">Задача {taskId}</DialogTitle>
            {task && (
              <Badge variant={STATE_VARIANT[task.status] ?? "outline"}>{task.status}</Badge>
            )}
          </div>
          <DialogDescription>
            {task ? `${task.kind} · операция: ${task.operation}` : "Загрузка информации…"}
          </DialogDescription>
        </DialogHeader>

        {isLoading && <p className="py-8 text-center text-sm text-muted-foreground">Загрузка…</p>}

        {task && (
          <div className="space-y-4 text-sm">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 rounded-lg bg-muted/40 p-3">
              <div>
                <p className="text-xs text-muted-foreground">Тип</p>
                <p className="font-medium">{task.kind}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Операция</p>
                <p className="font-medium">{task.operation}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Длительность</p>
                <p className="font-medium">
                  {task.duration_ms != null ? `${task.duration_ms} мс` : "—"}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Инициатор</p>
                <p className="font-mono text-xs">{task.initiator_type ? `${task.initiator_type}:${task.initiator_id}` : "system"}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Создана</p>
                <p className="text-xs">{new Date(task.created_at).toLocaleString()}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Запуск</p>
                <p className="text-xs">{task.started_at ? new Date(task.started_at).toLocaleString() : "—"}</p>
              </div>
              <div className="col-span-2">
                <p className="text-xs text-muted-foreground">Завершена</p>
                <p className="text-xs">{task.finished_at ? new Date(task.finished_at).toLocaleString() : "—"}</p>
              </div>
            </div>

            {task.error_message && (
              <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-3 text-destructive">
                <div className="flex items-center gap-1.5 font-medium">
                  <AlertCircle className="size-4 shrink-0" />
                  <span>Ошибка выполнения</span>
                </div>
                <pre className="mt-1 max-h-36 overflow-auto font-mono text-xs whitespace-pre-wrap">
                  {task.error_message}
                </pre>
              </div>
            )}

            <div>
              <div className="mb-1 flex items-center justify-between">
                <p className="font-medium flex items-center gap-1.5">
                  <FileText className="size-4" /> Журнал логов
                </p>
                {task.logs && task.logs.length > 0 && (
                  <Button variant="ghost" size="xs" onClick={copyLogs}>
                    <Copy className="size-3 mr-1" /> Копировать
                  </Button>
                )}
              </div>
              <div className="max-h-64 overflow-auto rounded-lg bg-neutral-950 p-3 font-mono text-xs text-neutral-200">
                {!task.logs || task.logs.length === 0 ? (
                  <span className="text-neutral-500">Логов нет</span>
                ) : Array.isArray(task.logs) ? (
                  task.logs.map((line, idx) => (
                    <div key={idx} className="leading-relaxed">
                      {typeof line === "object" ? JSON.stringify(line) : String(line)}
                    </div>
                  ))
                ) : (
                  <pre>{String(task.logs)}</pre>
                )}
              </div>
            </div>

            {task.meta && Object.keys(task.meta).length > 0 && (
              <div>
                <p className="mb-1 font-medium">Метаданные</p>
                <pre className="max-h-36 overflow-auto rounded-lg bg-muted p-2 font-mono text-xs">
                  {JSON.stringify(task.meta, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

function LiveTasksTab() {
  const [service, setService] = useState<"media" | "lua">("media")

  const { data, isLoading } = useQuery({
    queryKey: ["system-tasks-live", service],
    queryFn: async () =>
      (await api.get<TaskLogEntry[]>(`/v1/admin/tasks/${service}`, { params: { limit: 100 } })).data,
    refetchInterval: 4000,
  })

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <div>
          <h3 className="text-sm font-medium">Оперативный буфер событий (Valkey)</h3>
          <p className="text-xs text-muted-foreground">
            Свежие события последних задач без нагрузки на PostgreSQL.
          </p>
        </div>
        <Select value={service} onValueChange={(v) => setService(v as "media" | "lua")}>
          <SelectTrigger size="sm" className="w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="media">Mediaworker</SelectItem>
            <SelectItem value="lua">Lua</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Время</TableHead>
              <TableHead>Операция</TableHead>
              <TableHead>Токен/CID</TableHead>
              <TableHead>Статус</TableHead>
              <TableHead>Владелец</TableHead>
              <TableHead>Детали</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={6} className="py-8 text-center text-sm text-muted-foreground">
                  Загрузка…
                </TableCell>
              </TableRow>
            )}
            {!isLoading && (data?.length ?? 0) === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="py-8 text-center text-sm text-muted-foreground">
                  Нет активных задач в буфере.
                </TableCell>
              </TableRow>
            )}
            {data?.map((e, i) => (
              <TableRow key={i}>
                <TableCell>{new Date(e.ts * 1000).toLocaleTimeString()}</TableCell>
                <TableCell className="font-medium">{e.op}</TableCell>
                <TableCell className="max-w-[160px] truncate font-mono text-xs">{e.token_or_cid}</TableCell>
                <TableCell>
                  <Badge variant={STATE_VARIANT[e.state] ?? "outline"}>{e.state}</Badge>
                </TableCell>
                <TableCell>{e.owner_id ?? "—"}</TableCell>
                <TableCell className="max-w-xs truncate text-muted-foreground">{e.detail ?? "—"}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}

function ArchivedTasksTab() {
  const [kind, setKind] = useState<string>("all")
  const [statusFilter, setStatusFilter] = useState<string>("all")
  const [search, setSearch] = useState("")
  const [page, setPage] = useState(1)
  const [detailTaskId, setDetailTaskId] = useState<string | null>(null)
  const pageSize = 25

  const { data, isLoading } = useQuery({
    queryKey: ["admin-tasks-archive", kind, statusFilter, search, page],
    queryFn: async () =>
      (
        await api.get<ArchivedTaskPage>("/v1/admin/tasks/archive", {
          params: {
            kind: kind === "all" ? undefined : kind,
            status: statusFilter === "all" ? undefined : statusFilter,
            search: search.trim() || undefined,
            page,
            page_size: pageSize,
          },
        })
      ).data,
  })

  const totalPages = Math.ceil((data?.total ?? 0) / pageSize) || 1

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-medium">Постоянная история задач (PostgreSQL)</h3>
          <p className="text-xs text-muted-foreground">
            Полный архив фоновых задач с фильтрацией, трассировкой ошибок и логами.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="relative w-44">
            <Search className="absolute left-2.5 top-2.5 size-3.5 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => {
                setSearch(e.target.value)
                setPage(1)
              }}
              placeholder="Поиск ID задачи…"
              className="h-8 pl-8 text-xs"
            />
          </div>

          <Select
            value={kind}
            onValueChange={(v) => {
              setKind(v ?? "all")
              setPage(1)
            }}
          >
            <SelectTrigger size="sm" className="w-32">
              <SelectValue placeholder="Тип" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Все типы</SelectItem>
              <SelectItem value="media">Media</SelectItem>
              <SelectItem value="lua">Lua</SelectItem>
              <SelectItem value="billing">Billing</SelectItem>
            </SelectContent>
          </Select>

          <Select
            value={statusFilter}
            onValueChange={(v) => {
              setStatusFilter(v ?? "all")
              setPage(1)
            }}
          >
            <SelectTrigger size="sm" className="w-32">
              <SelectValue placeholder="Статус" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Все статусы</SelectItem>
              <SelectItem value="success">Success</SelectItem>
              <SelectItem value="failed">Failed</SelectItem>
              <SelectItem value="running">Running</SelectItem>
              <SelectItem value="timeout">Timeout</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Время</TableHead>
              <TableHead>Тип</TableHead>
              <TableHead>Операция</TableHead>
              <TableHead>Task ID</TableHead>
              <TableHead>Статус</TableHead>
              <TableHead>Длительность</TableHead>
              <TableHead className="text-right">Детали</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={7} className="py-8 text-center text-sm text-muted-foreground">
                  Загрузка архива…
                </TableCell>
              </TableRow>
            )}
            {!isLoading && (data?.items?.length ?? 0) === 0 && (
              <TableRow>
                <TableCell colSpan={7} className="py-8 text-center text-sm text-muted-foreground">
                  Архивных задач по выбранным фильтрам не найдено.
                </TableCell>
              </TableRow>
            )}
            {data?.items?.map((item) => (
              <TableRow
                key={item.id}
                className="cursor-pointer hover:bg-muted/50"
                onClick={() => setDetailTaskId(item.task_id)}
              >
                <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                  {new Date(item.created_at).toLocaleString()}
                </TableCell>
                <TableCell>
                  <Badge variant="outline">{item.kind}</Badge>
                </TableCell>
                <TableCell className="font-medium">{item.operation}</TableCell>
                <TableCell className="max-w-[140px] truncate font-mono text-xs text-muted-foreground">
                  {item.task_id}
                </TableCell>
                <TableCell>
                  <Badge variant={STATE_VARIANT[item.status] ?? "outline"}>{item.status}</Badge>
                </TableCell>
                <TableCell className="text-xs tabular-nums">
                  {item.duration_ms != null ? `${item.duration_ms} мс` : "—"}
                </TableCell>
                <TableCell className="text-right">
                  <Button
                    variant="ghost"
                    size="xs"
                    onClick={(e) => {
                      e.stopPropagation()
                      setDetailTaskId(item.task_id)
                    }}
                  >
                    Логи
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>Всего задач: {data?.total ?? 0}</span>
          <div className="flex items-center gap-1">
            <Button
              variant="outline"
              size="xs"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              Назад
            </Button>
            <span className="px-2">
              {page} / {totalPages}
            </span>
            <Button
              variant="outline"
              size="xs"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              Вперёд
            </Button>
          </div>
        </div>
      )}

      <TaskDetailDialog
        taskId={detailTaskId}
        open={!!detailTaskId}
        onOpenChange={(open) => !open && setDetailTaskId(null)}
      />
    </div>
  )
}

export function SystemTasks() {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Мониторинг задач</h2>
        <p className="text-sm text-muted-foreground">
          Оперативный стрим текущих событий и постоянный архив задач.
        </p>
      </div>

      <Tabs defaultValue="live" className="space-y-4">
        <TabsList>
          <TabsTrigger value="live" className="gap-1.5">
            <Activity className="size-3.5" /> Оперативный стрим (Live)
          </TabsTrigger>
          <TabsTrigger value="archive" className="gap-1.5">
            <Clock className="size-3.5" /> Архив задач (PostgreSQL)
          </TabsTrigger>
        </TabsList>
        <TabsContent value="live">
          <LiveTasksTab />
        </TabsContent>
        <TabsContent value="archive">
          <ArchivedTasksTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}
