import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Ban, Clock, Gauge, Lock, RefreshCw, ShieldAlert, ShieldCheck } from "lucide-react"

import { api } from "@/api/api.ts"
import { useAuth } from "@/hooks/use-auth"
import { toastError, toastSuccess } from "@/lib/toast"
import { Badge } from "@/components/shadsnui/badge"
import { Button } from "@/components/shadsnui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/shadsnui/card"
import { Input } from "@/components/shadsnui/input"
import { Label } from "@/components/shadsnui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/shadsnui/select"
import { Switch } from "@/components/shadsnui/switch"
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
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/shadsnui/dialog"

interface RateLimitRule {
  kind: string
  max_hits: number
  window: number
  overridden: boolean
}

interface AutobanSettings {
  enabled: boolean
  threshold: number
  window_sec: number
  duration_sec: number
}

interface CatalogPublicSettings {
  limit_max: number
  limit_step: number
  cache_ttl_sec: number
}

interface SecuritySettingsData {
  rate_limits: RateLimitRule[]
  autoban: AutobanSettings
  catalog_public: CatalogPublicSettings
}

interface BannedIpItem {
  ip: string
  banned_at?: string
  reason?: string
  duration_sec?: number
  ttl_remaining_sec?: number
}

const KIND_LABEL: Record<string, string> = {
  default: "По умолчанию",
  auth: "Аутентификация",
  mail: "Почта",
  sensitive: "Чувствительные операции",
  critical: "Критические мутации (платежи/баланс)",
}

export function SecuritySettings() {
  const { can } = useAuth()
  const qc = useQueryClient()
  const canEdit = can("settings.security.edit") || can("settings.ratelimits.edit") || can("settings.edit")

  // State for rate limit edits
  const [drafts, setDrafts] = useState<Record<string, { max_hits: string; window: string }>>({})

  // State for autoban edits
  const [autobanDraft, setAutobanDraft] = useState<AutobanSettings | null>(null)

  // State for catalog public edits
  const [catalogDraft, setCatalogDraft] = useState<CatalogPublicSettings | null>(null)

  // State for manual IP ban dialog
  const [isBanDialogOpen, setIsBanDialogOpen] = useState(false)
  const [manualIp, setManualIp] = useState("")
  const [manualDuration, setManualDuration] = useState("900")
  const [manualReason, setManualReason] = useState("Ручная блокировка администратором")

  // 1. Fetch Security Settings
  const { data: secData, isLoading: isSecLoading } = useQuery({
    queryKey: ["admin-security-settings"],
    queryFn: async () => (await api.get<SecuritySettingsData>("/v1/admin/settings/security")).data,
  })

  // 2. Fetch Banned IPs
  const { data: bannedIps, isLoading: isBansLoading, refetch: refetchBans } = useQuery({
    queryKey: ["system-banned-ips"],
    queryFn: async () => (await api.get<BannedIpItem[]>("/v1/system/security/banned-ips")).data,
    refetchInterval: 10000,
  })

  // Mutations
  const saveRateLimit = useMutation({
    mutationFn: async (kind: string) => {
      const d = drafts[kind]
      const rule = secData?.rate_limits.find((r) => r.kind === kind)
      await api.put(`/v1/admin/settings/ratelimits/${kind}`, {
        max_hits: Number(d?.max_hits ?? rule?.max_hits),
        window: Number(d?.window ?? rule?.window),
      })
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["admin-security-settings"] })
      toastSuccess("Лимит обновлён")
    },
    onError: () => toastError("Не удалось обновить лимит"),
  })

  const resetRateLimit = useMutation({
    mutationFn: async (kind: string) => {
      await api.delete(`/v1/admin/settings/ratelimits/${kind}`)
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["admin-security-settings"] })
      toastSuccess("Сброшено к значению из окружения")
    },
    onError: () => toastError("Не удалось сбросить лимит"),
  })

  const saveAutoban = useMutation({
    mutationFn: async () => {
      const payload = autobanDraft ?? secData?.autoban
      if (!payload) return
      await api.put("/v1/admin/settings/security", { autoban: payload })
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["admin-security-settings"] })
      setAutobanDraft(null)
      toastSuccess("Настройки Auto-Ban сохранены")
    },
    onError: () => toastError("Не удалось сохранить настройки Auto-Ban"),
  })

  const saveCatalogPublic = useMutation({
    mutationFn: async () => {
      const payload = catalogDraft ?? secData?.catalog_public
      if (!payload) return
      const res = await api.put<SecuritySettingsData>("/v1/admin/settings/security", {
        catalog_public: payload,
      })
      return res.data
    },
    onSuccess: (data) => {
      void qc.invalidateQueries({ queryKey: ["admin-security-settings"] })
      setCatalogDraft(null)
      if (data) {
        toastSuccess(
          `Лимиты каталога обновлены. Снап: ${data.catalog_public.limit_max} (шаг ${data.catalog_public.limit_step})`
        )
      } else {
        toastSuccess("Лимиты каталога обновлены")
      }
    },
    onError: () => toastError("Не удалось сохранить параметры каталога"),
  })

  const banIpMutation = useMutation({
    mutationFn: async () => {
      await api.post("/v1/system/security/banned-ips", {
        ip: manualIp.trim(),
        duration_sec: Number(manualDuration),
        reason: manualReason.trim() || "Ручная блокировка",
      })
    },
    onSuccess: () => {
      setIsBanDialogOpen(false)
      setManualIp("")
      void qc.invalidateQueries({ queryKey: ["system-banned-ips"] })
      void qc.invalidateQueries({ queryKey: ["system-security-events"] })
      toastSuccess("IP-адрес успешно заблокирован")
    },
    onError: () => toastError("Не удалось заблокировать IP"),
  })

  const unbanIpMutation = useMutation({
    mutationFn: async (ip: string) => {
      await api.delete(`/v1/system/security/banned-ips/${encodeURIComponent(ip)}`)
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["system-banned-ips"] })
      void qc.invalidateQueries({ queryKey: ["system-security-events"] })
      toastSuccess("IP-адрес разблокирован")
    },
    onError: () => toastError("Не удалось разблокировать IP"),
  })

  const curAutoban = autobanDraft ?? secData?.autoban ?? {
    enabled: true,
    threshold: 5,
    window_sec: 60,
    duration_sec: 900,
  }

  const curCatalog = catalogDraft ?? secData?.catalog_public ?? {
    limit_max: 20,
    limit_step: 10,
    cache_ttl_sec: 180,
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <ShieldCheck className="size-5 text-primary" />
          Центр безопасности
        </h2>
        <p className="text-sm text-muted-foreground">
          Управление лимитами частоты запросов, автоматическими блокировками (Auto-Ban), защитой
          публичного каталога и списком заблокированных IP.
        </p>
      </div>

      {/* Раздел 1: Auto-Ban & Защита от скрапинга */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <CardTitle className="text-base flex items-center gap-2">
                <ShieldAlert className="size-4 text-amber-500" />
                Автоматическая блокировка (Auto-Ban)
              </CardTitle>
              <CardDescription>
                При частых превышениях лимитов (Rate Limit breach) или аномальном скрапинге IP
                автоматически изолируется на заданное время.
              </CardDescription>
            </div>
            <div className="flex items-center gap-2">
              <Label htmlFor="autoban-toggle" className="text-sm cursor-pointer">
                {curAutoban.enabled ? "Включено" : "Отключено"}
              </Label>
              <Switch
                id="autoban-toggle"
                checked={curAutoban.enabled}
                onCheckedChange={(checked) =>
                  setAutobanDraft({ ...curAutoban, enabled: !!checked })
                }
                disabled={!canEdit}
              />
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Порог нарушений (штук)</Label>
              <Input
                type="number"
                min={1}
                max={100}
                value={curAutoban.threshold}
                onChange={(e) =>
                  setAutobanDraft({ ...curAutoban, threshold: Number(e.target.value) })
                }
                disabled={!canEdit || !curAutoban.enabled}
              />
              <span className="text-xs text-muted-foreground">
                Количество превышений для активации бана
              </span>
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Окно нарушений (сек)</Label>
              <Input
                type="number"
                min={5}
                max={3600}
                value={curAutoban.window_sec}
                onChange={(e) =>
                  setAutobanDraft({ ...curAutoban, window_sec: Number(e.target.value) })
                }
                disabled={!canEdit || !curAutoban.enabled}
              />
              <span className="text-xs text-muted-foreground">Период фиксации нарушений</span>
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Длительность бана (сек)</Label>
              <Input
                type="number"
                min={60}
                max={86400 * 30}
                value={curAutoban.duration_sec}
                onChange={(e) =>
                  setAutobanDraft({ ...curAutoban, duration_sec: Number(e.target.value) })
                }
                disabled={!canEdit || !curAutoban.enabled}
              />
              <span className="text-xs text-muted-foreground">
                Время изоляции IP ({Math.round(curAutoban.duration_sec / 60)} мин)
              </span>
            </div>
          </div>

          {canEdit && autobanDraft && (
            <div className="flex justify-end gap-2 pt-2 border-t">
              <Button variant="ghost" size="sm" onClick={() => setAutobanDraft(null)}>
                Отмена
              </Button>
              <Button
                size="sm"
                onClick={() => saveAutoban.mutate()}
                disabled={saveAutoban.isPending}
              >
                Сохранить параметры Auto-Ban
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Раздел 2: Квантование и защита публичного каталога */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Gauge className="size-4 text-blue-500" />
            Пагинация и кэш публичного каталога
          </CardTitle>
          <CardDescription>
            Защита базы данных от глубокого сканирования. Значение максимального limit для
            неавторизованных запросов строго квантуется с фиксированным шагом (5 или 10) для
            максимального кэш-попадания (Cache Hit Rate).
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Макс. limit элементов</Label>
              <Input
                type="number"
                min={1}
                max={200}
                value={curCatalog.limit_max}
                onChange={(e) =>
                  setCatalogDraft({ ...curCatalog, limit_max: Number(e.target.value) })
                }
                disabled={!canEdit}
              />
              <span className="text-xs text-muted-foreground">
                Округляется вниз кратно шагу (квантование)
              </span>
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Шаг квантования</Label>
              <Select
                value={String(curCatalog.limit_step)}
                onValueChange={(val) =>
                  setCatalogDraft({ ...curCatalog, limit_step: Number(val) })
                }
                disabled={!canEdit}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="5">Шаг 5 (порции по 5, 10, 15, 20...)</SelectItem>
                  <SelectItem value="10">Шаг 10 (порции по 10, 20, 30, 40...)</SelectItem>
                </SelectContent>
              </Select>
              <span className="text-xs text-muted-foreground">Фиксирует разнообразие кэш-ключей</span>
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">TTL кэша каталога (сек)</Label>
              <Input
                type="number"
                min={10}
                max={86400}
                value={curCatalog.cache_ttl_sec}
                onChange={(e) =>
                  setCatalogDraft({ ...curCatalog, cache_ttl_sec: Number(e.target.value) })
                }
                disabled={!canEdit}
              />
              <span className="text-xs text-muted-foreground">
                Время жизни в Valkey ({Math.round(curCatalog.cache_ttl_sec / 60)} мин)
              </span>
            </div>
          </div>

          {canEdit && catalogDraft && (
            <div className="flex justify-end gap-2 pt-2 border-t">
              <Button variant="ghost" size="sm" onClick={() => setCatalogDraft(null)}>
                Отмена
              </Button>
              <Button
                size="sm"
                onClick={() => saveCatalogPublic.mutate()}
                disabled={saveCatalogPublic.isPending}
              >
                Сохранить параметры каталога
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Раздел 3: Категории Rate Limit */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-semibold">Категории Rate Limit</h3>
            <p className="text-sm text-muted-foreground">
              Действующие лимиты по областям API. Переопределения применяются немедленно без
              перезапуска сервиса.
            </p>
          </div>
        </div>

        <div className="rounded-lg border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Категория</TableHead>
                <TableHead className="w-36">Запросов (max_hits)</TableHead>
                <TableHead className="w-36">Окно (сек)</TableHead>
                <TableHead className="w-36">Источник</TableHead>
                <TableHead className="w-48 text-right" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {isSecLoading && (
                <TableRow>
                  <TableCell colSpan={5} className="py-8 text-center text-sm text-muted-foreground">
                    Загрузка правил…
                  </TableCell>
                </TableRow>
              )}
              {secData?.rate_limits.map((r) => {
                const draft = drafts[r.kind] ?? {
                  max_hits: String(r.max_hits),
                  window: String(r.window),
                }
                const isChanged =
                  draft.max_hits !== String(r.max_hits) || draft.window !== String(r.window)

                return (
                  <TableRow key={r.kind}>
                    <TableCell>
                      <div className="font-medium">{KIND_LABEL[r.kind] ?? r.kind}</div>
                      <code className="text-xs text-muted-foreground">{r.kind}</code>
                    </TableCell>
                    <TableCell>
                      <Input
                        type="number"
                        min={1}
                        value={draft.max_hits}
                        onChange={(e) =>
                          setDrafts((prev) => ({
                            ...prev,
                            [r.kind]: { ...draft, max_hits: e.target.value },
                          }))
                        }
                        disabled={!canEdit}
                        className="h-8 w-28"
                      />
                    </TableCell>
                    <TableCell>
                      <Input
                        type="number"
                        min={1}
                        value={draft.window}
                        onChange={(e) =>
                          setDrafts((prev) => ({
                            ...prev,
                            [r.kind]: { ...draft, window: e.target.value },
                          }))
                        }
                        disabled={!canEdit}
                        className="h-8 w-28"
                      />
                    </TableCell>
                    <TableCell>
                      {r.overridden ? (
                        <Badge variant="secondary">Настройки (DB)</Badge>
                      ) : (
                        <Badge variant="outline">ENV по умолчанию</Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-1">
                        {canEdit && (
                          <>
                            <Button
                              size="sm"
                              variant={isChanged ? "default" : "outline"}
                              disabled={!isChanged || saveRateLimit.isPending}
                              onClick={() => saveRateLimit.mutate(r.kind)}
                            >
                              Сохранить
                            </Button>
                            {r.overridden && (
                              <Button
                                size="sm"
                                variant="ghost"
                                title="Сбросить к ENV"
                                disabled={resetRateLimit.isPending}
                                onClick={() => resetRateLimit.mutate(r.kind)}
                              >
                                Сбросить
                              </Button>
                            )}
                          </>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      </div>

      {/* Раздел 4: Активные блокировки IP */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-semibold flex items-center gap-2">
              <Ban className="size-4 text-destructive" />
              Заблокированные IP-адреса
              {bannedIps && bannedIps.length > 0 && (
                <Badge variant="destructive" className="ml-1">
                  {bannedIps.length}
                </Badge>
              )}
            </h3>
            <p className="text-sm text-muted-foreground">
              Список адресов, изолированных вручную или системой Auto-Ban.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => refetchBans()}>
              <RefreshCw className="size-3.5 mr-1" />
              Обновить
            </Button>
            {canEdit && (
              <>
                <Button size="sm" variant="destructive" onClick={() => setIsBanDialogOpen(true)}>
                  <Lock className="size-3.5 mr-1" />
                  Заблокировать IP
                </Button>
                <Dialog open={isBanDialogOpen} onOpenChange={setIsBanDialogOpen}>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Блокировка IP-адреса</DialogTitle>
                    <DialogDescription>
                      Заблокированный IP будет немедленно отсекаться шлюзом со статусом HTTP 403
                      Forbidden.
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
                        placeholder="Ручная блокировка администратором"
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
                      disabled={!manualIp.trim() || banIpMutation.isPending}
                      onClick={() => banIpMutation.mutate()}
                    >
                      Заблокировать
                    </Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
              </>
            )}
          </div>
        </div>

        <div className="rounded-lg border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>IP-адрес</TableHead>
                <TableHead>Причина</TableHead>
                <TableHead>Заблокирован</TableHead>
                <TableHead>Осталось времени</TableHead>
                <TableHead className="w-32 text-right" />
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
                    Активных блокировок нет. Все IP имеют стандартный доступ.
                  </TableCell>
                </TableRow>
              )}
              {bannedIps?.map((item) => {
                const ttl = item.ttl_remaining_sec ?? 0
                const mins = Math.floor(ttl / 60)
                const secs = ttl % 60

                return (
                  <TableRow key={item.ip}>
                    <TableCell>
                      <span className="font-mono font-medium">{item.ip}</span>
                    </TableCell>
                    <TableCell>
                      <span className="text-sm">{item.reason || "—"}</span>
                    </TableCell>
                    <TableCell>
                      <span className="text-xs text-muted-foreground">
                        {item.banned_at ? new Date(item.banned_at).toLocaleString("ru-RU") : "—"}
                      </span>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1.5 text-xs font-mono">
                        <Clock className="size-3 text-muted-foreground" />
                        {mins > 0 ? `${mins}м ${secs}с` : `${secs}с`}
                      </div>
                    </TableCell>
                    <TableCell className="text-right">
                      {canEdit && (
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-8"
                          onClick={() => unbanIpMutation.mutate(item.ip)}
                          disabled={unbanIpMutation.isPending}
                        >
                          Разблокировать
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
    </div>
  )
}
