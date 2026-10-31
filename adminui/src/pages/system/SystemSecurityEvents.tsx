import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  Check,
  Copy,
  Lock,
  RefreshCw,
  Search,
  ShieldAlert,
} from "lucide-react"

import { api } from "@/api/api.ts"
import { useAuth } from "@/hooks/use-auth"
import { toastError, toastSuccess } from "@/lib/toast"
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

interface SecurityEventItem {
  id: string
  ray_id: string | null
  timestamp: string
  ip: string
  scope: string
  kind: string
  action: string
  reason: string
  details: string
  user_id: number | null
  user_login: string | null
}

const ACTION_BADGES: Record<string, { label: string; variant: "default" | "secondary" | "destructive" | "outline" }> = {
  rate_limit_exceeded: { label: "Rate Limit превышен", variant: "destructive" },
  ip_banned: { label: "IP заблокирован", variant: "destructive" },
  ip_unbanned: { label: "IP разблокирован", variant: "secondary" },
  scraping_detected: { label: "Подозрительный скрапинг", variant: "outline" },
  bruteforce_attempt: { label: "Попытка подбора", variant: "destructive" },
}

export function SystemSecurityEvents() {
  const { can } = useAuth()
  const qc = useQueryClient()
  const canManage = can("system.security.manage") || can("settings.security.edit") || can("system")

  const [filterIp, setFilterIp] = useState("")
  const [search, setSearch] = useState("")
  const [limit, setLimit] = useState("100")
  const [copiedRayId, setCopiedRayId] = useState<string | null>(null)

  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["system-security-events", limit, filterIp],
    queryFn: async () => {
      const params = new URLSearchParams()
      params.set("limit", limit)
      if (filterIp.trim()) {
        params.set("ip", filterIp.trim())
      }
      return (await api.get<SecurityEventItem[]>(`/v1/system/security/events?${params.toString()}`)).data
    },
    refetchInterval: 10000,
  })

  const banMutation = useMutation({
    mutationFn: async ({ ip, reason }: { ip: string; reason: string }) => {
      await api.post("/v1/system/security/banned-ips", {
        ip,
        duration_sec: 900,
        reason,
      })
    },
    onSuccess: () => {
      toastSuccess("IP-адрес заблокирован на 15 минут")
      void qc.invalidateQueries({ queryKey: ["system-security-events"] })
      void qc.invalidateQueries({ queryKey: ["system-banned-ips"] })
    },
    onError: () => toastError("Не удалось заблокировать IP"),
  })

  const copyRayId = (rayId: string) => {
    navigator.clipboard.writeText(rayId)
    setCopiedRayId(rayId)
    setTimeout(() => setCopiedRayId(null), 2000)
    toastSuccess("Ray ID скопирован")
  }

  const filteredEvents = data?.filter((ev) => {
    if (!search.trim()) return true
    const q = search.toLowerCase()
    return (
      ev.ip.toLowerCase().includes(q) ||
      (ev.ray_id && ev.ray_id.toLowerCase().includes(q)) ||
      ev.action.toLowerCase().includes(q) ||
      ev.reason.toLowerCase().includes(q) ||
      ev.scope.toLowerCase().includes(q) ||
      (ev.user_login && ev.user_login.toLowerCase().includes(q))
    )
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <ShieldAlert className="size-5 text-amber-500" />
            События безопасности
          </h2>
          <p className="text-sm text-muted-foreground">
            Журнал превышений лимитов частоты, автоматических и ручных блокировок IP в реальном
            времени.
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

      {/* Панель фильтрации */}
      <div className="flex flex-col sm:flex-row items-center gap-2">
        <div className="relative flex-1 w-full">
          <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
          <Input
            placeholder="Поиск по причине, действию, пользователю или Ray ID..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-8 h-9"
          />
        </div>

        <div className="w-full sm:w-48">
          <Input
            placeholder="Фильтр по IP..."
            value={filterIp}
            onChange={(e) => setFilterIp(e.target.value)}
            className="h-9"
          />
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

      {/* Таблица событий */}
      <div className="rounded-lg border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Время (UTC/МСК)</TableHead>
              <TableHead>Действие</TableHead>
              <TableHead>IP-адрес</TableHead>
              <TableHead>Область / Категория</TableHead>
              <TableHead>Причина и детали</TableHead>
              <TableHead>Пользователь</TableHead>
              <TableHead>Ray ID</TableHead>
              <TableHead className="w-24 text-right" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={8} className="py-8 text-center text-sm text-muted-foreground">
                  Загрузка журнала безопасности…
                </TableCell>
              </TableRow>
            )}
            {filteredEvents?.length === 0 && !isLoading && (
              <TableRow>
                <TableCell colSpan={8} className="py-8 text-center text-sm text-muted-foreground">
                  Событий безопасности не зафиксировано.
                </TableCell>
              </TableRow>
            )}
            {filteredEvents?.map((ev) => {
              const badgeDef = ACTION_BADGES[ev.action] ?? {
                label: ev.action,
                variant: "secondary" as const,
              }

              return (
                <TableRow key={ev.id}>
                  <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                    {new Date(ev.timestamp).toLocaleString("ru-RU")}
                  </TableCell>
                  <TableCell>
                    <Badge variant={badgeDef.variant}>{badgeDef.label}</Badge>
                  </TableCell>
                  <TableCell>
                    <span className="font-mono text-xs font-semibold">{ev.ip}</span>
                  </TableCell>
                  <TableCell>
                    <div className="text-xs font-medium">{ev.scope}</div>
                    <code className="text-[10px] text-muted-foreground">{ev.kind}</code>
                  </TableCell>
                  <TableCell>
                    <div className="text-sm font-medium">{ev.reason}</div>
                    {ev.details && (
                      <div className="text-xs text-muted-foreground line-clamp-1">{ev.details}</div>
                    )}
                  </TableCell>
                  <TableCell>
                    {ev.user_login ? (
                      <span className="text-xs font-medium">
                        {ev.user_login} (id: {ev.user_id})
                      </span>
                    ) : (
                      <span className="text-xs text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell>
                    {ev.ray_id ? (
                      <button
                        type="button"
                        onClick={() => copyRayId(ev.ray_id!)}
                        className="inline-flex items-center gap-1 font-mono text-[11px] bg-muted hover:bg-muted/80 px-1.5 py-0.5 rounded cursor-pointer transition-colors"
                        title="Нажмите для копирования Ray ID"
                      >
                        {ev.ray_id}
                        {copiedRayId === ev.ray_id ? (
                          <Check className="size-3 text-emerald-500" />
                        ) : (
                          <Copy className="size-3 text-muted-foreground" />
                        )}
                      </button>
                    ) : (
                      <span className="text-xs text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    {canManage && ev.action !== "ip_banned" && (
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-7 text-xs text-destructive hover:bg-destructive/10"
                        title="Заблокировать IP на 15 мин"
                        onClick={() =>
                          banMutation.mutate({
                            ip: ev.ip,
                            reason: `Блокировка по событию ${ev.action}`,
                          })
                        }
                        disabled={banMutation.isPending}
                      >
                        <Lock className="size-3 mr-1" />
                        Бан
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
