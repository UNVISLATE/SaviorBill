import { useEffect, useState } from "react"
import { useQuery } from "@tanstack/react-query"

import { api } from "@/api/api.ts"
import { ChartCardBody } from "@/components/charts/ChartCard"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/shadsnui/card"

interface ServiceTotal {
  count: number
  cpu_percent: number
  rss_mb: number
}

interface StatsResponse {
  instances: unknown[]
  totals_by_service: Record<string, ServiceTotal>
  grand_total: ServiceTotal
}

const SERVICE_LABEL: Record<string, string> = {
  billing: "Billing",
  media: "Mediaworker",
  lua: "Lua",
}

// Живые "последние N точек" без сохранения истории на backend — проще и
// достаточно для наблюдения за трендом прямо сейчас (см. IMPLEMENTATION_PLAN.md
// §2: явно решили не персистить историю метрик).
const MAX_POINTS = 30
const POLL_MS = 4000

interface ChartPoint {
  t: string
  cpu: number
  rss: number
}

export function SystemOverview() {
  const [points, setPoints] = useState<ChartPoint[]>([])

  const { data } = useQuery({
    queryKey: ["system-stats"],
    queryFn: async () => (await api.get<StatsResponse>("/v1/system/stats")).data,
    refetchInterval: POLL_MS,
  })

  useEffect(() => {
    if (!data) return
    setPoints((prev) => {
      const next = [
        ...prev,
        {
          t: new Date().toLocaleTimeString(),
          cpu: Math.round(data.grand_total.cpu_percent * 10) / 10,
          rss: Math.round(data.grand_total.rss_mb),
        },
      ]
      return next.slice(-MAX_POINTS)
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data])

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Всего инстансов</CardDescription>
            <CardTitle className="text-2xl">{data?.grand_total.count ?? "—"}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Суммарный CPU</CardDescription>
            <CardTitle className="text-2xl">
              {data ? `${data.grand_total.cpu_percent.toFixed(1)}%` : "—"}
            </CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Суммарная RSS</CardDescription>
            <CardTitle className="text-2xl">
              {data ? `${Math.round(data.grand_total.rss_mb)} МБ` : "—"}
            </CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Обновление</CardDescription>
            <CardTitle className="text-2xl">каждые {POLL_MS / 1000}с</CardTitle>
          </CardHeader>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {Object.entries(data?.totals_by_service ?? {}).map(([svc, t]) => (
          <Card key={svc}>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">{SERVICE_LABEL[svc] ?? svc}</CardTitle>
              <CardDescription>{t.count} инстанс(ов)</CardDescription>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">
              CPU: {t.cpu_percent.toFixed(1)}% · RSS: {Math.round(t.rss_mb)} МБ
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Потребление во времени (live)</CardTitle>
          <CardDescription>Последние {MAX_POINTS} замеров, без сохранения истории</CardDescription>
        </CardHeader>
        <CardContent>
          <ChartCardBody
            data={points}
            xKey="t"
            series={[
              { key: "cpu", label: "CPU %", color: "#009080", yAxisId: "cpu" },
              { key: "rss", label: "RSS МБ", color: "#0D504B", yAxisId: "rss" },
            ]}
            height={256}
          />
        </CardContent>
      </Card>
    </div>
  )
}
