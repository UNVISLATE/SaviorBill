import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { XCircle, Terminal, Activity, Server, Clock, Cpu, HardDrive } from "lucide-react"

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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/shadsnui/dialog"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/shadsnui/alert-dialog"

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
  scheduler: "Scheduler",
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
  const [selectedMediaworker, setSelectedMediaworker] = useState<Instance | null>(null)
  const [confirmCancel, setConfirmCancel] = useState<{
    pid?: number
    token?: string
    description: string
  } | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ["system-stats"],
    queryFn: async () => (await api.get<StatsResponse>("/v1/system/stats")).data,
    refetchInterval: 4000,
  })

  // Synchronize selected mediaworker with latest polled data
  const currentMediaworker =
    selectedMediaworker &&
    data?.instances.find(
      (i) => i.service === selectedMediaworker.service && i.consumer === selectedMediaworker.consumer,
    )
  const activeModalInstance = currentMediaworker || selectedMediaworker

  const cancelMutation = useMutation({
    mutationFn: async ({ pid, token }: { pid?: number; token?: string }) => {
      return api.post("/v1/system/instances/media/cancel", { pid, token })
    },
    onSuccess: () => {
      toastSuccess("Сигнал отмены отправлен")
      void qc.invalidateQueries({ queryKey: ["system-stats"] })
      setConfirmCancel(null)
    },
    onError: (e: unknown) => {
      toastError("Ошибка при отправке сигнала отмены", getErrorDetail(e))
    },
  })

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Инстансы</h2>
        <p className="text-sm text-muted-foreground">
          Живые процессы billing/media/lua/scheduler по heartbeat в Valkey. Для инстанса Mediaworker доступен детальный просмотр процессов.
        </p>
      </div>
      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Сервис</TableHead>
              <TableHead>Инстанс</TableHead>
              <TableHead>Статус</TableHead>
              <TableHead>Uptime</TableHead>
              <TableHead>CPU</TableHead>
              <TableHead>RSS</TableHead>
              <TableHead className="w-[140px] text-right">Подпроцессы</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={7} className="py-8 text-center text-sm text-muted-foreground">
                  Загрузка…
                </TableCell>
              </TableRow>
            )}
            {!isLoading && (data?.instances.length ?? 0) === 0 && (
              <TableRow>
                <TableCell colSpan={7} className="py-8 text-center text-sm text-muted-foreground">
                  Нет живых инстансов.
                </TableCell>
              </TableRow>
            )}
            {data?.instances.map((i) => {
              const id = `${i.service}:${i.consumer}`
              const subCount = i.subprocesses?.length ?? 0
              const isMedia = i.service === "media"

              return (
                <TableRow
                  key={id}
                  className={isMedia ? "cursor-pointer hover:bg-muted/50 transition-colors" : ""}
                  onClick={isMedia ? () => setSelectedMediaworker(i) : undefined}
                >
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
                  <TableCell className="text-right">
                    {isMedia ? (
                      <Button
                        variant={subCount > 0 ? "secondary" : "ghost"}
                        size="sm"
                        onClick={(e) => {
                          e.stopPropagation()
                          setSelectedMediaworker(i)
                        }}
                        className="h-7 px-2.5 text-xs font-mono gap-1"
                      >
                        {subCount > 0 ? (
                          <>
                            <Activity className="size-3 text-amber-500 animate-pulse" />
                            <span>{subCount} шт.</span>
                          </>
                        ) : (
                          <span className="text-muted-foreground">0 шт.</span>
                        )}
                      </Button>
                    ) : (
                      <span className="text-muted-foreground text-xs pr-4">—</span>
                    )}
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </div>

      {/* Mediaworker Dialog */}
      <Dialog
        open={Boolean(activeModalInstance)}
        onOpenChange={(open) => !open && setSelectedMediaworker(null)}
      >
        <DialogContent className="max-w-3xl max-h-[85vh] flex flex-col p-6 space-y-4">
          <DialogHeader>
            <div className="flex items-center gap-2">
              <Server className="size-5 text-primary" />
              <DialogTitle className="text-lg">
                Инстанс Mediaworker: {activeModalInstance?.consumer}
              </DialogTitle>
              <Badge variant={activeModalInstance?.online ? "outline" : "destructive"} className="ml-auto">
                {activeModalInstance?.online ? "online" : "offline"}
              </Badge>
            </div>
            <DialogDescription>
              Конвертация, сжатие и генерация превью медиафайлов через FFmpeg.
            </DialogDescription>
          </DialogHeader>

          {activeModalInstance && (
            <div className="space-y-4 overflow-y-auto pr-1">
              {/* Metrics grid */}
              <div className="grid grid-cols-3 gap-3">
                <div className="rounded-lg border bg-muted/30 p-3 space-y-1">
                  <div className="text-[11px] text-muted-foreground flex items-center gap-1.5">
                    <Clock className="size-3.5" />
                    <span>Время работы (Uptime)</span>
                  </div>
                  <div className="font-mono text-sm font-semibold">
                    {fmtUptime(activeModalInstance.uptime_sec)}
                  </div>
                </div>
                <div className="rounded-lg border bg-muted/30 p-3 space-y-1">
                  <div className="text-[11px] text-muted-foreground flex items-center gap-1.5">
                    <Cpu className="size-3.5" />
                    <span>Нагрузка CPU</span>
                  </div>
                  <div className="font-mono text-sm font-semibold">
                    {activeModalInstance.cpu_percent.toFixed(1)}%
                  </div>
                </div>
                <div className="rounded-lg border bg-muted/30 p-3 space-y-1">
                  <div className="text-[11px] text-muted-foreground flex items-center gap-1.5">
                    <HardDrive className="size-3.5" />
                    <span>Память (RSS)</span>
                  </div>
                  <div className="font-mono text-sm font-semibold">
                    {Math.round(activeModalInstance.rss_mb)} МБ
                  </div>
                </div>
              </div>

              {/* Active job */}
              {activeModalInstance.current_job ? (
                <div className="flex flex-wrap items-center justify-between gap-2 p-3 bg-card rounded-lg border text-xs">
                  <div className="space-y-0.5">
                    <div className="font-semibold text-foreground flex items-center gap-2">
                      <span className="flex size-2 rounded-full bg-amber-500 animate-pulse" />
                      <span>Активная задача: {activeModalInstance.current_job.op}</span>
                      <Badge variant="outline" className="font-mono text-[10px]">
                        {activeModalInstance.current_job.token}
                      </Badge>
                    </div>
                    <div className="text-muted-foreground pl-4">
                      В работе: {fmtDuration(Math.max(0, Date.now() / 1000 - activeModalInstance.current_job.started_at))}
                    </div>
                  </div>
                  <Button
                    size="sm"
                    variant="destructive"
                    disabled={cancelMutation.isPending}
                    onClick={() =>
                      setConfirmCancel({
                        token: activeModalInstance.current_job?.token,
                        description: `Будет остановлена задача конвертации для токена ${activeModalInstance.current_job?.token}.`,
                      })
                    }
                    className="gap-1.5 h-8 text-xs"
                  >
                    <XCircle className="size-3.5" />
                    <span>Отменить конвертацию</span>
                  </Button>
                </div>
              ) : (
                <div className="text-xs text-muted-foreground bg-muted/20 border rounded-lg p-3">
                  Нет активной задачи (воркер находится в режиме ожидания новых задач).
                </div>
              )}

              {/* Subprocesses */}
              <div className="space-y-2">
                <div className="text-xs font-semibold flex items-center gap-1.5 text-foreground">
                  <Terminal className="size-3.5 text-muted-foreground" />
                  <span>
                    Подпроцессы FFmpeg / FFprobe ({activeModalInstance.subprocesses?.length ?? 0})
                  </span>
                </div>

                {(activeModalInstance.subprocesses?.length ?? 0) === 0 ? (
                  <div className="text-xs text-muted-foreground italic py-3 text-center border rounded-lg bg-background">
                    Нет активных дочерних процессов (FFmpeg/FFprobe). Воркер находится в режиме ожидания.
                  </div>
                ) : (
                  <div className="rounded-lg border bg-background overflow-hidden">
                    <Table>
                      <TableHeader>
                        <TableRow className="text-xs">
                          <TableHead className="w-[70px]">PID</TableHead>
                          <TableHead className="w-[90px]">Процесс</TableHead>
                          <TableHead>Команда и параметры</TableHead>
                          <TableHead className="w-[60px]">CPU</TableHead>
                          <TableHead className="w-[80px]">Память</TableHead>
                          <TableHead className="w-[80px]">Время</TableHead>
                          <TableHead className="w-[100px] text-right">Действие</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {activeModalInstance.subprocesses?.map((sub) => (
                          <TableRow key={sub.pid} className="text-xs font-mono">
                            <TableCell>{sub.pid}</TableCell>
                            <TableCell className="font-sans font-medium">{sub.name}</TableCell>
                            <TableCell
                              className="text-muted-foreground text-[11px] truncate max-w-[280px]"
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
                                onClick={() =>
                                  setConfirmCancel({
                                    pid: sub.pid,
                                    token: activeModalInstance.current_job?.token,
                                    description: `Будет принудительно завершён подпроцесс PID ${sub.pid} (${sub.name}).`,
                                  })
                                }
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
          )}
        </DialogContent>
      </Dialog>

      {/* Confirmation AlertDialog for cancel */}
      <AlertDialog open={Boolean(confirmCancel)} onOpenChange={(open) => !open && setConfirmCancel(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Подтверждение отмены</AlertDialogTitle>
            <AlertDialogDescription>{confirmCancel?.description}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Закрыть</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive hover:bg-destructive/90 text-destructive-foreground"
              disabled={cancelMutation.isPending}
              onClick={() => {
                if (confirmCancel) {
                  cancelMutation.mutate({
                    pid: confirmCancel.pid,
                    token: confirmCancel.token,
                  })
                }
              }}
            >
              Подтвердить отмену
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
