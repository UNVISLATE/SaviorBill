import { useEffect, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate, useParams, Link } from "react-router-dom"
import {
  ArrowLeft,
  FileCode2,
  FileUp,
  KeyRound,
  Package,
  Plus,
  Save,
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
import { Switch } from "@/components/shadsnui/switch"
import { Textarea } from "@/components/shadsnui/textarea"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/shadsnui/select"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/shadsnui/dialog"
import { MediaPickerDialog } from "@/components/media/MediaPickerDialog"
import { ServiceMediaWidget } from "@/components/media/ServiceMediaWidget"
import { useInstanceCurrency } from "@/lib/currency"
import { toastError, toastSuccess } from "@/lib/toast"

interface Catalog {
  id: number
  name: string
}

interface ServiceAdmin {
  id: number
  slug: string
  name: string
  description: string | null
  catalog_id: number | null
  price: string
  currency: string
  delivery: string
  is_active: boolean
  out_of_stock: boolean | null
  lua_script_id: number | null
  lua_script_version: number | null
  params: Record<string, unknown>
  settings: Record<string, unknown>
  warnings: string[]
  created_at?: string
  updated_at?: string
}

interface LuaScript {
  id: number
  name: string
}

interface Attachment {
  id: number
  media_id: number
  token: string
  kind: string
  mime: string | null
  status: string
  tag: string | null
  position: number
  url: string
}

interface Stock {
  available: number
  out_of_stock: boolean
}

function translit(str: string): string {
  const ru: Record<string, string> = {
    а: "a", б: "b", в: "v", г: "g", д: "d", е: "e", ё: "yo", ж: "zh",
    з: "z", и: "i", й: "y", к: "k", л: "l", м: "m", н: "n", о: "o",
    п: "p", р: "r", с: "s", т: "t", у: "u", ф: "f", х: "kh", ц: "ts",
    ч: "ch", ш: "sh", щ: "shch", ъ: "", ы: "y", ь: "", э: "e", ю: "yu", я: "ya",
  }
  return str
    .toLowerCase()
    .split("")
    .map((c) => ru[c] || c)
    .join("")
    .replace(/[^a-z0-9_-]/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "")
}

export function ServiceEditorPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { can } = useAuth()
  const qc = useQueryClient()

  const isNew = !id || id === "new"
  const serviceId = isNew ? null : Number(id)

  // Данные услуги при редактировании
  const { data: service, isLoading: isServiceLoading } = useQuery({
    queryKey: ["admin-service", serviceId],
    queryFn: async () => (await api.get<ServiceAdmin>(`/v1/admin/services/${serviceId}`)).data,
    enabled: Boolean(serviceId && Number.isFinite(serviceId)),
  })

  // Список каталогов
  const { data: catalogs } = useQuery({
    queryKey: ["admin-catalogs"],
    queryFn: async () => (await api.get<Catalog[]>("/v1/admin/catalogs")).data,
    staleTime: 60_000,
  })

  // Вложения
  const { data: attachments } = useQuery({
    queryKey: ["admin-service-attachments", serviceId],
    queryFn: async () => (await api.get<Attachment[]>(`/v1/admin/services/${serviceId}/attachments`)).data,
    enabled: Boolean(serviceId),
  })

  // Остаток ключей (если delivery=key)
  const { data: stock } = useQuery({
    queryKey: ["admin-service-stock", serviceId],
    queryFn: async () => (await api.get<Stock>(`/v1/admin/services/${serviceId}/keys/stock`)).data,
    enabled: Boolean(serviceId && service?.delivery === "key"),
  })

  // Скрипты Lua
  const { data: luaScripts } = useQuery({
    queryKey: ["admin-lua-scripts-lookup"],
    queryFn: async () => (await api.get<LuaScript[]>("/v1/admin/lua")).data,
    staleTime: 60_000,
  })

  // Локальное состояние формы
  const [name, setName] = useState("")
  const [slug, setSlug] = useState("")
  const [description, setDescription] = useState("")
  const [catalogId, setCatalogId] = useState<string>("")
  const [price, setPrice] = useState("0")
  const { currency: instanceCurrency } = useInstanceCurrency()
  const [currency, setCurrency] = useState("RUB")
  const [delivery, setDelivery] = useState<"key" | "lua">("key")
  const [luaScriptId, setLuaScriptId] = useState<string>("")
  const [isActive, setIsActive] = useState(true)
  const [paramsText, setParamsText] = useState("{}")
  const [settingsText, setSettingsText] = useState("{}")
  const [jsonError, setJsonError] = useState<string | null>(null)
  const [slugManuallyEdited, setSlugManuallyEdited] = useState(false)

  // Модалки
  const [mediaPickerOpen, setMediaPickerOpen] = useState(false)
  const [quickImportOpen, setQuickImportOpen] = useState(false)
  const [quickImportText, setQuickImportText] = useState("")
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Заполнение полей при загрузке существующей услуги
  useEffect(() => {
    if (isNew && instanceCurrency) {
      setCurrency(instanceCurrency)
    }
  }, [isNew, instanceCurrency])
  useEffect(() => {
    if (isNew && instanceCurrency) {
      setCurrency(instanceCurrency)
    }
  }, [isNew, instanceCurrency])


  useEffect(() => {
    if (service) {
      setName(service.name)
      setSlug(service.slug)
      setDescription(service.description ?? "")
      setCatalogId(service.catalog_id ? String(service.catalog_id) : "")
      setPrice(service.price)
      setCurrency(service.currency)
      setDelivery(service.delivery as "key" | "lua")
      setLuaScriptId(service.lua_script_id ? String(service.lua_script_id) : "")
      setIsActive(service.is_active)
      setParamsText(JSON.stringify(service.params || {}, null, 2))
      setSettingsText(JSON.stringify(service.settings || {}, null, 2))
      setSlugManuallyEdited(true)
    }
  }, [service])

  // Автогенерация слага для новой услуги
  const handleNameChange = (val: string) => {
    setName(val)
    if (isNew && !slugManuallyEdited) {
      setSlug(translit(val))
    }
  }

  // Мутация сохранения (создание или редактирование)
  const saveMutation = useMutation({
    mutationFn: async () => {
      let params: unknown
      let settings: unknown
      try {
        params = JSON.parse(paramsText)
        settings = JSON.parse(settingsText)
      } catch {
        setJsonError("params или settings содержат некорректный JSON")
        throw new Error("invalid json")
      }
      setJsonError(null)

      if (isNew) {
        return (
          await api.post("/v1/admin/services", {
            name,
            slug,
            description: description || null,
            catalog_id: catalogId ? Number(catalogId) : null,
            price,
            currency,
            delivery,
            lua_script_id: delivery === "lua" && luaScriptId ? Number(luaScriptId) : null,
            params,
            settings,
            is_active: isActive,
          })
        ).data
      } else {
        return (
          await api.patch(`/v1/admin/services/${serviceId}`, {
            name,
            description: description || null,
            catalog_id: catalogId ? Number(catalogId) : null,
            price,
            currency,
            delivery,
            lua_script_id: delivery === "lua" && luaScriptId ? Number(luaScriptId) : null,
            params,
            settings,
            is_active: isActive,
          })
        ).data
      }
    },
    onSuccess: (data: ServiceAdmin) => {
      toastSuccess(isNew ? "Услуга создана" : "Услуга сохранена")
      data.warnings?.forEach((w) => toastError("Предупреждение", w))
      void qc.invalidateQueries({ queryKey: ["admin-services"] })
      if (isNew) {
        navigate(`/services/${data.id}`, { replace: true })
      } else {
        void qc.invalidateQueries({ queryKey: ["admin-service", serviceId] })
      }
    },
    onError: (e) => {
      if ((e as Error).message !== "invalid json") {
        toastError("Не удалось сохранить услугу", getErrorDetail(e))
      }
    },
  })

  // Быстрое сохранение по Ctrl+S
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault()
        saveMutation.mutate()
      }
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [saveMutation])

  // Удаление услуги
  const deleteMutation = useMutation({
    mutationFn: async () => api.delete(`/v1/admin/services/${serviceId}`),
    onSuccess: () => {
      toastSuccess("Услуга удалена")
      void qc.invalidateQueries({ queryKey: ["admin-services"] })
      navigate("/services", { replace: true })
    },
    onError: (e) => toastError("Не удалось удалить услугу", getErrorDetail(e)),
  })

  // Добавление вложения медиа
  const addAttachmentMutation = useMutation({
    mutationFn: async (mediaId: number) =>
      api.post(`/v1/admin/services/${serviceId}/attachments`, {
        media_id: mediaId,
        position: attachments?.length ?? 0,
      }),
    onSuccess: () => {
      toastSuccess("Медиа прикреплено к карточке")
      void qc.invalidateQueries({ queryKey: ["admin-service-attachments", serviceId] })
    },
    onError: (e) => toastError("Не удалось прикрепить медиа", getErrorDetail(e)),
  })


  // Быстрый импорт ключей
  const quickImportMutation = useMutation({
    mutationFn: async () => {
      const values = quickImportText.split("\n").map((v) => v.trim()).filter(Boolean)
      return (
        await api.post(`/v1/admin/services/${serviceId}/keys/import`, { values })
      ).data
    },
    onSuccess: (data: { added: number; skipped: number }) => {
      toastSuccess(`Импортировано: ${data.added}${data.skipped ? `, пропущено дублей: ${data.skipped}` : ""}`)
      setQuickImportText("")
      setQuickImportOpen(false)
      void qc.invalidateQueries({ queryKey: ["admin-service-stock", serviceId] })
      void qc.invalidateQueries({ queryKey: ["admin-service-keys", serviceId] })
      void qc.invalidateQueries({ queryKey: ["admin-service-keys-overview"] })
    },
    onError: (e) => toastError("Ошибка импорта ключей", getErrorDetail(e)),
  })

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      const content = await file.text()
      setQuickImportText(content)
      toastSuccess(`Файл ${file.name} загружен`)
    } catch (err) {
      toastError("Ошибка чтения файла", String(err))
    }
    e.target.value = ""
  }

  if (!isNew && isServiceLoading) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
        Загрузка параметров услуги…
      </div>
    )
  }

  return (
    <div className="space-y-6 max-w-6xl mx-auto pb-12">
      {/* Верхний бар навигации */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b pb-4">
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="icon"
            className="size-9 rounded-xl border hover:bg-muted"
            onClick={() => navigate("/services")}
          >
            <ArrowLeft className="size-4" />
          </Button>

          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-xl font-bold tracking-tight text-foreground">
                {isNew ? "Создание услуги" : name || "Редактирование услуги"}
              </h1>
              {!isNew && slug && (
                <Badge variant="outline" className="font-mono text-xs">
                  {slug}
                </Badge>
              )}
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              {isNew
                ? "Заполните параметры товара, цену и настройте способ автоматической выдачи."
                : `ID товара: #${serviceId}`}
            </p>
          </div>
        </div>

        {/* Кнопки быстрого сохранения в шапке */}
        <div className="flex items-center gap-2">
          <Button
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending || !name.trim() || !slug.trim()}
            className="gap-2 shadow-xs"
          >
            <Save className="size-4" />
            {saveMutation.isPending ? "Сохранение…" : isNew ? "Создать услугу" : "Сохранить"}
            <kbd className="hidden sm:inline-block ml-1 px-1.5 py-0.5 text-[10px] font-mono bg-primary-foreground/20 rounded">
              Ctrl+S
            </kbd>
          </Button>
        </div>
      </div>

      {/* Основная сетка: слева контент формы (2/3), справа статус и действия (1/3) */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Левая колонка формы */}
        <div className="space-y-6 lg:col-span-2">
          {/* Блок 1: Основные реквизиты товара */}
          <Card className="bg-card/90 shadow-2xs border-border/80">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <Package className="size-4 text-primary" /> Основные параметры
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label>Название услуги *</Label>
                  <Input
                    value={name}
                    onChange={(e) => handleNameChange(e.target.value)}
                    placeholder="Например: Премиум подписка 30 дней"
                  />
                </div>

                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <Label>Slug (URL идентификатор) *</Label>
                    <span className="text-[11px] text-muted-foreground font-mono">
                      /services/{slug || "…"}
                    </span>
                  </div>
                  <Input
                    value={slug}
                    disabled={!isNew}
                    onChange={(e) => {
                      setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, ""))
                      setSlugManuallyEdited(true)
                    }}
                    placeholder="premium-30-days"
                    className="font-mono text-xs"
                  />
                </div>
              </div>

              <div className="grid gap-4 sm:grid-cols-3">
                <div className="space-y-1.5 sm:col-span-1">
                  <Label>Каталог</Label>
                  <Select
                    value={catalogId || "root"}
                    onValueChange={(v) => setCatalogId(v === "root" ? "" : v ?? "")}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Без каталога" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="root">— Без каталога —</SelectItem>
                      {catalogs?.map((c) => (
                        <SelectItem key={c.id} value={String(c.id)}>
                          {c.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-1.5 sm:col-span-1">
                  <Label>Цена *</Label>
                  <Input
                    type="number"
                    min="0"
                    step="0.01"
                    value={price}
                    onChange={(e) => setPrice(e.target.value)}
                    placeholder="0.00"
                    className="font-mono text-sm"
                  />
                </div>

                <div className="space-y-1.5 sm:col-span-1">
                  <Label>Валюта *</Label>
                  <Input
                    value={currency}
                    onChange={(e) => setCurrency(e.target.value.toUpperCase())}
                    maxLength={8}
                    placeholder={instanceCurrency || "RUB"}
                    className="font-mono text-sm"
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Блок 2: Способ выдачи (Fulfillment) */}
          <Card className="bg-card/90 shadow-2xs border-border/80">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <KeyRound className="size-4 text-primary" /> Выдача товара покупателю
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              {/* Переключатель способа выдачи (2 большие карточки) */}
              <div className="grid gap-3 sm:grid-cols-2">
                <div
                  onClick={() => setDelivery("key")}
                  className={`p-4 rounded-xl border cursor-pointer transition-all flex flex-col justify-between ${
                    delivery === "key"
                      ? "border-primary bg-primary/5 shadow-xs ring-1 ring-primary/40"
                      : "border-border/70 hover:border-border hover:bg-muted/40"
                  }`}
                >
                  <div className="flex items-center gap-2.5">
                    <div
                      className={`size-8 rounded-lg flex items-center justify-center ${
                        delivery === "key" ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"
                      }`}
                    >
                      <KeyRound className="size-4" />
                    </div>
                    <div>
                      <div className="text-sm font-semibold">Цифровые ключи</div>
                      <div className="text-[11px] text-muted-foreground">Из пула лицензий</div>
                    </div>
                  </div>
                  <p className="text-xs text-muted-foreground mt-3">
                    Автоматическая отправка уникального ключа покупателю сразу после подтверждения оплаты.
                  </p>
                </div>

                <div
                  onClick={() => setDelivery("lua")}
                  className={`p-4 rounded-xl border cursor-pointer transition-all flex flex-col justify-between ${
                    delivery === "lua"
                      ? "border-primary bg-primary/5 shadow-xs ring-1 ring-primary/40"
                      : "border-border/70 hover:border-border hover:bg-muted/40"
                  }`}
                >
                  <div className="flex items-center gap-2.5">
                    <div
                      className={`size-8 rounded-lg flex items-center justify-center ${
                        delivery === "lua" ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"
                      }`}
                    >
                      <FileCode2 className="size-4" />
                    </div>
                    <div>
                      <div className="text-sm font-semibold">Lua-скрипт</div>
                      <div className="text-[11px] text-muted-foreground">Изолированный воркер</div>
                    </div>
                  </div>
                  <p className="text-xs text-muted-foreground mt-3">
                    Вызов скрипта автоматизации через песочницу LuaWorker: выдача ролей, API ботов, генерация ссылок.
                  </p>
                </div>
              </div>

              {/* Настройки пула ключей */}
              {delivery === "key" && (
                <div className="p-4 rounded-xl bg-muted/40 border border-border/80 space-y-3">
                  <div className="flex items-center justify-between flex-wrap gap-2">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold">Запас ключей в пуле:</span>
                      {isNew ? (
                        <span className="text-xs text-muted-foreground">
                          Ключи можно загрузить сразу после первого сохранения
                        </span>
                      ) : (
                        <span
                          className={`font-mono text-sm font-bold ${
                            stock?.out_of_stock
                              ? "text-red-500"
                              : (stock?.available ?? 0) < 5
                              ? "text-amber-500"
                              : "text-emerald-500"
                          }`}
                        >
                          {stock?.available ?? 0} шт.
                        </span>
                      )}
                    </div>

                    {!isNew && (
                      <div className="flex items-center gap-2">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="h-7 text-xs"
                          onClick={() => setQuickImportOpen(true)}
                        >
                          <Plus className="size-3.5" /> Быстрый импорт
                        </Button>
                        <Link
                          to={`/service-keys?service_id=${serviceId}&tab=keys`}
                          className="text-xs text-primary hover:underline font-medium"
                        >
                          Все ключи в пуле ↗
                        </Link>
                      </div>
                    )}
                  </div>

                  {!isNew && stock?.out_of_stock && (
                    <div className="flex items-center gap-2 text-xs text-red-500 bg-red-500/10 p-2.5 rounded-lg border border-red-500/20">
                      <XCircle className="size-4 shrink-0" />
                      <span>
                        Ключи закончились. Продажи товара остановлены до пополнения пула.
                      </span>
                    </div>
                  )}
                </div>
              )}

              {/* Настройки Lua-скрипта */}
              {delivery === "lua" && (
                <div className="space-y-4 p-4 rounded-xl bg-muted/30 border border-border/80">
                  <div className="space-y-1.5">
                    <Label>Скрипт автоматизации *</Label>
                    <Select
                      value={luaScriptId}
                      onValueChange={(v) => setLuaScriptId(v ?? "")}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Выберите скрипт" />
                      </SelectTrigger>
                      <SelectContent>
                        {luaScripts?.map((s) => (
                          <SelectItem key={s.id} value={String(s.id)}>
                            {s.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <Label>Параметры доставки (Params JSON)</Label>
                      <span className="text-[11px] text-muted-foreground font-mono">
                        json schema
                      </span>
                    </div>
                    <Textarea
                      rows={4}
                      value={paramsText}
                      onChange={(e) => setParamsText(e.target.value)}
                      className="font-mono text-xs"
                    />
                  </div>

                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <Label>Настройки скрипта (Settings JSON)</Label>
                      <span className="text-[11px] text-muted-foreground font-mono">
                        service.settings.*
                      </span>
                    </div>
                    <Textarea
                      rows={4}
                      value={settingsText}
                      onChange={(e) => setSettingsText(e.target.value)}
                      className="font-mono text-xs"
                    />
                  </div>

                  {jsonError && <p className="text-xs text-destructive">{jsonError}</p>}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Блок 3: Медиа карточки товара */}
          {isNew ? (
            <Card className="bg-card/90 shadow-2xs border-border/80">
              <CardHeader className="pb-3">
                <CardTitle className="text-base font-semibold">
                  Медиа карточки товара
                </CardTitle>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Медиафайлы можно будет прикрепить к карточке сразу после сохранения услуги.
                </p>
              </CardHeader>
            </Card>
          ) : (
            <div className="space-y-2">
              <div className="flex items-center justify-between px-1">
                <div>
                  <h3 className="text-base font-semibold text-foreground">
                    Медиа карточки товара
                  </h3>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Изображения, баннеры и промо-файлы с распределением по расположению (placement).
                  </p>
                </div>
              </div>
              <ServiceMediaWidget
                serviceId={serviceId!}
                serviceName={name || `Услуга #${serviceId}`}
                attachments={attachments ?? []}
                onRefresh={() => {
                  void qc.invalidateQueries({ queryKey: ["admin-service-attachments", serviceId] })
                }}
              />
            </div>
          )}

          {/* Блок 4: Описание услуги */}
          <Card className="bg-card/90 shadow-2xs border-border/80">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold">
                Описание товара
              </CardTitle>
            </CardHeader>
            <CardContent>
              <Textarea
                rows={6}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Подробное описание товара, возможности, комплектация или инструкция по активации…"
                className="leading-relaxed"
              />
            </CardContent>
          </Card>
        </div>

        {/* Правая колонка: Панель действий (Sticky) */}
        <div className="space-y-4">
          <div className="sticky top-6 space-y-4">
            <Card className="bg-card/95 shadow-xs border-border/80 backdrop-blur-xs">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-semibold">Действия</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Тумблер активности */}
                <div className="flex items-center justify-between p-3 rounded-xl border bg-muted/30">
                  <div className="space-y-0.5">
                    <Label className="text-xs font-semibold cursor-pointer">
                      Активность товара
                    </Label>
                    <p className="text-[11px] text-muted-foreground">
                      {isActive ? "Доступен к покупке" : "Скрыт из каталога"}
                    </p>
                  </div>
                  <Switch checked={isActive} onCheckedChange={setIsActive} />
                </div>

                {/* Большая кнопка сохранения */}
                <Button
                  onClick={() => saveMutation.mutate()}
                  disabled={saveMutation.isPending || !name.trim() || !slug.trim()}
                  className="w-full h-11 text-sm font-semibold gap-2 shadow-sm"
                >
                  <Save className="size-4" />
                  {saveMutation.isPending ? "Сохранение…" : isNew ? "Создать товар" : "Сохранить товар"}
                </Button>

                {/* Дополнительные ссылки для существующей услуги */}
                {!isNew && (
                  <div className="pt-2 border-t space-y-2">
                    {delivery === "key" && (
                      <Button
                        variant="outline"
                        size="sm"
                        className="w-full text-xs justify-start gap-2 h-9"
                        onClick={() => navigate(`/service-keys?service_id=${serviceId}&tab=keys`)}
                      >
                        <KeyRound className="size-4 text-primary" />
                        Инвентарь ключей ({stock?.available ?? 0} шт.)
                      </Button>
                    )}

                    {can("services.delete") && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="w-full text-xs text-destructive hover:bg-destructive/10 justify-start gap-2 h-9"
                        onClick={() => setDeleteConfirmOpen(true)}
                      >
                        <Trash2 className="size-4" />
                        Удалить услугу
                      </Button>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Мета-информация о датах (если редактирование) */}
            {!isNew && service && (
              <Card className="bg-muted/30 border-border/60 text-xs text-muted-foreground p-4 space-y-1.5">
                <div className="flex items-center justify-between">
                  <span>Статус пула:</span>
                  <span className="font-medium text-foreground">
                    {delivery === "key" ? (stock?.out_of_stock ? "Закончились" : "В наличии") : "Lua автоматизация"}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span>Способ доставки:</span>
                  <span className="font-mono text-foreground">{delivery}</span>
                </div>
              </Card>
            )}
          </div>
        </div>
      </div>

      {/* Диалог выбора медиа */}
      <MediaPickerDialog
        open={mediaPickerOpen}
        onOpenChange={setMediaPickerOpen}
        onSelect={(m) => {
          addAttachmentMutation.mutate(m.id)
          setMediaPickerOpen(false)
        }}
      />

      {/* Диалог быстрого импорта ключей */}
      <Dialog open={quickImportOpen} onOpenChange={setQuickImportOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <KeyRound className="size-5 text-primary" /> Быстрый импорт ключей
            </DialogTitle>
            <DialogDescription>
              Добавление ключей для услуги «{name}».
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3 py-2">
            <Textarea
              rows={6}
              value={quickImportText}
              onChange={(e) => setQuickImportText(e.target.value)}
              placeholder={"По одному ключу на строку\nKEY-AAAA-1111\nKEY-BBBB-2222"}
              className="font-mono text-xs"
            />

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
              <FileUp className="size-4" /> Загрузить файл (.txt)
            </Button>
          </div>

          <DialogFooter>
            <Button variant="ghost" onClick={() => setQuickImportOpen(false)}>
              Отмена
            </Button>
            <Button
              disabled={!quickImportText.trim() || quickImportMutation.isPending}
              onClick={() => quickImportMutation.mutate()}
            >
              {quickImportMutation.isPending ? "Импорт…" : "Импортировать"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Диалог подтверждения удаления услуги */}
      <Dialog open={deleteConfirmOpen} onOpenChange={setDeleteConfirmOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Удалить услугу?</DialogTitle>
            <DialogDescription>
              Услуга «{name}» и все привязанные к ней данные будут удалены безвозвратно.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDeleteConfirmOpen(false)}>
              Отмена
            </Button>
            <Button
              variant="destructive"
              disabled={deleteMutation.isPending}
              onClick={() => deleteMutation.mutate()}
            >
              {deleteMutation.isPending ? "Удаление…" : "Удалить"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
