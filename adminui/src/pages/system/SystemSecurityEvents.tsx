import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  Ban,
  Check,
  Copy,
  Lock,
  RefreshCw,
  Search,
  ShieldAlert,
  Unlock,
} from "lucide-react"

import { api } from "@/api/api.ts"
import { useAuth } from "@/hooks/use-auth"
import { toastError, toastSuccess } from "@/lib/toast"
import { Badge } from "@/components/shadsnui/badge"
import { Button } from "@/components/shadsnui/button"
import { Input } from "@/components/shadsnui/input"
import { Label } from "@/components/shadsnui/label"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/shadsnui/dialog"
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/shadsnui/tabs"

interface SecurityEventItem {
  id: string
  trace_id: string | null
  ray_id?: string | null
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

interface BannedIpItem {
  ip: string
  banned_at?: string
  reason?: string
  duration_sec?: number
  ttl_remaining_sec?: number
}

const ACTION_BADGES: Record<string, { label: string; variant: "default" | "secondary" | "destructive" | "outline" }> = {
  rate_limit_exceeded: { label: "Rate Limit превышен", variant: "destructive" },
  rate_limited: { label: "Rate Limit превышен", variant: "destructive" },
  ip_banned: { label: "IP заблокирован", variant: "destructive" },
  ip_unbanned: { label: "IP разблокирован", variant: "secondary" },
  scraping_detected: { label: "Подозрительный скрапинг", variant: "outline" },
  bruteforce_attempt: { label: "Попытка подбора", variant: "destructive" },
}

export function SystemSecurityEvents() {
  const { can } = useAuth()
  const qc = useQueryClient()
  const canManage = can("system.security.manage") || can("settings.security.edit") || can("system")

  const [activeTab, setActiveTab] = useState("events")
  const [filterIp, setFilterIp] = useState("")
  const [search, setSearch] = useState("")
  const [limit, setLimit] = useState("100")
  const [copiedTraceId, setCopiedTraceId] = useState<string | null>(null)

  // Manual Ban State
  const [isBanDialogOpen, setIsBanDialogOpen] = useState(false)
  const [manualIp, setManualIp] = useState("")
  const [manualDuration, setManualDuration] = useState("900")
  const [manualReason, setManualReason] = useState("Ручная блокировка оператором")

  // 1. Security events
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

  // 2. Active banned IPs
  const { data: bannedIps, isLoading: isBansLoading, refetch: refetchBans, isFetching: isBansFetching } = useQuery({
    queryKey: ["system-banned-ips"],
    queryFn: async () => (await api.get<BannedIpItem[]>("/v1/system/security/banned-ips")).data,
    refetchInterval: 10000,
  })

  const banMutation = useMutation({
    mutationFn: async ({ ip, reason, duration }: { ip: string; reason: string; duration?: number }) => {
      await api.post("/v1/system/security/banned-ips", {
        ip,
        duration_sec: duration ?? 900,
        reason,
      })
    },
    onSuccess: () => {
      toastSuccess("IP-адрес успешно заблокирован")
      setIsBanDialogOpen(false)
      setManualIp("")
      void qc.invalidateQueries({ queryKey: ["system-security-events"] })
      void qc.invalidateQueries({ queryKey: ["system-banned-ips"] })
    },
    onError: () => toastError("Не удалось заблокировать IP"),
  })

  const unbanMutation = useMutation({
    mutationFn: async (ip: string) => {
      await api.delete(`/v1/system/security/banned-ips/${encodeURIComponent(ip)}`)
    },
    onSuccess: () => {
      toastSuccess("IP-адрес разблокирован")
      void qc.invalidateQueries({ queryKey: ["system-security-events"] })
      void qc.invalidateQueries({ queryKey: ["system-banned-ips"] })
    },
    onError: () => toastError("Не удалось разблокировать IP"),
  })

  const copyTraceId = (traceId: string) => {
    navigator.clipboard.writeText(traceId)
    setCopiedTraceId(traceId)
    setTimeout(() => setCopiedTraceId(null), 2000)
    toastSuccess("Trace ID скопирован")
  }

  const filteredEvents = data?.filter((ev) => {
    if (!search.trim()) return true
    const q = search.toLowerCase()
    const tid = ev.trace_id || ev.ray_id || ""
    return (
      ev.ip.toLowerCase().includes(q) ||
      tid.toLowerCase().includes(q) ||
      ev.action.toLowerCase().includes(q) ||
      ev.reason.toLowerCase().includes(q) ||
      ev.scope.toLowerCase().includes(q) ||
      (ev.user_login && ev.user_login.toLowerCase().includes(q))
    )
  })

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <ShieldAlert className="size-5 text-amber-500" />
            Оперативная безопасность (SecOps)
          </h2>
          <p className="text-sm text-muted-foreground">
            Журнал превышений лимитов, событий безопасности и управление активными блокировками IP.
          </p>
        </div>

        <div className="flex items-center gap-2">
          {canManage && (
            <Button size="sm" variant="destructive" onClick={() => setIsBanDialogOpen(true)}>
              <Lock className="size-3.5 mr-1" />
              Заблокировать IP
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              void refetch()
              void refetchBans()
            }}
            disabled={isFetching || isBansFetching}
          >
            <RefreshCw className={`size-3.5 mr-1 ${isFetching || isBansFetching ? "animate-spin" : ""}`} />
            Обновить
          </Button>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="mb-4">
          <TabsTrigger value="events" className="flex items-center gap-2">
            <ShieldAlert className="size-4" />
            Журнал событий
            {data && data.length > 0 && (
              <Badge variant="secondary" className="text-xs px-1.5 py-0">
                {data.length}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="bans" className="flex items-center gap-2">
            <Ban className="size-4 text-destructive" />
            Заблокированные IP
            {bannedIps && bannedIps.length > 0 && (
              <Badge variant="destructive" className="text-xs px-1.5 py-0">
                {bannedIps.length}
              </Badge>
            )}
          </TabsTrigger>
        </TabsList>

        {/* TAB 1: EVENTS */}
        <TabsContent value="events" className="space-y-4">
          {/* Панель фильтрации */}
          <div className="flex flex-col sm:flex-row items-center gap-2">
            <div className="relative flex-1 w-full">
              <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
              <Input
                placeholder="Поиск по причине, действию, пользователю или Trace ID..."
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
                  <TableHead>Trace ID</TableHead>
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
                  const tid = ev.trace_id || ev.ray_id

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
                        {tid ? (
                          <button
                            type="button"
                            onClick={() => copyTraceId(tid)}
                            className="inline-flex items-center gap-1 font-mono text-[11px] bg-muted hover:bg-muted/80 px-1.5 py-0.5 rounded cursor-pointer transition-colors max-w-[120px] truncate"
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
                                duration: 900,
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
        </TabsContent>

        {/* TAB 2: BANNED IPS */}
        <TabsContent value="bans" className="space-y-4">
          <div className="rounded-lg border bg-card">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>IP-адрес</TableHead>
                  <TableHead>Время блокировки</TableHead>
                  <TableHead>Причина</TableHead>
                  <TableHead>Осталось (TTL)</TableHead>
                  <TableHead className="w-32 text-right">Действие</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {isBansLoading && (
                  <TableRow>
                    <TableCell colSpan={5} className="py-8 text-center text-sm text-muted-foreground">
                      Загрузка списка блокировок…
                    </TableCell>
                  </TableRow>
                )}
                {bannedIps?.length === 0 && !isBansLoading && (
                  <TableRow>
                    <TableCell colSpan={5} className="py-8 text-center text-sm text-muted-foreground">
                      Активных блокировок IP нет. Система работает в штатном режиме.
                    </TableCell>
                  </TableRow>
                )}
                {bannedIps?.map((item) => {
                  const remSec = item.ttl_remaining_sec ?? 0
                  const remMin = Math.ceil(remSec / 60)
                  return (
                    <TableRow key={item.ip}>
                      <TableCell>
                        <span className="font-mono text-sm font-semibold text-destructive">
                          {item.ip}
                        </span>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {item.banned_at ? new Date(item.banned_at).toLocaleString("ru-RU") : "—"}
                      </TableCell>
                      <TableCell className="text-sm">
                        {item.reason || "Auto-Ban / Превышение лимитов"}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className="font-mono text-xs">
                          {remSec > 0 ? `~${remMin} мин (${remSec}с)` : "Бессрочно / Истекает"}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        {canManage && (
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-7 text-xs hover:bg-emerald-500/10 hover:text-emerald-500 hover:border-emerald-500/30"
                            title="Разблокировать IP"
                            onClick={() => unbanMutation.mutate(item.ip)}
                            disabled={unbanMutation.isPending}
                          >
                            <Unlock className="size-3 mr-1" />
                            Разбанить
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        </TabsContent>
      </Tabs>

      {/* Модалка ручной блокировки IP */}
      <Dialog open={isBanDialogOpen} onOpenChange={setIsBanDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Блокировка IP-адреса</DialogTitle>
            <DialogDescription>
              Заблокированный IP будет немедленно отсекаться шлюзом со статусом HTTP 403 Forbidden.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label htmlFor="ban-ip">IP-адрес</Label>
              <Input
                id="ban-ip"
                placeholder="например 198.51.100.42"
                value={manualIp}
                onChange={(e) => setManualIp(e.target.value)}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="ban-duration">Длительность блокировки</Label>
              <Select value={manualDuration} onValueChange={(val) => val && setManualDuration(val)}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="300">5 минут (300 сек)</SelectItem>
                  <SelectItem value="900">15 минут (900 сек)</SelectItem>
                  <SelectItem value="3600">1 час (3600 сек)</SelectItem>
                  <SelectItem value="86400">24 часа (1 день)</SelectItem>
                  <SelectItem value="604800">7 дней</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="ban-reason">Причина блокировки</Label>
              <Input
                id="ban-reason"
                placeholder="Ручная блокировка оператором"
                value={manualReason}
                onChange={(e) => setManualReason(e.target.value)}
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="ghost" onClick={() => setIsBanDialogOpen(false)}>
              Отмена
            </Button>
            <Button
              variant="destructive"
              disabled={!manualIp.trim() || banMutation.isPending}
              onClick={() =>
                banMutation.mutate({
                  ip: manualIp.trim(),
                  duration: Number(manualDuration),
                  reason: manualReason.trim() || "Ручная блокировка",
                })
              }
            >
              Заблокировать
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
