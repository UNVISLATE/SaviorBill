import { useEffect, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useSearchParams } from "react-router-dom"
import {
  AlertTriangle,
  CheckCircle2,
  Eye,
  EyeOff,
  FileUp,
  KeyRound,
  Package,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  XCircle,
} from "lucide-react"

import { api } from "@/api/api.ts"
import { getErrorDetail } from "@/lib/api-error.ts"
import { useAuth } from "@/hooks/use-auth"
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
import { Textarea } from "@/components/shadsnui/textarea"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/shadsnui/tabs"
import { toastError, toastSuccess } from "@/lib/toast"

interface ServiceStockItem {
  service_id: number
  service_name: string
  service_slug: string
  catalog_id: number | null
  catalog_name: string | null
  price: string
  currency: string
  is_active: boolean
  available_keys: number
  used_keys: number
  total_keys: number
  stock_status: "ok" | "low" | "out_of_stock"
}

interface ServiceKeysOverview {
  total_available: number
  total_used: number
  total_keys: number
  out_of_stock_count: number
  low_stock_count: number
  threshold?: number
  items: ServiceStockItem[]
}

interface ServiceKeyItem {
  id: number
  service_id: number
  service_name: string | null
  service_slug: string | null
  is_used: boolean
  used_at: string | null
  order_id: number | null
  created_at: string
  value: string
}

interface KeysPageResponse {
  items: ServiceKeyItem[]
  total: number
  limit: number
  offset: number
  has_more: boolean
}

function ImportKeysModal({
  open,
  onOpenChange,
  defaultServiceId,
  services,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  defaultServiceId?: number
  services: ServiceStockItem[]
}) {
  const [selectedServiceId, setSelectedServiceId] = useState<string>(
    defaultServiceId ? String(defaultServiceId) : (services[0]?.service_id ? String(services[0].service_id) : "")
  )

  useEffect(() => {
    if (defaultServiceId) {
      setSelectedServiceId(String(defaultServiceId))
    } else if (services[0]?.service_id) {
      setSelectedServiceId((prev) => prev || String(services[0].service_id))
    }
  }, [defaultServiceId, services, open])

  const [text, setText] = useState("")
  const fileInputRef = useRef<HTMLInputElement>(null)
  const qc = useQueryClient()

  const keysCount = text.split("\n").map((s) => s.trim()).filter(Boolean).length

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      const content = await file.text()
      setText(content)
      toastSuccess(`Файл ${file.name} прочитан: найдено ${content.split("\n").filter(Boolean).length} строк`)
    } catch (err) {
      toastError("Ошибка чтения файла", String(err))
    }
    e.target.value = ""
  }

  const importMutation = useMutation({
    mutationFn: async () => {
      const values = text.split("\n").map((s) => s.trim()).filter(Boolean)
      return (
        await api.post("/v1/admin/service-keys/import", {
          service_id: Number(selectedServiceId),
          values,
        })
      ).data
    },
    onSuccess: (data: { added: number; skipped: number }) => {
      toastSuccess(`Импортировано: ${data.added}${data.skipped ? `, пропущено дублей: ${data.skipped}` : ""}`)
      setText("")
      onOpenChange(false)
      void qc.invalidateQueries({ queryKey: ["admin-service-keys-overview"] })
      void qc.invalidateQueries({ queryKey: ["admin-global-service-keys"] })
    },
    onError: (e) => toastError("Ошибка импорта ключей", getErrorDetail(e)),
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <KeyRound className="size-5 text-primary" /> Импорт ключей
          </DialogTitle>
          <DialogDescription>
            Добавление уникальных цифровых лицензий в пул выбранного товара.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label>Целевой товар / услуга</Label>
            <Select
              value={selectedServiceId}
              onValueChange={(val) => setSelectedServiceId(val ?? "")}
            >
              <SelectTrigger>
                <SelectValue placeholder="Выберите товар" />
              </SelectTrigger>
              <SelectContent>
                {services.map((s) => (
                  <SelectItem key={s.service_id} value={String(s.service_id)}>
                    {s.service_name} ({s.currency} {s.price})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label>Список ключей (по одному на строку)</Label>
              <span className="text-xs text-muted-foreground font-mono">
                Строк: {keysCount}
              </span>
            </div>
            <Textarea
              rows={8}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={"XXXXX-YYYYY-ZZZZZ\nAAAAA-BBBBB-CCCCC\n..."}
              className="font-mono text-xs"
            />
          </div>

          <div className="flex items-center gap-2">
            <input
              type="file"
              ref={fileInputRef}
              accept=".txt,.csv,text/plain,text/csv"
              className="hidden"
              onChange={handleFileUpload}
            />
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => fileInputRef.current?.click()}
            >
              <FileUp className="size-4" /> Загрузить файл (.txt, .csv)
            </Button>
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Отмена
          </Button>
          <Button
            disabled={!selectedServiceId || keysCount === 0 || importMutation.isPending}
            onClick={() => importMutation.mutate()}
          >
            {importMutation.isPending ? "Импорт…" : `Импортировать ${keysCount} ключей`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function ServiceKeysPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const { can } = useAuth()
  const canReveal = can("ownersec.servicekeys.read")
  const canCreate = can("services.keys.create")
  const canDelete = can("services.keys.delete")

  const qc = useQueryClient()
  const activeTab = searchParams.get("tab") || "overview"
  const serviceFilter = searchParams.get("service_id") || "all"
  const statusFilter = searchParams.get("status") || "all"
  const [searchQuery, setSearchQuery] = useState("")

  const [importModalOpen, setImportModalOpen] = useState(false)
  const [importTargetServiceId, setImportTargetServiceId] = useState<number | undefined>()
  const [revealed, setRevealed] = useState<Record<number, string>>({})

  // Запрос общей сводки по всем ключам
  const { data: overview, isLoading: isOverviewLoading, refetch: refetchOverview } = useQuery({
    queryKey: ["admin-service-keys-overview"],
    queryFn: async () => (await api.get<ServiceKeysOverview>("/v1/admin/service-keys/overview")).data,
  })

  const [editingThreshold, setEditingThreshold] = useState(false)
  const [tempThreshold, setTempThreshold] = useState("5")

  useEffect(() => {
    if (overview?.threshold) {
      setTempThreshold(String(overview.threshold))
    }
  }, [overview?.threshold])

  const updateThresholdMutation = useMutation({
    mutationFn: async (thresholdVal: number) => {
      return (
        await api.post<{ ok: boolean; threshold: number }>("/v1/admin/service-keys/threshold", {
          threshold: thresholdVal,
        })
      ).data
    },
    onSuccess: (data) => {
      toastSuccess(`Порог малого остатка изменен на ${data.threshold} шт.`)
      setEditingThreshold(false)
      void qc.invalidateQueries({ queryKey: ["admin-service-keys-overview"] })
    },
    onError: (e) => toastError("Не удалось обновить порог", getErrorDetail(e)),
  })


  // Запрос журнала ключей
  const isUsedParam = statusFilter === "available" ? false : statusFilter === "used" ? true : undefined
  const serviceIdParam = serviceFilter !== "all" ? Number(serviceFilter) : undefined

  const { data: keysPage, isLoading: isKeysLoading, refetch: refetchKeys } = useQuery({
    queryKey: ["admin-global-service-keys", serviceIdParam, isUsedParam, searchQuery],
    queryFn: async () =>
      (
        await api.get<KeysPageResponse>("/v1/admin/service-keys", {
          params: {
            service_id: serviceIdParam,
            is_used: isUsedParam,
            order_id: searchQuery && !isNaN(Number(searchQuery)) ? Number(searchQuery) : undefined,
            limit: 50,
            sort: "-created_at",
          },
        })
      ).data,
  })

  const removeKey = useMutation({
    mutationFn: async (keyId: number) => api.delete(`/v1/admin/service-keys/${keyId}`),
    onSuccess: () => {
      toastSuccess("Ключ удален из пула")
      void qc.invalidateQueries({ queryKey: ["admin-global-service-keys"] })
      void qc.invalidateQueries({ queryKey: ["admin-service-keys-overview"] })
    },
    onError: (e) => toastError("Не удалось удалить ключ", getErrorDetail(e)),
  })

  const revealKey = async (keyId: number) => {
    if (revealed[keyId]) {
      setRevealed((prev) => {
        const next = { ...prev }
        delete next[keyId]
        return next
      })
      return
    }
    try {
      const res = await api.get<{ value: string }>(`/v1/admin/service-keys/${keyId}/reveal`)
      setRevealed((prev) => ({ ...prev, [keyId]: res.data.value }))
    } catch (e) {
      toastError("Не удалось раскрыть значение ключа", getErrorDetail(e))
    }
  }

  const openImportForService = (serviceId?: number) => {
    setImportTargetServiceId(serviceId)
    setImportModalOpen(true)
  }

  const setFilterService = (serviceId: string) => {
    setSearchParams((prev) => {
      const n = new URLSearchParams(prev)
      if (serviceId === "all") n.delete("service_id")
      else n.set("service_id", serviceId)
      n.set("tab", "keys")
      return n
    })
  }

  return (
    <div className="space-y-6">
      {/* Шапка раздела */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-2">
            <KeyRound className="size-6 text-primary" /> Инвентарь цифровых ключей
          </h1>
          <p className="text-sm text-muted-foreground">
            Единый пул лицензий и ключей для услуг SaviorBill с автовыдачей при оплате.
          </p>
        </div>

        <div className="flex items-center flex-wrap gap-2">
          {/* Настройка порога алертов */}
          <div className="flex items-center gap-1.5 px-3 py-1 rounded-lg border border-border/80 bg-muted/40 text-xs">
            <span className="text-muted-foreground">Порог «Мало»:</span>
            {editingThreshold ? (
              <div className="flex items-center gap-1">
                <Input
                  type="number"
                  min={1}
                  max={9999}
                  className="h-6 w-16 text-xs px-1 text-center"
                  value={tempThreshold}
                  onChange={(e) => setTempThreshold(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      const num = parseInt(tempThreshold, 10)
                      if (!isNaN(num) && num > 0) updateThresholdMutation.mutate(num)
                    } else if (e.key === "Escape") {
                      setEditingThreshold(false)
                      setTempThreshold(String(overview?.threshold ?? 5))
                    }
                  }}
                  autoFocus
                />
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-6 px-1.5 text-xs text-primary"
                  onClick={() => {
                    const num = parseInt(tempThreshold, 10)
                    if (!isNaN(num) && num > 0) updateThresholdMutation.mutate(num)
                  }}
                  disabled={updateThresholdMutation.isPending}
                >
                  OK
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-6 px-1.5 text-xs text-muted-foreground"
                  onClick={() => {
                    setEditingThreshold(false)
                    setTempThreshold(String(overview?.threshold ?? 5))
                  }}
                >
                  ✕
                </Button>
              </div>
            ) : (
              <button
                type="button"
                className="font-bold text-amber-500 hover:underline cursor-pointer flex items-center gap-1"
                onClick={() => setEditingThreshold(true)}
                title="Нажмите, чтобы изменить порог"
              >
                &lt; {overview?.threshold ?? 5} шт. ✎
              </button>
            )}
          </div>

          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              void refetchOverview()
              void refetchKeys()
            }}
          >
            <RefreshCw className="size-4" /> Обновить
          </Button>

          {canCreate && (
            <Button size="sm" onClick={() => openImportForService()}>
              <Plus className="size-4" /> Импортировать ключи
            </Button>
          )}
        </div>
      </div>

      {/* KPI Cards: аналитика и алерты */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {/* Доступно */}
        <Card className="bg-card/70 border-border/80 shadow-2xs">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-medium text-muted-foreground">
              Доступно к выдаче
            </CardTitle>
            <div className="size-8 rounded-lg bg-emerald-500/10 flex items-center justify-center text-emerald-500">
              <CheckCircle2 className="size-4" />
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-foreground">
              {isOverviewLoading ? "…" : overview?.total_available ?? 0}
            </div>
            <p className="text-[11px] text-muted-foreground mt-1">
              Активных лицензий готовы к мгновенной выдаче
            </p>
          </CardContent>
        </Card>

        {/* Выдано */}
        <Card className="bg-card/70 border-border/80 shadow-2xs">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-medium text-muted-foreground">
              Выдано покупателям
            </CardTitle>
            <div className="size-8 rounded-lg bg-primary/10 flex items-center justify-center text-primary">
              <Package className="size-4" />
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-foreground">
              {isOverviewLoading ? "…" : overview?.total_used ?? 0}
            </div>
            <p className="text-[11px] text-muted-foreground mt-1">
              Успешно привязаны к оплаченным заказам
            </p>
          </CardContent>
        </Card>

        {/* Товары с низким остатком */}
        <Card
          className={`bg-card/70 border-border/80 shadow-2xs transition-all ${
            (overview?.low_stock_count ?? 0) > 0 ? "border-amber-500/40 bg-amber-500/5 cursor-pointer" : ""
          }`}
          onClick={() => {
            const firstLow = overview?.items.find((i) => i.stock_status === "low")
            if (firstLow) setFilterService(String(firstLow.service_id))
          }}
        >
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-medium text-muted-foreground">
              Заканчиваются (&lt; {overview?.threshold ?? 5} шт.)
            </CardTitle>
            <div className="size-8 rounded-lg bg-amber-500/10 flex items-center justify-center text-amber-500">
              <AlertTriangle className="size-4" />
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-amber-500">
              {isOverviewLoading ? "…" : overview?.low_stock_count ?? 0}
            </div>
            <p className="text-[11px] text-muted-foreground mt-1">
              Товаров требуют скорого пополнения
            </p>
          </CardContent>
        </Card>

        {/* Закончились (Out of stock) */}
        <Card
          className={`bg-card/70 border-border/80 shadow-2xs transition-all ${
            (overview?.out_of_stock_count ?? 0) > 0 ? "border-red-500/40 bg-red-500/5 cursor-pointer" : ""
          }`}
          onClick={() => {
            const firstOut = overview?.items.find((i) => i.stock_status === "out_of_stock")
            if (firstOut) setFilterService(String(firstOut.service_id))
          }}
        >
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-medium text-muted-foreground">
              Закончились (0 шт.)
            </CardTitle>
            <div className="size-8 rounded-lg bg-red-500/10 flex items-center justify-center text-red-500">
              <XCircle className="size-4" />
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-red-500">
              {isOverviewLoading ? "…" : overview?.out_of_stock_count ?? 0}
            </div>
            <p className="text-[11px] text-muted-foreground mt-1">
              Продажи этих товаров временно остановлены
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Вкладки: Обзор остатков по товарам / Полный журнал ключей */}
      <Tabs
        value={activeTab}
        onValueChange={(val) => {
          setSearchParams((prev) => {
            const n = new URLSearchParams(prev)
            n.set("tab", val)
            return n
          })
        }}
        className="space-y-4"
      >
        <TabsList className="bg-muted/50 p-1">
          <TabsTrigger value="overview" className="gap-2">
            <Package className="size-4" /> Товары и остатки
          </TabsTrigger>
          <TabsTrigger value="keys" className="gap-2">
            <KeyRound className="size-4" /> Журнал ключей
          </TabsTrigger>
        </TabsList>

        {/* Вкладка 1: Остатки по товарам */}
        <TabsContent value="overview" className="space-y-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold">
                Состояние запасов цифровых ключей по товарам
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Товар / Услуга</TableHead>
                    <TableHead>Категория</TableHead>
                    <TableHead>Цена</TableHead>
                    <TableHead>Остаток</TableHead>
                    <TableHead>Выдано</TableHead>
                    <TableHead>Всего</TableHead>
                    <TableHead>Статус</TableHead>
                    <TableHead className="text-right">Действия</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {isOverviewLoading && (
                    <TableRow>
                      <TableCell colSpan={8} className="py-8 text-center text-sm text-muted-foreground">
                        Загрузка запасов…
                      </TableCell>
                    </TableRow>
                  )}
                  {!isOverviewLoading && (overview?.items?.length ?? 0) === 0 && (
                    <TableRow>
                      <TableCell colSpan={8} className="py-8 text-center text-sm text-muted-foreground">
                        Нет товаров с типом выдачи «Ключи». Создайте товар в каталоге.
                      </TableCell>
                    </TableRow>
                  )}
                  {overview?.items?.map((item) => (
                    <TableRow key={item.service_id} className="hover:bg-muted/40 transition-colors">
                      <TableCell>
                        <div className="flex flex-col">
                          <Link
                            to={`/services/${item.service_id}`}
                            className="font-medium text-foreground hover:text-primary transition-colors hover:underline"
                          >
                            {item.service_name}
                          </Link>
                          <span className="font-mono text-xs text-muted-foreground">
                            {item.service_slug}
                          </span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <span className="text-xs text-muted-foreground">
                          {item.catalog_name || "—"}
                        </span>
                      </TableCell>
                      <TableCell className="font-mono text-xs font-semibold">
                        {item.price} {item.currency}
                      </TableCell>
                      <TableCell>
                        <span
                          className={`font-mono text-sm font-bold ${
                            item.stock_status === "out_of_stock"
                              ? "text-red-500"
                              : item.stock_status === "low"
                              ? "text-amber-500"
                              : "text-emerald-500"
                          }`}
                        >
                          {item.available_keys}
                        </span>
                      </TableCell>
                      <TableCell className="font-mono text-xs text-muted-foreground">
                        {item.used_keys}
                      </TableCell>
                      <TableCell className="font-mono text-xs text-muted-foreground">
                        {item.total_keys}
                      </TableCell>
                      <TableCell>
                        {item.stock_status === "out_of_stock" ? (
                          <Badge variant="destructive" className="text-[10px] gap-1">
                            <span className="size-1.5 rounded-full bg-red-400" /> Закончились
                          </Badge>
                        ) : item.stock_status === "low" ? (
                          <Badge variant="outline" className="text-[10px] gap-1 border-amber-500/40 text-amber-500 bg-amber-500/10">
                            <span className="size-1.5 rounded-full bg-amber-500" /> Мало (&lt; {overview?.threshold ?? 5})
                          </Badge>
                        ) : (
                          <Badge variant="outline" className="text-[10px] gap-1 border-emerald-500/40 text-emerald-500 bg-emerald-500/10">
                            <span className="size-1.5 rounded-full bg-emerald-500" /> В наличии
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-xs h-8"
                            onClick={() => setFilterService(String(item.service_id))}
                          >
                            Ключи
                          </Button>
                          {canCreate && (
                            <Button
                              variant="outline"
                              size="sm"
                              className="text-xs h-8 gap-1"
                              onClick={() => openImportForService(item.service_id)}
                            >
                              <Plus className="size-3.5" /> Пополнить
                            </Button>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Вкладка 2: Журнал ключей с фильтрацией */}
        <TabsContent value="keys" className="space-y-4">
          <Card>
            <CardHeader className="pb-3">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <CardTitle className="text-base font-semibold">
                  Журнал ключей
                </CardTitle>

                {/* Панель фильтров */}
                <div className="flex flex-wrap items-center gap-2">
                  {/* Выбор услуги */}
                  <Select
                    value={serviceFilter}
                    onValueChange={(val) => {
                      setSearchParams((prev) => {
                        const n = new URLSearchParams(prev)
                        if (val === "all") n.delete("service_id")
                        else n.set("service_id", val ?? "")
                        return n
                      })
                    }}
                  >
                    <SelectTrigger className="w-[180px] h-8 text-xs">
                      <SelectValue placeholder="Все товары" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">Все товары</SelectItem>
                      {overview?.items.map((i) => (
                        <SelectItem key={i.service_id} value={String(i.service_id)}>
                          {i.service_name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>

                  {/* Статус */}
                  <Select
                    value={statusFilter}
                    onValueChange={(val) => {
                      setSearchParams((prev) => {
                        const n = new URLSearchParams(prev)
                        if (val === "all") n.delete("status")
                        else n.set("status", val ?? "")
                        return n
                      })
                    }}
                  >
                    <SelectTrigger className="w-[140px] h-8 text-xs">
                      <SelectValue placeholder="Все статусы" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">Все статусы</SelectItem>
                      <SelectItem value="available">Только свободные</SelectItem>
                      <SelectItem value="used">Только выданные</SelectItem>
                    </SelectContent>
                  </Select>

                  {/* Поиск по Order ID */}
                  <div className="relative">
                    <Search className="size-3.5 absolute left-2.5 top-2.5 text-muted-foreground" />
                    <Input
                      placeholder="№ Заказа…"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="pl-8 h-8 text-xs w-[120px]"
                    />
                  </div>
                </div>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-16">ID</TableHead>
                    <TableHead>Товар / Услуга</TableHead>
                    <TableHead>Значение ключа</TableHead>
                    <TableHead>Статус</TableHead>
                    <TableHead>Заказ</TableHead>
                    <TableHead>Добавлен</TableHead>
                    <TableHead className="text-right">Действия</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {isKeysLoading && (
                    <TableRow>
                      <TableCell colSpan={7} className="py-8 text-center text-sm text-muted-foreground">
                        Загрузка ключей…
                      </TableCell>
                    </TableRow>
                  )}
                  {!isKeysLoading && (keysPage?.items?.length ?? 0) === 0 && (
                    <TableRow>
                      <TableCell colSpan={7} className="py-8 text-center text-sm text-muted-foreground">
                        Ключей с выбранными фильтрами не найдено.
                      </TableCell>
                    </TableRow>
                  )}
                  {keysPage?.items?.map((k) => (
                    <TableRow key={k.id} className="hover:bg-muted/40 transition-colors">
                      <TableCell className="font-mono text-xs text-muted-foreground">
                        #{k.id}
                      </TableCell>
                      <TableCell>
                        <Link
                          to={`/services/${k.service_id}`}
                          className="font-medium text-foreground hover:text-primary transition-colors text-xs hover:underline"
                        >
                          {k.service_name || `Услуга #${k.service_id}`}
                        </Link>
                      </TableCell>
                      <TableCell className="font-mono text-xs">
                        {revealed[k.id] ? (
                          <span className="font-bold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
                            {revealed[k.id]}
                          </span>
                        ) : (
                          <span className="text-muted-foreground tracking-widest">
                            ••••••••••••
                          </span>
                        )}
                      </TableCell>
                      <TableCell>
                        {k.is_used ? (
                          <Badge variant="outline" className="text-[10px]">
                            выдан
                          </Badge>
                        ) : (
                          <Badge className="text-[10px] bg-emerald-500/15 text-emerald-500 border border-emerald-500/30 hover:bg-emerald-500/20">
                            свободен
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell>
                        {k.order_id ? (
                          <Link
                            to={`/orders?id=${k.order_id}`}
                            className="font-mono text-xs text-primary hover:underline"
                          >
                            Заказ #{k.order_id}
                          </Link>
                        ) : (
                          <span className="text-xs text-muted-foreground">—</span>
                        )}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {new Date(k.created_at).toLocaleString()}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex items-center justify-end gap-1">
                          {canReveal && (
                            <Button
                              variant="ghost"
                              size="icon"
                              className="size-8"
                              title={revealed[k.id] ? "Скрыть" : "Показать значение"}
                              onClick={() => revealKey(k.id)}
                            >
                              {revealed[k.id] ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                            </Button>
                          )}
                          {canDelete && !k.is_used && (
                            <Button
                              variant="ghost"
                              size="icon"
                              className="size-8 text-destructive hover:bg-destructive/10"
                              title="Удалить ключ"
                              onClick={() => removeKey.mutate(k.id)}
                            >
                              <Trash2 className="size-4" />
                            </Button>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Модалка импорта */}
      <ImportKeysModal
        open={importModalOpen}
        onOpenChange={setImportModalOpen}
        defaultServiceId={importTargetServiceId}
        services={overview?.items ?? []}
      />
    </div>
  )
}
