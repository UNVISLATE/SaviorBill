import { useState } from "react"
import { useQuery } from "@tanstack/react-query"

import { api } from "@/api/api.ts"
import { Badge } from "@/components/shadsnui/badge"
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

interface TaskLogEntry {
  kind: string
  op: string
  token_or_cid: string
  state: string
  detail: string | null
  owner_id: number | null
  ts: number
  meta?: Record<string, unknown> | null
}

function formatTimeMs(ts: number | string | Date | null | undefined): string {
  if (!ts) return "—"
  const d = typeof ts === "number" ? new Date(ts * 1000) : new Date(ts)
  if (isNaN(d.getTime())) return "—"
  const h = String(d.getHours()).padStart(2, "0")
  const m = String(d.getMinutes()).padStart(2, "0")
  const s = String(d.getSeconds()).padStart(2, "0")
  const ms = String(d.getMilliseconds()).padStart(3, "0")
  return `${h}:${m}:${s}.${ms}`
}

function formatDurationMs(ms: number | null | undefined): string {
  if (ms == null) return "—"
  const totalSec = Math.floor(ms / 1000)
  const remMs = ms % 1000
  const h = Math.floor(totalSec / 3600)
  const m = Math.floor((totalSec % 3600) / 60)
  const s = totalSec % 60
  const timeStr = `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}.${String(remMs).padStart(3, "0")}`
  if (ms < 1000) {
    return `${ms} мс (${timeStr})`
  }
  return `${timeStr} (${ms} мс)`
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

export function SystemTasks() {
  const [service, setService] = useState<"media" | "lua">("media")

  const { data, isLoading } = useQuery({
    queryKey: ["system-tasks-live", service],
    queryFn: async () =>
      (await api.get<TaskLogEntry[]>(`/v1/admin/tasks/${service}`, { params: { limit: 100 } })).data,
    refetchInterval: 4000,
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Оперативный буфер событий</h2>
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
              <TableHead>Длительность</TableHead>
              <TableHead>Владелец</TableHead>
              <TableHead>Детали</TableHead>
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
            {!isLoading && (data?.length ?? 0) === 0 && (
              <TableRow>
                <TableCell colSpan={7} className="py-8 text-center text-sm text-muted-foreground">
                  Нет активных задач в буфере.
                </TableCell>
              </TableRow>
            )}
            {data?.map((e, i) => {
              const durMs = (e.meta as Record<string, unknown> | undefined)?.duration_ms as number | undefined
              return (
                <TableRow key={i}>
                  <TableCell className="font-mono text-xs whitespace-nowrap">{formatTimeMs(e.ts)}</TableCell>
                  <TableCell className="font-medium text-xs">{e.op}</TableCell>
                  <TableCell className="max-w-[160px] truncate font-mono text-xs">{e.token_or_cid}</TableCell>
                  <TableCell>
                    <Badge variant={STATE_VARIANT[e.state] ?? "outline"}>{e.state}</Badge>
                  </TableCell>
                  <TableCell className="font-mono text-xs tabular-nums">
                    {durMs != null ? formatDurationMs(durMs) : "—"}
                  </TableCell>
                  <TableCell className="text-xs">{e.owner_id ?? "—"}</TableCell>
                  <TableCell className="max-w-xs truncate text-xs text-muted-foreground">{e.detail ?? "—"}</TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
