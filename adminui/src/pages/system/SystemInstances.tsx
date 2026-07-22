import { useQuery } from "@tanstack/react-query"

import { api } from "@/api/api.ts"
import { Badge } from "@/components/shadsnui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/shadsnui/table"

interface Instance {
  service: string
  consumer: string
  online: boolean
  uptime_sec: number
  cpu_percent: number
  rss_mb: number
  last_seen_at: number
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

export function SystemInstances() {
  const { data, isLoading } = useQuery({
    queryKey: ["system-stats"],
    queryFn: async () => (await api.get<StatsResponse>("/v1/system/stats")).data,
    refetchInterval: 4000,
  })

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Инстансы</h2>
        <p className="text-sm text-muted-foreground">
          Живые процессы billing/media/lua по heartbeat в Valkey (TTL истёк — инстанс исчезает из списка).
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
            {!isLoading && (data?.instances.length ?? 0) === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="py-8 text-center text-sm text-muted-foreground">
                  Нет живых инстансов.
                </TableCell>
              </TableRow>
            )}
            {data?.instances.map((i) => (
              <TableRow key={`${i.service}:${i.consumer}`}>
                <TableCell className="font-medium">{SERVICE_LABEL[i.service] ?? i.service}</TableCell>
                <TableCell className="font-mono text-xs">{i.consumer}</TableCell>
                <TableCell>
                  <Badge variant={i.online ? "outline" : "destructive"}>
                    {i.online ? "online" : "offline"}
                  </Badge>
                </TableCell>
                <TableCell>{fmtUptime(i.uptime_sec)}</TableCell>
                <TableCell>{i.cpu_percent.toFixed(1)}%</TableCell>
                <TableCell>{Math.round(i.rss_mb)} МБ</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
