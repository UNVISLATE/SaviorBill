import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Gauge, Info, ShieldAlert, ShieldCheck, Zap } from "lucide-react"

import { api } from "@/api/api.ts"
import { useAuth } from "@/hooks/use-auth"
import { toastError, toastSuccess } from "@/lib/toast"
import { Badge } from "@/components/shadsnui/badge"
import { Button } from "@/components/shadsnui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/shadsnui/card"
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
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/shadsnui/tooltip"

interface RateLimitRule {
  kind: string
  max_hits: number
  window: number
  burst_hits: number
  burst_window: number
  overridden: boolean
}

interface AutobanSettings {
  enabled: boolean
  threshold: number
  window_sec: number
  duration_sec: number
}

interface CatalogPublicSettings {
  enabled: boolean
  limit_max_guest?: number
  limit_max_auth?: number
  limit_max?: number
  limit_step: number
  cache_ttl_sec: number
}

interface SecuritySettingsData {
  rate_limits: RateLimitRule[]
  autoban: AutobanSettings
  catalog_public: CatalogPublicSettings
}

const KIND_LABEL: Record<string, string> = {
  default: "По умолчанию",
  auth: "Аутентификация",
  mail: "Почта",
  sensitive: "Чувствительные операции",
  critical: "Критические мутации (платежи/баланс)",
}

function HintIcon({ text }: { text: string }) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <button
            type="button"
            aria-label={text}
            className="inline-flex text-muted-foreground/60 transition-colors hover:text-foreground cursor-help"
          >
            <Info className="size-3.5" />
          </button>
        }
      />
      <TooltipContent className="max-w-xs text-xs font-normal leading-relaxed">{text}</TooltipContent>
    </Tooltip>
  )
}

export function SecuritySettings() {
  const { can } = useAuth()
  const qc = useQueryClient()
  const canEdit =
    can("settings.security.edit") || can("settings.ratelimits.edit") || can("settings.edit")

  // State for rate limit edits
  const [drafts, setDrafts] = useState<
    Record<string, { max_hits: string; window: string; burst_hits: string }>
  >({})

  // State for autoban edits
  const [autobanDraft, setAutobanDraft] = useState<AutobanSettings | null>(null)

  // State for catalog public edits
  const [catalogDraft, setCatalogDraft] = useState<CatalogPublicSettings | null>(null)

  // 1. Fetch Security Settings
  const { data: secData, isLoading: isSecLoading } = useQuery({
    queryKey: ["admin-security-settings"],
    queryFn: async () => (await api.get<SecuritySettingsData>("/v1/admin/settings/security")).data,
  })

  // Mutations
  const saveRateLimit = useMutation({
    mutationFn: async (kind: string) => {
      const d = drafts[kind]
      const rule = secData?.rate_limits.find((r) => r.kind === kind)
      await api.put(`/v1/admin/settings/ratelimits/${kind}`, {
        max_hits: Number(d?.max_hits ?? rule?.max_hits),
        window: Number(d?.window ?? rule?.window),
        burst_hits: Number(d?.burst_hits ?? rule?.burst_hits),
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
      toastSuccess("Сброшено к значению по умолчанию")
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
      void qc.invalidateQueries({ queryKey: ["system-cache-stats"] })
      setCatalogDraft(null)
      if (data) {
        const gMax = data.catalog_public.limit_max_guest ?? data.catalog_public.limit_max ?? 20
        const aMax = data.catalog_public.limit_max_auth ?? 100
        toastSuccess(
          `Параметры каталога обновлены (кэш: ${data.catalog_public.enabled ? "вкл" : "выкл"}, гости: ${gMax}, клиенты: ${aMax})`
        )
      } else {
        toastSuccess("Параметры каталога обновлены")
      }
    },
    onError: () => toastError("Не удалось сохранить параметры каталога"),
  })

  const curAutoban = autobanDraft ?? secData?.autoban ?? {
    enabled: true,
    threshold: 5,
    window_sec: 60,
    duration_sec: 900,
  }

  const curCatalog = catalogDraft ?? secData?.catalog_public ?? {
    enabled: true,
    limit_max_guest: 20,
    limit_max_auth: 100,
    limit_max: 20,
    limit_step: 10,
    cache_ttl_sec: 3600,
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <ShieldCheck className="size-5 text-primary" />
          Центр безопасности
        </h2>
        <p className="text-sm text-muted-foreground">
          Управление лимитами частоты запросов, автоматическими блокировками и кэшированием каталога.
        </p>
      </div>

      {/* Раздел 1: Auto-Ban & Защита от скрапинга */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base flex items-center gap-2">
              <ShieldAlert className="size-4 text-amber-500" />
              Автоматическая блокировка (Auto-Ban)
              <HintIcon text="При серии частых превышений лимитов IP-адрес автоматически изолируется со статусом HTTP 403 Forbidden" />
            </CardTitle>
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
              <div className="flex items-center gap-1.5">
                <Label className="text-xs text-muted-foreground">Порог нарушений (штук)</Label>
                <HintIcon text="Количество превышений Rate Limit за контрольное окно, вызывающее временный бан IP" />
              </div>
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
            </div>

            <div className="space-y-1.5">
              <div className="flex items-center gap-1.5">
                <Label className="text-xs text-muted-foreground">Окно нарушений (сек)</Label>
                <HintIcon text="Период в секундах, за который суммируются нарушения лимитов" />
              </div>
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
            </div>

            <div className="space-y-1.5">
              <div className="flex items-center gap-1.5">
                <Label className="text-xs text-muted-foreground">Длительность бана (сек)</Label>
                <HintIcon text={`Время изоляции нарушившего IP-адреса (${Math.round(curAutoban.duration_sec / 60)} мин)`} />
              </div>
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

      {/* Раздел 2: Квантование и кэш публичного каталога */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base flex items-center gap-2">
              <Gauge className="size-4 text-blue-500" />
              Пагинация и кэш каталога
              <HintIcon text="Двухуровневый кэш в Valkey (индекс ID + сущности карточек) снижает нагрузку на базу до 0 запросов при просмотре страниц" />
            </CardTitle>
            <div className="flex items-center gap-2">
              <Label htmlFor="cache-toggle" className="text-sm cursor-pointer">
                {curCatalog.enabled ? "Кэш активен" : "Кэш отключен"}
              </Label>
              <Switch
                id="cache-toggle"
                checked={curCatalog.enabled}
                onCheckedChange={(checked) =>
                  setCatalogDraft({ ...curCatalog, enabled: !!checked })
                }
                disabled={!canEdit}
              />
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="space-y-1.5">
              <div className="flex items-center gap-1.5">
                <Label className="text-xs text-muted-foreground">Макс. limit (гости)</Label>
                <HintIcon text="Максимальный размер страницы товаров для анонимных посетителей (по умолчанию: 20)" />
              </div>
              <Input
                type="number"
                min={1}
                max={200}
                value={curCatalog.limit_max_guest ?? curCatalog.limit_max ?? 20}
                onChange={(e) => {
                  const val = Number(e.target.value)
                  setCatalogDraft({
                    ...curCatalog,
                    limit_max_guest: val,
                    limit_max: val,
                  })
                }}
                disabled={!canEdit}
              />
            </div>

            <div className="space-y-1.5">
              <div className="flex items-center gap-1.5">
                <Label className="text-xs text-muted-foreground">Макс. limit (клиенты)</Label>
                <HintIcon text="Максимальный размер страницы для авторизованных клиентов (по умолчанию: 100)" />
              </div>
              <Input
                type="number"
                min={1}
                max={200}
                value={curCatalog.limit_max_auth ?? 100}
                onChange={(e) =>
                  setCatalogDraft({ ...curCatalog, limit_max_auth: Number(e.target.value) })
                }
                disabled={!canEdit}
              />
            </div>

            <div className="space-y-1.5">
              <div className="flex items-center gap-1.5">
                <Label className="text-xs text-muted-foreground">Шаг квантования</Label>
                <HintIcon text="Принудительное округление limit вниз до кратного шагу, предотвращает распыление кэш-ключей" />
              </div>
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
                  <SelectItem value="5">Шаг 5 (порции: 5, 10, 15, 20...)</SelectItem>
                  <SelectItem value="10">Шаг 10 (порции: 10, 20, 30, 40...)</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <div className="flex items-center gap-1.5">
                <Label className="text-xs text-muted-foreground">TTL кэша каталога (сек)</Label>
                <HintIcon text={`Время жизни кэша в Valkey (${Math.round(curCatalog.cache_ttl_sec / 60)} мин). При изменении или исчерпании товара кэш сбрасывается мгновенно.`} />
              </div>
              <Input
                type="number"
                min={10}
                max={86400 * 7}
                value={curCatalog.cache_ttl_sec}
                onChange={(e) =>
                  setCatalogDraft({ ...curCatalog, cache_ttl_sec: Number(e.target.value) })
                }
                disabled={!canEdit}
              />
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
            <h3 className="text-base font-semibold flex items-center gap-2">
              <Zap className="size-4 text-emerald-500" />
              Категории Rate Limit
              <HintIcon text="Ограничивает интенсивность запросов (sliding window) и резкие всплески (burst 1с). Изменения вступают в силу мгновенно." />
            </h3>
          </div>
        </div>

        <div className="rounded-lg border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Категория</TableHead>
                <TableHead className="w-32">Лимит (max)</TableHead>
                <TableHead className="w-32">Окно (сек)</TableHead>
                <TableHead className="w-32">
                  <span className="flex items-center gap-1">
                    Всплеск (1с)
                    <HintIcon text="Максимум запросов в секунду для сглаживания пиковых нагрузок (burst)" />
                  </span>
                </TableHead>
                <TableHead className="w-32">Источник</TableHead>
                <TableHead className="w-48 text-right" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {isSecLoading && (
                <TableRow>
                  <TableCell colSpan={6} className="py-8 text-center text-sm text-muted-foreground">
                    Загрузка правил…
                  </TableCell>
                </TableRow>
              )}
              {secData?.rate_limits.map((r) => {
                const draft = drafts[r.kind] ?? {
                  max_hits: String(r.max_hits),
                  window: String(r.window),
                  burst_hits: String(r.burst_hits ?? 15),
                }
                const isChanged =
                  draft.max_hits !== String(r.max_hits) ||
                  draft.window !== String(r.window) ||
                  draft.burst_hits !== String(r.burst_hits ?? 15)

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
                        className="h-8 w-24"
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
                        className="h-8 w-24"
                      />
                    </TableCell>
                    <TableCell>
                      <Input
                        type="number"
                        min={1}
                        value={draft.burst_hits}
                        onChange={(e) =>
                          setDrafts((prev) => ({
                            ...prev,
                            [r.kind]: { ...draft, burst_hits: e.target.value },
                          }))
                        }
                        disabled={!canEdit}
                        className="h-8 w-24"
                      />
                    </TableCell>
                    <TableCell>
                      {r.overridden ? (
                        <Badge variant="secondary">Настройки (DB)</Badge>
                      ) : (
                        <Badge variant="outline">По умолчанию</Badge>
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
                                title="Сбросить к дефолту"
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
    </div>
  )
}
