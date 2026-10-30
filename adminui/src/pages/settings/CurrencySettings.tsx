import { useState, useMemo } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  AlertCircle,
  ArrowDown,
  ArrowUp,
  BookOpen,
  CheckCircle2,
  Coins,
  ExternalLink,
  GripVertical,
  KeyRound,
  Loader2,
  Lock,
  Play,
  Plus,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  Sliders,
  Trash2,
  XCircle,
} from "lucide-react"

import { api } from "@/api/api.ts"
import { getErrorDetail } from "@/lib/api-error.ts"
import { toastError, toastSuccess } from "@/lib/toast"
import { SettingsSection } from "./SettingsSection"
import { TabbedDialog, type TabDefinition } from "@/components/common/TabbedDialog"
import { CurrencySelect } from "@/components/common/CurrencySelect"
import { LuaScriptSelect } from "@/components/common/LuaScriptSelect"
import { Badge } from "@/components/shadsnui/badge"
import { Button } from "@/components/shadsnui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/shadsnui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/shadsnui/dialog"
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

interface CurrencyStatus {
  currency: string
  can_change: boolean
  reason: string | null
  accounts_with_balance: number
  total_balance: string
  total_bonus: string
}

interface FxProvider {
  key: string
  title: string
  needs_key: boolean
  signup_url: string | null
  fixed_base: string | null
  note: string
}

export interface FxSourceItem {
  id: number
  type: "provider" | "lua" | "manual"
  name: string
  priority: number
  enabled: boolean
  provider?: string | null
  has_api_key?: boolean
  api_key?: string
  script_id?: number | null
  lua_slug?: string | null
  rates: Record<string, string>
  last_rates?: Record<string, string>
  last_fetched_at?: string | null
  last_error?: string | null
  last_error_at?: string | null
  last_rates_count?: number
}

interface FxHealth {
  has_errors: boolean
  count: number
  errors: Array<{
    id: number
    name: string
    provider: string | null
    error: string
    error_at: string | null
  }>
}

interface RateOverviewItem {
  currency: string
  rate_to_base: string
  source_id: number | null
  source_name: string
  priority: number
}

interface FxTestResult {
  ok: boolean
  base: string
  rates: Record<string, string>
  total: number
  error: string | null
}

interface RateEntry {
  code: string
  rate: string
}

const COMMON_CURRENCY_CODES = [
  "USD", "EUR", "USDT", "RUB", "TON", "BTC", "ETH", "CNY", "KZT", "BYN",
  "GBP", "TRY", "AED", "GEL", "AMD", "UZS", "UAH", "JPY", "CHF", "PLN",
]

/** Справка по готовым провайдерам (внутри вкладки диалога) */
function ProvidersReference({ providers }: { providers: FxProvider[] }) {
  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">
        Готовые API-провайдеры для автоматической загрузки котировок. Если провайдер требует ключ —
        зарегистрируйтесь по ссылке и сохраните его в параметрах источника.
      </p>
      <div className="divide-y rounded-lg border">
        {providers.map((p) => (
          <div key={p.key} className="flex items-start justify-between gap-4 p-3 text-xs">
            <div className="min-w-0 space-y-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold">{p.title}</span>
                {p.needs_key ? (
                  <Badge variant="outline" className="gap-1 text-[10px]">
                    <KeyRound className="size-3" /> нужен ключ
                  </Badge>
                ) : (
                  <Badge variant="outline" className="text-[10px] text-emerald-500">
                    без ключа
                  </Badge>
                )}
                {p.fixed_base && (
                  <Badge variant="outline" className="text-[10px]">
                    только базовая {p.fixed_base}
                  </Badge>
                )}
              </div>
              <p className="text-[11px] text-muted-foreground leading-relaxed">{p.note}</p>
            </div>
            {p.signup_url && (
              <a
                href={p.signup_url}
                target="_blank"
                rel="noreferrer"
                className="flex shrink-0 items-center gap-1 text-[11px] text-primary hover:underline font-medium"
              >
                Получить ключ <ExternalLink className="size-3" />
              </a>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

/** Диалог со всеми доступными валютами и котировками к базовой валюте */
function AllCurrenciesModal({
  open,
  onOpenChange,
  items,
  baseCurrency,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  items: RateOverviewItem[] | undefined
  baseCurrency: string
}) {
  const [filter, setFilter] = useState("")

  const filtered = useMemo(() => {
    if (!items) return []
    const q = filter.trim().toUpperCase()
    if (!q) return items
    return items.filter(
      (it) => it.currency.includes(q) || it.source_name.toUpperCase().includes(q)
    )
  }, [items, filter])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle className="text-base font-semibold">
            Доступные валюты и текущие котировки
          </DialogTitle>
          <DialogDescription className="text-xs">
            Все валюты, которые биллинг умеет конвертировать прямо сейчас. Котировка показывает,
            сколько единиц базовой валюты (<strong>{baseCurrency}</strong>) стоит 1 единица целевой валюты.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 py-1">
          <Input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Поиск по коду валюты или источнику..."
            className="text-xs h-8"
          />

          <div className="rounded-lg border max-h-80 overflow-y-auto">
            <Table>
              <TableHeader>
                <TableRow className="h-8">
                  <TableHead className="w-24 text-[11px]">Валюта</TableHead>
                  <TableHead className="text-[11px]">Курс к 1 {baseCurrency}</TableHead>
                  <TableHead className="text-[11px]">Активный источник</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((item) => (
                  <TableRow key={item.currency} className="h-9">
                    <TableCell className="font-mono font-bold text-xs">
                      <Badge
                        variant={item.currency === baseCurrency ? "default" : "secondary"}
                        className="font-mono text-[11px]"
                      >
                        {item.currency}
                      </Badge>
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {item.currency === baseCurrency ? (
                        <span className="text-muted-foreground">1.00 (базовая)</span>
                      ) : (
                        <span>
                          1 {item.currency} = <strong>{item.rate_to_base}</strong> {baseCurrency}
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      <div className="flex items-center gap-1.5">
                        <span className="truncate">{item.source_name}</span>
                        {item.priority >= 0 && (
                          <span className="text-[10px] font-mono font-semibold text-muted-foreground">
                            (#{item.priority + 1})
                          </span>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

/** Табированный диалог создания / редактирования источника курсов */
function SourceDialog({
  open,
  onOpenChange,
  source,
  providers,
  baseCurrency,
  onSave,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  source: FxSourceItem | null
  providers: FxProvider[] | undefined
  baseCurrency: string
  onSave: (data: {
    id?: number
    type: "provider" | "lua" | "manual"
    name: string
    provider?: string
    api_key?: string
    lua_slug?: string
    rates?: Record<string, string>
    enabled: boolean
  }) => Promise<void>
}) {
  const isEdit = source !== null

  const [type, setType] = useState<"provider" | "lua" | "manual">("provider")
  const [providerKey, setProviderKey] = useState<string>("cbr")
  const [name, setName] = useState<string>("")
  const [apiKey, setApiKey] = useState<string>("")
  const [luaSlug, setLuaSlug] = useState<string>("")
  const [enabled, setEnabled] = useState<boolean>(true)
  const [manualRates, setManualRates] = useState<RateEntry[]>([])
  const [testResult, setTestResult] = useState<FxTestResult | null>(null)
  const [isTesting, setIsTesting] = useState(false)
  const [isSaving, setIsSaving] = useState(false)

  const handleOpenReset = () => {
    setType(source?.type || "provider")
    setProviderKey(source?.provider || "cbr")
    setName(source?.name || "")
    setApiKey("")
    setLuaSlug(source?.lua_slug || "")
    setEnabled(source?.enabled ?? true)
    setTestResult(null)
    setIsSaving(false)

    const rawRates = source?.rates || source?.last_rates
    if (source?.type === "manual" && rawRates && Object.keys(rawRates).length > 0) {
      setManualRates(Object.entries(rawRates).map(([code, rate]) => ({ code, rate: String(rate) })))
    } else {
      setManualRates([
        { code: "USD", rate: "95.00" },
        { code: "EUR", rate: "103.00" },
      ])
    }
  }

  const runTest = async () => {
    setIsTesting(true)
    setTestResult(null)
    try {
      const ratesMap: Record<string, string> = {}
      for (const r of manualRates) {
        if (r.code.trim() && r.rate.trim()) {
          ratesMap[r.code.trim().toUpperCase()] = r.rate.trim()
        }
      }

      const payload = {
        source: {
          id: source?.id,
          type,
          provider: type === "provider" ? providerKey : undefined,
          api_key: type === "provider" && apiKey.trim() ? apiKey.trim() : undefined,
          lua_slug: type === "lua" ? luaSlug.trim() : undefined,
          rates: type === "manual" ? ratesMap : undefined,
        },
      }
      const res = (await api.post<FxTestResult>("/v1/admin/settings/fx/test-source", payload)).data
      setTestResult(res)
    } catch (err) {
      setTestResult({
        ok: false,
        base: baseCurrency,
        rates: {},
        total: 0,
        error: getErrorDetail(err) || "Ошибка при проверке источника",
      })
    } finally {
      setIsTesting(false)
    }
  }

  const handleSave = async () => {
    setIsSaving(true)
    try {
      let defaultName: string
      if (type === "provider") {
        const p = providers?.find((item) => item.key === providerKey)
        defaultName = p?.title || providerKey
      } else if (type === "lua") {
        defaultName = `Lua: ${luaSlug || "скрипт"}`
      } else {
        defaultName = "Ручные курсы"
      }

      const ratesMap: Record<string, string> = {}
      if (type === "manual") {
        for (const r of manualRates) {
          if (r.code.trim() && r.rate.trim()) {
            ratesMap[r.code.trim().toUpperCase()] = r.rate.trim()
          }
        }
      }

      await onSave({
        id: source?.id,
        type,
        name: name.trim() || defaultName,
        provider: type === "provider" ? providerKey : undefined,
        api_key: type === "provider" && apiKey.trim() ? apiKey.trim() : undefined,
        lua_slug: type === "lua" ? luaSlug.trim() : undefined,
        rates: type === "manual" ? ratesMap : undefined,
        enabled,
      })

      onOpenChange(false)
    } finally {
      setIsSaving(false)
    }
  }

  const addRateRow = (code = "", rate = "") => {
    setManualRates((prev) => [...prev, { code, rate }])
  }

  const updateRateRow = (index: number, key: "code" | "rate", val: string) => {
    setManualRates((prev) => {
      const next = [...prev]
      next[index] = { ...next[index], [key]: key === "code" ? val.toUpperCase() : val }
      return next
    })
  }

  const removeRateRow = (index: number) => {
    setManualRates((prev) => prev.filter((_, i) => i !== index))
  }

  const selectedProvider = providers?.find((p) => p.key === providerKey)

  const tabs: TabDefinition[] = [
    {
      id: "general",
      title: "Параметры",
      label: "Параметры",
      icon: Sliders,
      content: (
        <div className="space-y-4 py-1 text-xs">
          <div className="space-y-1.5">
            <Label className="text-xs">Тип источника</Label>
            <Select
              value={type}
              onValueChange={(v) => {
                setType(v as "provider" | "lua" | "manual")
                setTestResult(null)
              }}
            >
              <SelectTrigger className="text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="provider">Готовый провайдер (API)</SelectItem>
                <SelectItem value="manual">Ручные курсы (Manual)</SelectItem>
                <SelectItem value="lua">Lua-скрипт</SelectItem>
              </SelectContent>
            </Select>
            <p className="text-[11px] text-muted-foreground">
              {type === "provider" && "Курсы автоматически запрашиваются через внешний HTTP API."}
              {type === "manual" && "Фиксированные курсы, заданные вручную для этого источника."}
              {type === "lua" && "Курсы вычисляются или загружаются пользовательским Lua-скриптом."}
            </p>
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">Название источника</Label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={type === "provider" ? (selectedProvider?.title || "ЦБ РФ") : "Например: Фиксированные курсы USDT"}
              className="text-xs"
            />
          </div>

          {type === "provider" && (
            <div className="space-y-3 rounded-lg border p-3 bg-muted/20">
              <div className="space-y-1.5">
                <Label className="text-xs">Провайдер API</Label>
                <Select value={providerKey} onValueChange={(v) => setProviderKey(v || "cbr")}>
                  <SelectTrigger className="text-xs bg-background">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {providers?.map((p) => (
                      <SelectItem key={p.key} value={p.key} className="text-xs">
                        {p.title} {p.needs_key ? "(нужен ключ)" : ""}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {selectedProvider?.note && (
                  <p className="text-[11px] text-muted-foreground">{selectedProvider.note}</p>
                )}
              </div>

              {selectedProvider?.needs_key && (
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <Label className="text-xs">API-ключ</Label>
                    {isEdit && source?.has_api_key && (
                      <span className="text-[10px] text-emerald-500 font-medium">
                        Ключ сохранён и зашифрован
                      </span>
                    )}
                  </div>
                  <Input
                    type="password"
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder={isEdit && source?.has_api_key ? "Оставьте пустым, чтобы не менять" : "Введите API-ключ"}
                    className="font-mono text-xs bg-background"
                  />
                  {selectedProvider.signup_url && (
                    <a
                      href={selectedProvider.signup_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-[11px] text-primary hover:underline inline-flex items-center gap-1"
                    >
                      Получить ключ на сайте провайдера <ExternalLink className="size-3" />
                    </a>
                  )}
                </div>
              )}
            </div>
          )}

          {type === "lua" && (
            <div className="space-y-1.5 rounded-lg border p-3 bg-muted/20">
              <Label className="text-xs">Lua-скрипт источника курсов</Label>
              <LuaScriptSelect
                value={luaSlug}
                onChange={setLuaSlug}
                valueField="slug"
                placeholder="Выберите Lua-скрипт курсов…"
              />
              <p className="text-[11px] text-muted-foreground">
                Скрипт должен возвращать курсы в объекте <code className="font-mono font-bold">public.rates</code>.
              </p>
            </div>
          )}

          <div className="flex items-center justify-between rounded-lg border p-3">
            <div className="space-y-0.5">
              <Label className="text-xs">Активен</Label>
              <p className="text-[11px] text-muted-foreground">
                Включить источник в цепочку опроса приоритетов
              </p>
            </div>
            <Switch checked={enabled} onCheckedChange={setEnabled} />
          </div>
        </div>
      ),
    },
  ]

  if (type === "manual") {
    tabs.push({
      id: "rates",
      title: "Курсы валют",
      label: "Курсы валют",
      icon: Coins,
      badge: `${manualRates.filter((r) => r.code.trim() && r.rate.trim()).length}`,
      content: (
        <div className="space-y-3 py-1 text-xs">
          <div className="space-y-1">
            <h4 className="font-medium text-xs">Таблица фиксированных курсов</h4>
            <p className="text-[11px] text-muted-foreground">
              Укажите, сколько базовой валюты (<strong>{baseCurrency}</strong>) стоит одна единица
              каждой валюты. Например, для USD при курсе 1 USD = 95.50 {baseCurrency} введите 95.50.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-1.5 pt-1">
            <span className="text-[11px] text-muted-foreground mr-1">Быстро добавить:</span>
            {COMMON_CURRENCY_CODES.map((code) => {
              const alreadyHas = manualRates.some((r) => r.code.toUpperCase() === code)
              if (alreadyHas || code === baseCurrency) return null
              return (
                <Button
                  key={code}
                  size="xs"
                  variant="outline"
                  className="h-6 text-[10px] font-mono"
                  onClick={() => addRateRow(code, "")}
                >
                  +{code}
                </Button>
              )
            })}
          </div>

          <div className="rounded-lg border overflow-hidden max-h-60 overflow-y-auto">
            <Table>
              <TableHeader>
                <TableRow className="h-8">
                  <TableHead className="w-48 text-[11px]">Валюта</TableHead>
                  <TableHead className="text-[11px]">Курс к 1 {baseCurrency}</TableHead>
                  <TableHead className="w-12"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {manualRates.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={3} className="text-center py-4 text-muted-foreground text-[11px]">
                      Курсы не добавлены. Нажмите «Добавить валюту» ниже.
                    </TableCell>
                  </TableRow>
                ) : (
                  manualRates.map((r, i) => (
                    <TableRow key={i} className="h-10">
                      <TableCell className="p-1.5 pl-3">
                        <div className="w-44">
                          <CurrencySelect
                            value={r.code}
                            onChange={(code) => updateRateRow(i, "code", code)}
                            placeholder="Валюта"
                          />
                        </div>
                      </TableCell>
                      <TableCell className="p-1.5">
                        <div className="flex items-center gap-1.5">
                          <Input
                            value={r.rate}
                            onChange={(e) => updateRateRow(i, "rate", e.target.value)}
                            placeholder="95.50"
                            className="font-mono text-xs h-8 max-w-xs"
                          />
                          <span className="text-[11px] text-muted-foreground shrink-0">
                            {baseCurrency}
                          </span>
                        </div>
                      </TableCell>
                      <TableCell className="p-1.5 text-right pr-3">
                        <Button
                          size="icon"
                          variant="ghost"
                          className="size-8 text-destructive hover:text-destructive hover:bg-destructive/10"
                          onClick={() => removeRateRow(i)}
                        >
                          <Trash2 className="size-3.5" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>

          <Button
            size="sm"
            variant="outline"
            className="w-full text-xs h-8 gap-1.5"
            onClick={() => addRateRow("", "")}
          >
            <Plus className="size-3.5" /> Добавить валюту
          </Button>
        </div>
      ),
    })
  } else if (type === "provider") {
    tabs.push({
      id: "reference",
      title: "Справка по API",
      label: "Справка по API",
      icon: BookOpen,
      content: <ProvidersReference providers={providers || []} />,
    })
  }

  tabs.push({
    id: "test",
    title: "Проверка",
    label: "Проверка",
    icon: Play,
    content: (
      <div className="space-y-3 py-1 text-xs">
        <p className="text-muted-foreground text-[11px]">
          Тестовый запрос в реальном времени с текущими параметрами без сохранения в базу данных.
        </p>

        <Button
          size="sm"
          onClick={runTest}
          disabled={isTesting}
          className="w-full"
        >
          {isTesting && <Loader2 className="mr-2 size-4 animate-spin" />}
          {testResult ? "Повторить проверку" : "Выполнить тестовый запрос"}
        </Button>

        {testResult && (
          <div className="rounded-md border p-3 text-xs space-y-2 mt-2">
            {testResult.ok ? (
              <>
                <p className="flex items-center gap-1.5 font-medium text-emerald-500">
                  <CheckCircle2 className="size-4 shrink-0" />
                  Курсы получены: {testResult.total} (к базовой валюте {testResult.base})
                </p>
                <div className="mt-2 grid max-h-48 overflow-y-auto grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-3">
                  {Object.entries(testResult.rates).map(([code, rate]) => (
                    <div key={code} className="flex justify-between gap-1 font-mono text-[11px]">
                      <span className="text-muted-foreground">{code}:</span>
                      <span className="font-semibold">{Number(rate).toFixed(4)}</span>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <p className="flex items-start gap-1.5 text-destructive">
                <XCircle className="mt-0.5 size-4 shrink-0" />
                <span>{testResult.error}</span>
              </p>
            )}
          </div>
        )}
      </div>
    ),
  })

  return (
    <TabbedDialog
      open={open}
      onOpenChange={(v) => {
        if (v) handleOpenReset()
        onOpenChange(v)
      }}
      title={isEdit ? `Источник «${source.name || source.id}»` : "Новый источник курсов"}
      description="Настройка приоритета и параметров получения курсов валют"
      tabs={tabs}
      primaryAction={{
        label: isEdit ? "Сохранить изменения" : "Добавить источник",
        onClick: handleSave,
        disabled: isSaving,
        loading: isSaving,
      }}
      secondaryAction={{
        label: "Отмена",
        onClick: () => onOpenChange(false),
      }}
    />
  )
}

export function CurrencySettings() {
  const qc = useQueryClient()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingSource, setEditingSource] = useState<FxSourceItem | null>(null)
  const [currenciesModalOpen, setCurrenciesModalOpen] = useState(false)
  const [search, setSearch] = useState("")
  const [typeFilter, setTypeFilter] = useState<string>("all")

  // Drag and Drop reordering state
  const [draggedIdx, setDraggedIdx] = useState<number | null>(null)
  const [dragOverIdx, setDragOverIdx] = useState<number | null>(null)

  const { data: status } = useQuery({
    queryKey: ["admin-currency-status"],
    queryFn: async () => (await api.get<CurrencyStatus>("/v1/admin/settings/fx/currency-status")).data,
    staleTime: 10_000,
  })

  const { data: providers } = useQuery({
    queryKey: ["fx-providers"],
    queryFn: async () => (await api.get<FxProvider[]>("/v1/admin/settings/fx/providers")).data,
    staleTime: 10 * 60_000,
  })

  const { data: sources, isLoading: sourcesLoading } = useQuery({
    queryKey: ["admin-fx-sources"],
    queryFn: async () => (await api.get<FxSourceItem[]>("/v1/admin/settings/fx/sources")).data,
  })

  const { data: health } = useQuery({
    queryKey: ["admin-fx-health"],
    queryFn: async () => (await api.get<FxHealth>("/v1/admin/settings/fx/health")).data,
    refetchInterval: 15_000,
  })

  const { data: ratesOverview, refetch: refetchOverview, isFetching: isFetchingOverview } = useQuery({
    queryKey: ["admin-fx-rates-overview"],
    queryFn: async () => (await api.get<RateOverviewItem[]>("/v1/admin/settings/fx/rates-overview")).data,
    staleTime: 20_000,
  })

  const createSource = useMutation({
    mutationFn: async (input: {
      type: "provider" | "lua" | "manual"
      name: string
      provider?: string
      api_key?: string
      lua_slug?: string
      rates?: Record<string, string>
      enabled: boolean
    }) => {
      return (await api.post<FxSourceItem>("/v1/admin/settings/fx/sources", input)).data
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["admin-fx-sources"] })
      void qc.invalidateQueries({ queryKey: ["admin-fx-available-currencies"] })
      void qc.invalidateQueries({ queryKey: ["admin-fx-rates-overview"] })
      void qc.invalidateQueries({ queryKey: ["admin-fx-health"] })
      toastSuccess("Источник добавлен и опрошен")
    },
    onError: (err) => toastError("Ошибка добавления источника", getErrorDetail(err)),
  })

  const updateSource = useMutation({
    mutationFn: async ({
      id,
      data,
    }: {
      id: number
      data: {
        name?: string
        enabled?: boolean
        provider?: string
        api_key?: string
        lua_slug?: string
        rates?: Record<string, string>
      }
    }) => {
      return (await api.patch<FxSourceItem>(`/v1/admin/settings/fx/sources/${id}`, data)).data
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["admin-fx-sources"] })
      void qc.invalidateQueries({ queryKey: ["admin-fx-available-currencies"] })
      void qc.invalidateQueries({ queryKey: ["admin-fx-rates-overview"] })
      void qc.invalidateQueries({ queryKey: ["admin-fx-health"] })
      toastSuccess("Источник обновлён и опрошен")
    },
    onError: (err) => toastError("Ошибка обновления источника", getErrorDetail(err)),
  })

  const deleteSource = useMutation({
    mutationFn: async (id: number) => {
      await api.delete(`/v1/admin/settings/fx/sources/${id}`)
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["admin-fx-sources"] })
      void qc.invalidateQueries({ queryKey: ["admin-fx-available-currencies"] })
      void qc.invalidateQueries({ queryKey: ["admin-fx-rates-overview"] })
      void qc.invalidateQueries({ queryKey: ["admin-fx-health"] })
      toastSuccess("Источник удалён")
    },
    onError: (err) => toastError("Ошибка удаления источника", getErrorDetail(err)),
  })

  const refreshSource = useMutation({
    mutationFn: async (id: number) => {
      return (await api.post<FxSourceItem>(`/v1/admin/settings/fx/sources/${id}/refresh`)).data
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["admin-fx-sources"] })
      void qc.invalidateQueries({ queryKey: ["admin-fx-rates-overview"] })
      void qc.invalidateQueries({ queryKey: ["admin-fx-health"] })
      toastSuccess("Курсы источника обновлены")
    },
    onError: (err) => toastError("Не удалось обновить источник", getErrorDetail(err)),
  })

  const refreshAll = useMutation({
    mutationFn: async () => {
      return (await api.post<FxSourceItem[]>("/v1/admin/settings/fx/sources/refresh-all")).data
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["admin-fx-sources"] })
      void qc.invalidateQueries({ queryKey: ["admin-fx-rates-overview"] })
      void qc.invalidateQueries({ queryKey: ["admin-fx-health"] })
      toastSuccess("Все источники курсов обновлены")
    },
    onError: (err) => toastError("Ошибка обновления источников", getErrorDetail(err)),
  })

  const reorderSources = useMutation({
    mutationFn: async (ids: number[]) => {
      return (await api.put<FxSourceItem[]>("/v1/admin/settings/fx/sources/reorder", { ids })).data
    },
    onSuccess: (saved) => {
      qc.setQueryData(["admin-fx-sources"], saved)
      void qc.invalidateQueries({ queryKey: ["admin-fx-rates-overview"] })
      toastSuccess("Порядок приоритетов обновлён")
    },
    onError: (err) => toastError("Ошибка сохранения приоритетов", getErrorDetail(err)),
  })

  const isLocked = status ? !status.can_change : false
  const baseCurrency = status?.currency || "RUB"

  const filteredSources = useMemo(() => {
    if (!sources) return []
    return sources.filter((s) => {
      if (typeFilter !== "all" && s.type !== typeFilter) return false
      if (!search.trim()) return true
      const q = search.toLowerCase()
      const matchName = (s.name || "").toLowerCase().includes(q)
      const matchProv = (s.provider || "").toLowerCase().includes(q)
      const matchSlug = (s.lua_slug || "").toLowerCase().includes(q)
      const rawRates = s.rates || s.last_rates
      const matchRates = rawRates ? Object.keys(rawRates).some((c) => c.toLowerCase().includes(q)) : false
      return matchName || matchProv || matchSlug || matchRates
    })
  }, [sources, search, typeFilter])

  // Animated Drag & Drop
  const handleDragStart = (e: React.DragEvent, index: number) => {
    setDraggedIdx(index)
    e.dataTransfer.effectAllowed = "move"
  }

  const handleDragOver = (e: React.DragEvent, index: number) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = "move"
    if (dragOverIdx !== index) {
      setDragOverIdx(index)
    }
  }

  const handleDrop = (e: React.DragEvent, targetIdx: number) => {
    e.preventDefault()
    if (draggedIdx === null || draggedIdx === targetIdx || !sources) {
      setDraggedIdx(null)
      setDragOverIdx(null)
      return
    }
    const next = [...sources]
    const [moved] = next.splice(draggedIdx, 1)
    next.splice(targetIdx, 0, moved)
    setDraggedIdx(null)
    setDragOverIdx(null)
    reorderSources.mutate(next.map((s) => s.id))
  }

  const handleDragEnd = () => {
    setDraggedIdx(null)
    setDragOverIdx(null)
  }

  const moveItem = (fromIdx: number, toIdx: number) => {
    if (!sources || toIdx < 0 || toIdx >= sources.length) return
    const next = [...sources]
    const [moved] = next.splice(fromIdx, 1)
    next.splice(toIdx, 0, moved)
    reorderSources.mutate(next.map((s) => s.id))
  }

  const toggleEnabled = (src: FxSourceItem) => {
    updateSource.mutate({ id: src.id, data: { enabled: !src.enabled } })
  }

  const handleSaveSource = async (data: {
    id?: number
    type: "provider" | "lua" | "manual"
    name: string
    provider?: string
    api_key?: string
    lua_slug?: string
    rates?: Record<string, string>
    enabled: boolean
  }) => {
    if (data.id) {
      await updateSource.mutateAsync({ id: data.id, data })
    } else {
      await createSource.mutateAsync(data)
    }
  }

  // Currencies to show in the compact preview
  const previewRates = useMemo(() => {
    if (!ratesOverview) return []
    return ratesOverview.filter((r) => r.currency !== baseCurrency).slice(0, 8)
  }, [ratesOverview, baseCurrency])

  const totalCurrenciesCount = (ratesOverview?.length ?? 1) - 1

  return (
    <div className="w-full space-y-6">
      {isLocked && (
        <div className="flex items-start gap-3 rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-xs text-amber-600 dark:text-amber-400">
          <Lock className="size-4 shrink-0 mt-0.5 text-amber-500" />
          <div className="space-y-1">
            <p className="font-semibold text-sm">Смена валюты инстанса заблокирована</p>
            <p className="text-muted-foreground leading-relaxed">{status?.reason}</p>
          </div>
        </div>
      )}

      {/* Верхний блок: Базовая валюта (слева) + Мониторинг и статус (справа) — одинаковая высота */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-stretch">
        {/* Базовая валюта */}
        <SettingsSection
          title="Базовая валюта"
          description="Балансы аккаунтов ведутся только в ней. Платежи в других валютах конвертируются при создании с фиксацией курса."
          className="h-full mb-0 flex flex-col"
          fields={[
            {
              key: "billing.currency",
              label: "Валюта инстанса",
              kind: "currency",
              placeholder: "RUB",
              disabled: isLocked,
              hint: isLocked
                ? "Заблокировано: на балансах пользователей есть средства. Сначала обнулите их."
                : "Не меняйте на работающем инстансе без переноса данных: уже начисленные балансы не пересчитываются.",
            },
            {
              key: "billing.fx.markup_percent",
              label: "Спред",
              kind: "number",
              suffix: "%",
              placeholder: "0",
              hint: "На столько уменьшается зачисляемая сумма при конвертации. 0 — по курсу без наценки.",
            },
            {
              key: "billing.fx.fail_open",
              label: "Fail-open (резерв курсов из БД)",
              kind: "switch",
              hint: "Если источник курсов недоступен из-за сбоя сети или API, использовать последние сохранённые в БД курсы вместо прерывания создания платежа.",
            },
          ]}
        />

        {/* Сводка и статус валютной подсистемы */}
        <Card className="h-full flex flex-col">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base font-medium">Статус подсистемы курсов</CardTitle>
              {health?.has_errors ? (
                <Badge variant="destructive" className="gap-1 text-[10px]">
                  <ShieldAlert className="size-3" /> Ошибки в источниках ({health.count})
                </Badge>
              ) : (
                <Badge variant="outline" className="gap-1 text-[10px] text-emerald-500 border-emerald-500/30">
                  <ShieldCheck className="size-3" /> Источники в норме
                </Badge>
              )}
            </div>
            <CardDescription className="text-xs">
              Мониторинг конвертации, состояние цепочки приоритетов и резервирование (Fail-Open)
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 text-xs">
            {health?.has_errors && (
              <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 space-y-1.5 text-destructive">
                <div className="flex items-center gap-1.5 font-medium">
                  <AlertCircle className="size-4 shrink-0" />
                  <span>Внимание: Обнаружены проблемы обновления курсов</span>
                </div>
                <div className="text-[11px] space-y-1 pl-5">
                  {health.errors.map((err) => (
                    <div key={err.id} className="truncate">
                      <strong>{err.name || `Источник #${err.id}`}:</strong> {err.error}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Доступные валюты и их текущие котировки */}
            <div className="rounded-lg border bg-muted/20 p-3 space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-medium text-xs">
                  Текущие котировки (к 1 {baseCurrency}):
                </span>
                <Button
                  size="icon"
                  variant="ghost"
                  className="size-6"
                  onClick={() => void refetchOverview()}
                  title="Обновить курсы прямо сейчас"
                  disabled={isFetchingOverview}
                >
                  <RefreshCw className={`size-3 ${isFetchingOverview ? "animate-spin" : ""}`} />
                </Button>
              </div>

              <div className="flex flex-wrap items-center gap-1.5">
                <Badge variant="default" className="font-mono text-[10px]">
                  {baseCurrency} (базовая)
                </Badge>

                {previewRates.map((r) => (
                  <Badge
                    key={r.currency}
                    variant="secondary"
                    className="font-mono text-[10px] py-0.5"
                    title={`1 ${r.currency} = ${r.rate_to_base} ${baseCurrency} (источник: ${r.source_name})`}
                  >
                    {r.currency}: {r.rate_to_base}
                  </Badge>
                ))}

                {totalCurrenciesCount > previewRates.length && (
                  <Button
                    size="xs"
                    variant="outline"
                    className="h-5 text-[10px] px-2 font-medium text-primary hover:underline"
                    onClick={() => setCurrenciesModalOpen(true)}
                  >
                    +{totalCurrenciesCount - previewRates.length} ещё… (все курсы)
                  </Button>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Полноценная таблица источников курсов без обёртки Card (стиль как в пользователях / заказах) */}
      <div className="space-y-3">
        {/* Заголовок таблицы и кнопка добавления */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold">Источники курсов валют</h2>
            <p className="text-xs text-muted-foreground">
              Биллинг опрашивает источники строго по цепочке приоритетов сверху вниз. Нажмите на строку для редактирования
              или перетаскивайте строки для настройки приоритета.
            </p>
          </div>
          <Button
            size="sm"
            onClick={() => {
              setEditingSource(null)
              setDialogOpen(true)
            }}
            className="shrink-0 gap-1.5"
          >
            <Plus className="size-4" /> Добавить источник
          </Button>
        </div>

        {/* Панель инструментов: поиск и фильтрация */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="relative w-full sm:w-72">
            <Search className="absolute left-2.5 top-2.5 size-3.5 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Поиск по названию, валюте..."
              className="pl-8 text-xs h-8"
            />
          </div>

          <div className="flex items-center gap-2 w-full sm:w-auto">
            <Select value={typeFilter} onValueChange={(v) => setTypeFilter(v || "all")}>
              <SelectTrigger className="text-xs h-8 w-44">
                <SelectValue placeholder="Все типы" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Все типы источников</SelectItem>
                <SelectItem value="provider">API-провайдеры</SelectItem>
                <SelectItem value="manual">Ручные курсы (Manual)</SelectItem>
                <SelectItem value="lua">Lua-скрипты</SelectItem>
              </SelectContent>
            </Select>

            <Button
              variant="outline"
              size="sm"
              className="h-8 text-xs gap-1.5"
              onClick={() => refreshAll.mutate()}
              disabled={refreshAll.isPending}
            >
              <RefreshCw className={`size-3.5 ${refreshAll.isPending ? "animate-spin" : ""}`} />
              <span className="hidden sm:inline">Обновить все</span>
            </Button>
          </div>
        </div>

        {/* Таблица на всю ширину с плавной анимацией перемещения строк */}
        <div className="rounded-lg border overflow-x-auto bg-card">
          <Table>
            <TableHeader>
              <TableRow className="h-9 hover:bg-transparent">
                <TableHead className="w-20 text-[11px]">Приоритет</TableHead>
                <TableHead className="min-w-[180px] text-[11px]">Источник</TableHead>
                <TableHead className="w-32 text-[11px]">Тип</TableHead>
                <TableHead className="min-w-[200px] text-[11px]">Конфигурация</TableHead>
                <TableHead className="min-w-[180px] text-[11px]">Статус и курсы</TableHead>
                <TableHead className="w-20 text-center text-[11px]">Активен</TableHead>
                <TableHead className="w-28 text-right pr-4 text-[11px]">Действия</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sourcesLoading && (
                <TableRow>
                  <TableCell colSpan={7} className="py-8 text-center text-xs text-muted-foreground">
                    Загрузка источников…
                  </TableCell>
                </TableRow>
              )}

              {!sourcesLoading && filteredSources.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} className="py-12 text-center text-xs text-muted-foreground">
                    {sources?.length === 0
                      ? "Источники курсов пока не добавлены. Нажмите «Добавить источник»."
                      : "Ничего не найдено по текущему запросу."}
                  </TableCell>
                </TableRow>
              )}

              {!sourcesLoading &&
                filteredSources.map((src, idx) => {
                  const isBeingDragged = draggedIdx === idx
                  const isOver = dragOverIdx === idx && draggedIdx !== idx
                  const ratesObj = (src.rates && Object.keys(src.rates).length > 0) ? src.rates : src.last_rates

                  return (
                    <TableRow
                      key={src.id}
                      draggable
                      onDragStart={(e) => handleDragStart(e, idx)}
                      onDragOver={(e) => handleDragOver(e, idx)}
                      onDrop={(e) => handleDrop(e, idx)}
                      onDragEnd={handleDragEnd}
                      onClick={() => {
                        setEditingSource(src)
                        setDialogOpen(true)
                      }}
                      className={`cursor-pointer transition-all duration-150 ${
                        isBeingDragged
                          ? "opacity-40 scale-[0.99] bg-accent/50"
                          : isOver
                          ? "border-t-2 border-t-primary bg-primary/5"
                          : "hover:bg-muted/40"
                      }`}
                    >
                      {/* Приоритет */}
                      <TableCell className="py-2.5 pl-4" onClick={(e) => e.stopPropagation()}>
                        <div className="flex items-center gap-1.5">
                          <button
                            type="button"
                            className="cursor-grab active:cursor-grabbing text-muted-foreground hover:text-foreground p-0.5"
                            title="Перетащите для изменения приоритета"
                          >
                            <GripVertical className="size-3.5" />
                          </button>
                          <div className="flex flex-col items-center">
                            <span className="text-[11px] font-mono font-bold">#{idx + 1}</span>
                            {idx === 0 && (
                              <span className="text-[9px] text-amber-500 font-bold uppercase leading-none">
                                Top
                              </span>
                            )}
                          </div>
                        </div>
                      </TableCell>

                      {/* Источник */}
                      <TableCell className="py-2.5">
                        <div className="space-y-0.5">
                          <span className="font-medium text-xs text-foreground block truncate">
                            {src.name || src.id}
                          </span>
                          {src.last_error && (
                            <div
                              className="inline-flex items-center gap-1 text-destructive bg-destructive/10 border border-destructive/20 rounded px-1.5 py-0.2 text-[10px]"
                              title={`Ошибка (${src.last_error_at ? new Date(src.last_error_at).toLocaleString() : ""}):\n${src.last_error}`}
                            >
                              <AlertCircle className="size-3 shrink-0 text-destructive animate-pulse" />
                              <span className="font-medium max-w-[180px] truncate">
                                {src.last_error}
                              </span>
                            </div>
                          )}
                        </div>
                      </TableCell>

                      {/* Тип */}
                      <TableCell className="py-2.5">
                        {src.type === "provider" && (
                          <Badge variant="outline" className="text-[10px]">
                            Провайдер API
                          </Badge>
                        )}
                        {src.type === "manual" && (
                          <Badge variant="outline" className="text-[10px] text-primary border-primary/30">
                            Ручные курсы
                          </Badge>
                        )}
                        {src.type === "lua" && (
                          <Badge variant="secondary" className="text-[10px]">
                            Lua-скрипт
                          </Badge>
                        )}
                      </TableCell>

                      {/* Конфигурация */}
                      <TableCell className="py-2.5 text-xs text-muted-foreground">
                        {src.type === "provider" && (
                          <div className="space-y-0.5">
                            <span className="font-mono text-[11px] text-foreground font-medium">
                              {src.provider || "API"}
                            </span>
                            <p className="text-[10px]">
                              {src.has_api_key || src.api_key ? "Ключ: ••• (зашифрован)" : "Без ключа"}
                            </p>
                          </div>
                        )}
                        {src.type === "manual" && (
                          <div className="flex flex-wrap gap-1 max-w-xs">
                            {ratesObj && Object.keys(ratesObj).length > 0 ? (
                              Object.entries(ratesObj).slice(0, 4).map(([code, rate]) => (
                                <Badge key={code} variant="secondary" className="font-mono text-[10px] py-0 px-1">
                                  {code}: {String(rate)}
                                </Badge>
                              ))
                            ) : (
                              <span className="text-[11px] italic">Курсы не настроены</span>
                            )}
                            {ratesObj && Object.keys(ratesObj).length > 4 && (
                              <span className="text-[10px] text-muted-foreground">
                                +{Object.keys(ratesObj).length - 4} ещё
                              </span>
                            )}
                          </div>
                        )}
                        {src.type === "lua" && (
                          <span className="font-mono text-[11px] text-foreground">
                            slug: {src.lua_slug}
                          </span>
                        )}
                      </TableCell>

                      {/* Статус и курсы */}
                      <TableCell className="py-2.5 text-xs">
                        {src.last_fetched_at && !src.last_error && (
                          <div className="space-y-0.5">
                            <span className="text-[11px] text-emerald-600 dark:text-emerald-400 font-medium">
                              Актуален ({src.last_rates_count} валют)
                            </span>
                            <p className="text-[10px] text-muted-foreground">
                              {new Date(src.last_fetched_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                            </p>
                          </div>
                        )}
                        {src.type === "manual" && !src.last_fetched_at && (
                          <span className="text-[11px] text-muted-foreground font-mono">
                            {Object.keys(ratesObj || {}).length} валют
                          </span>
                        )}
                        {!src.last_fetched_at && src.type !== "manual" && !src.last_error && (
                          <span className="text-[11px] text-muted-foreground">Ожидает первого опроса</span>
                        )}
                      </TableCell>

                      {/* Активен */}
                      <TableCell className="py-2.5 text-center" onClick={(e) => e.stopPropagation()}>
                        <Switch
                          checked={src.enabled}
                          onCheckedChange={() => toggleEnabled(src)}
                          title={src.enabled ? "Включен" : "Отключен"}
                        />
                      </TableCell>

                      {/* Действия */}
                      <TableCell className="py-2.5 text-right pr-4" onClick={(e) => e.stopPropagation()}>
                        <div className="flex items-center justify-end gap-1">
                          <div className="flex flex-col gap-0.5 mr-1">
                            <Button
                              size="icon"
                              variant="ghost"
                              className="size-5 h-4"
                              disabled={idx === 0}
                              onClick={() => moveItem(idx, idx - 1)}
                              title="Поднять приоритет"
                            >
                              <ArrowUp className="size-3" />
                            </Button>
                            <Button
                              size="icon"
                              variant="ghost"
                              className="size-5 h-4"
                              disabled={idx === sources!.length - 1}
                              onClick={() => moveItem(idx, idx + 1)}
                              title="Понизить приоритет"
                            >
                              <ArrowDown className="size-3" />
                            </Button>
                          </div>

                          <Button
                            size="icon"
                            variant="ghost"
                            className="size-7"
                            onClick={() => refreshSource.mutate(src.id)}
                            title="Принудительно обновить курсы"
                            disabled={refreshSource.isPending}
                          >
                            <RefreshCw className="size-3.5" />
                          </Button>

                          <Button
                            size="sm"
                            variant="outline"
                            className="h-7 text-xs px-2"
                            onClick={() => {
                              setEditingSource(src)
                              setDialogOpen(true)
                            }}
                          >
                            Изменить
                          </Button>

                          <Button
                            size="icon"
                            variant="ghost"
                            className="size-7 text-destructive hover:text-destructive hover:bg-destructive/10"
                            onClick={() => deleteSource.mutate(src.id)}
                            title="Удалить источник"
                          >
                            <Trash2 className="size-3.5" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  )
                })}
            </TableBody>
          </Table>
        </div>
      </div>

      {/* Табированный диалог создания / редактирования источника */}
      <SourceDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        source={editingSource}
        providers={providers}
        baseCurrency={baseCurrency}
        onSave={handleSaveSource}
      />

      {/* Диалог со всеми валютами и котировками */}
      <AllCurrenciesModal
        open={currenciesModalOpen}
        onOpenChange={setCurrenciesModalOpen}
        items={ratesOverview}
        baseCurrency={baseCurrency}
      />
    </div>
  )
}
