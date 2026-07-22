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
}

const STATE_VARIANT: Record<string, "outline" | "secondary" | "destructive"> = {
  ready: "outline",
  processing: "secondary",
  queued: "secondary",
  failed: "destructive",
  error: "destructive",
}

export function SystemTasks() {
  const [service, setService] = useState<"media" | "lua">("media")

  const { data, isLoading } = useQuery({
    queryKey: ["system-tasks", service],
    queryFn: async () =>
      (await api.get<TaskLogEntry[]>(`/v1/admin/tasks/${service}`, { params: { limit: 100 } })).data,
    refetchInterval: 4000,
  })

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <div>
          <h2 className="text-lg font-semibold">Задачи</h2>
          <p className="text-sm text-muted-foreground">
            Последние {data?.length ?? 0} фактов из журнала фоновых тасков (кольцевой буфер в Valkey).
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
                  Пусто.
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
