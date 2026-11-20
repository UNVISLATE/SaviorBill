import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { ChevronDown, ChevronRight, XCircle, Terminal, Activity } from "lucide-react"

import { api } from "@/api/api.ts"
import { getErrorDetail } from "@/lib/api-error.ts"
import { toastError, toastSuccess } from "@/lib/toast"
import { Badge } from "@/components/shadsnui/badge"
import { Button } from "@/components/shadsnui/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/shadsnui/table"

interface Subprocess {
  pid: number
  name: string
  cmdline: string
  cpu_percent: number
  rss_mb: number
  started_at: number
  running_sec: number
}

interface CurrentJob {
  token: string
  op: string
  started_at: number
}

interface Instance {
  service: string
  consumer: string
  online: boolean
  uptime_sec: number
  cpu_percent: number
  rss_mb: number
  last_seen_at: number
  subprocesses?: Subprocess[]
  current_job?: CurrentJob | null
}

interface StatsResponse {
  instances: Instance[]
}

const SERVICE_LABEL: Record<string, string> = {
  billing: "Billing",
  media: "Mediaworker",
  lua: "Lua",
}

function fmtUptime(sec: number): string {
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  if (h > 0) return `${h}ч ${m}м`
  return `${m}м`
}

function fmtDuration(sec: number): string {
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  if (m > 0) return `${m}м ${s}с`
  return `${s}с`
}

export function SystemInstances() {
  const qc = useQueryClient()
  const [expanded, setExpanded] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ["system-stats"],
    queryFn: async () => (await api.get<StatsResponse>("/v1/system/stats")).data,
    refetchInterval: 4000,
  })

  const cancelMutation = useMutation({
    mutationFn: async ({ pid, token }: { pid?: number; token?: string }) => {
      return api.post("/v1/system/instances/media/cancel", { pid, token })
    },
    onSuccess: () => {
      toastSuccess("Сигнал отмены отправлен")
      void qc.invalidateQueries({ queryKey: ["system-stats"] })
    },
    onError: (e: unknown) => {
      toastError("Ошибка при отправке сигнала отмены", getErrorDetail(e))
    },
  })

  const toggleExpand = (id: string) => {
    setExpanded((curr) => (curr === id ? null : id))
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Инстансы</h2>
        <p className="text-sm text-muted-foreground">
          Живые процессы billing/media/lua по heartbeat в Valkey. Нажмите на строку Mediaworker для просмотра подпроцессов FFmpeg.
        </p>
      </div>
      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[30px]"></TableHead>
              <TableHead>Сервис</TableHead>
              <TableHead>Инстанс</TableHead>
              <TableHead>Статус</TableHead>
              <TableHead>Uptime</TableHead>
              <TableHead>CPU</TableHead>
              <TableHead>RSS</TableHead>
              <TableHead className="w-[120px]">Подпроцессы</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={8} className="py-8 text-center text-sm text-muted-foreground">
                  Загрузка…
                </TableCell>
              </TableRow>
            )}
            {!isLoading && (data?.instances.length ?? 0) === 0 && (
              <TableRow>
                <TableCell colSpan={8} className="py-8 text-center text-sm text-muted-foreground">
                  Нет живых инстансов.
                </TableCell>
              </TableRow>
            )}
            {data?.instances.map((i) => {
              const id = `${i.service}:${i.consumer}`
              const isExp = expanded === id
              const subCount = i.subprocesses?.length ?? 0
              const isMedia = i.service === "media"

              return (
                <div key={id} className="contents">
                  <TableRow
                    className="cursor-pointer hover:bg-muted/50 transition-colors"
                    onClick={() => toggleExpand(id)}
                  >
                    <TableCell className="w-[30px] px-2 text-muted-foreground">
                      {isExp ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
                    </TableCell>
                    <TableCell className="font-medium">
                      <div className="flex items-center gap-1.5">
                        {SERVICE_LABEL[i.service] ?? i.service}
                        {i.current_job && (
                          <span className="flex size-2 rounded-full bg-amber-500 animate-pulse" title="В процессе обработки" />
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="font-mono text-xs">{i.consumer}</TableCell>
                    <TableCell>
                      <Badge variant={i.online ? "outline" : "destructive"}>
                        {i.online ? "online" : "offline"}
                      </Badge>
                    </TableCell>
                    <TableCell>{fmtUptime(i.uptime_sec)}</TableCell>
                    <TableCell>{i.cpu_percent.toFixed(1)}%</TableCell>
                    <TableCell>{Math.round(i.rss_mb)} МБ</TableCell>
                    <TableCell>
                      {subCount > 0 ? (
                        <Badge variant="secondary" className="font-mono text-xs gap-1">
                          <Activity className="size-3 text-amber-500" /> {subCount}
                        </Badge>
                      ) : isMedia ? (
                        <span className="text-xs text-muted-foreground">0</span>
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </TableCell>
                  </TableRow>

                  {isExp && (
                    <TableRow className="bg-muted/30 hover:bg-muted/30">
                      <TableCell colSpan={8} className="p-4 border-t">
                        <div className="space-y-4">
                          {i.current_job && (
                            <div className="flex flex-wrap items-center justify-between gap-2 p-3 bg-background rounded-md border text-xs">
                              <div className="space-y-0.5">
                                <div className="font-semibold text-foreground flex items-center gap-2">
                                  <span>Активная задача: {i.current_job.op}</span>
                                  <Badge variant="outline" className="font-mono text-[10px]">
                                    {i.current_job.token}
                                  </Badge>
                                </div>
                                <div className="text-muted-foreground">
                                  В работе: {fmtDuration(Math.max(0, Date.now() / 1000 - i.current_job.started_at))}
                                </div>
                              </div>
                              <Button
                                size="sm"
                                variant="destructive"
                                disabled={cancelMutation.isPending}
                                onClick={(e) => {
                                  e.stopPropagation()
                                  cancelMutation.mutate({ token: i.current_job?.token })
                                }}
                                className="gap-1.5 h-8 text-xs"
                              >
                                <XCircle className="size-3.5" />
                                <span>Отменить конвертацию</span>
                              </Button>
                            </div>
                          )}

                          <div>
                            <div className="text-xs font-semibold mb-2 flex items-center gap-1.5 text-foreground">
                              <Terminal className="size-3.5 text-muted-foreground" />
                              <span>Подпроцессы инстанса ({subCount})</span>
                            </div>

                            {subCount === 0 ? (
                              <div className="text-xs text-muted-foreground italic py-2">
                                Нет активных дочерних процессов (FFmpeg/FFprobe). Воркер находится в режиме ожидания.
                              </div>
                            ) : (
                              <div className="rounded border bg-background overflow-hidden">
                                <Table>
                                  <TableHeader>
                                    <TableRow className="text-xs">
                                      <TableHead className="w-[80px]">PID</TableHead>
                                      <TableHead className="w-[100px]">Процесс</TableHead>
                                      <TableHead>Команда и параметры</TableHead>
                                      <TableHead className="w-[70px]">CPU</TableHead>
                                      <TableHead className="w-[80px]">Память</TableHead>
                                      <TableHead className="w-[90px]">Время</TableHead>
                                      <TableHead className="w-[110px] text-right">Действие</TableHead>
                                    </TableRow>
                                  </TableHeader>
                                  <TableBody>
                                    {i.subprocesses?.map((sub) => (
                                      <TableRow key={sub.pid} className="text-xs font-mono">
                                        <TableCell>{sub.pid}</TableCell>
                                        <TableCell className="font-sans font-medium">{sub.name}</TableCell>
                                        <TableCell
                                          className="text-muted-foreground text-[11px] truncate max-w-[320px]"
                                          title={sub.cmdline}
                                        >
                                          {sub.cmdline}
                                        </TableCell>
                                        <TableCell>{sub.cpu_percent.toFixed(1)}%</TableCell>
                                        <TableCell>{sub.rss_mb.toFixed(1)} МБ</TableCell>
                                        <TableCell>{fmtDuration(sub.running_sec)}</TableCell>
                                        <TableCell className="text-right">
                                          <Button
                                            size="sm"
                                            variant="destructive"
                                            disabled={cancelMutation.isPending}
                                            onClick={(e) => {
                                              e.stopPropagation()
                                              cancelMutation.mutate({
                                                pid: sub.pid,
                                                token: i.current_job?.token,
                                              })
                                            }}
                                            className="h-7 px-2 text-[11px] gap-1 font-sans"
                                          >
                                            <XCircle className="size-3" />
                                            <span>Отменить</span>
                                          </Button>
                                        </TableCell>
                                      </TableRow>
                                    ))}
                                  </TableBody>
                                </Table>
                              </div>
                            )}
                          </div>
                        </div>
                      </TableCell>
                    </TableRow>
                  )}
                </div>
              )
            })}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
