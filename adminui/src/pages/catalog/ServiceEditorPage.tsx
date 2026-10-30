import { useEffect, useMemo, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate, useParams, Link } from "react-router-dom"
import {
  ArrowLeft,
  Check,
  AlertCircle,
  Coins,
  FileCode2,
  FileUp,
  Info,
  KeyRound,
  Layers,
  Package,
  Plus,
  Save,
  Sliders,
  Sparkles,
  Trash2,
  XCircle,
  SlidersHorizontal,
  Code2,
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
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/shadsnui/tooltip"
import { CatalogTreeSelect, type CatalogItem } from "@/components/common/CatalogTreeSelect"
import { LuaScriptSelect } from "@/components/common/LuaScriptSelect"
import { CurrencySelect } from "@/components/common/CurrencySelect"
import { KeySecretEditor } from "@/components/common/forms/KeySecretEditor"
import { MediaPickerDialog } from "@/components/media/MediaPickerDialog"
import { ServiceMediaWidget } from "@/components/media/ServiceMediaWidget"
import { useInstanceCurrency } from "@/lib/currency"
import { toastError, toastSuccess } from "@/lib/toast"

export type PriceType = "fixed" | "custom" | "tiered" | "configurable"
export type DurationUnit = "minutes" | "hours" | "days" | "months"

export interface FlatTierPlan {
  code: string
  title: string
  price: string
  durationValue: string
  durationUnit: DurationUnit
  group?: string
  settings_override?: Record<string, unknown>
}

export interface ComponentOption {
  value: string
  label: string
  price_delta: string
}

export interface ConfigurableComponent {
  code: string
  name: string
  type: string
  unit: string
  unit_price: string
  min?: string
  max?: string
  step?: string
  default: string
  path: string
  options?: ComponentOption[]
}

interface ServiceAdmin {
  id: number
  slug: string
  name: string
  description: string | null
  catalog_id: number | null
  price: string
  currency: string
  price_type?: PriceType
  pricing_config?: Record<string, unknown>
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

function InfoTip({ content }: { content: React.ReactNode }) {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger
          className="inline-flex items-center justify-center text-muted-foreground/70 hover:text-foreground transition-colors p-0.5 rounded-full cursor-help"
          onClick={(e: React.MouseEvent) => e.stopPropagation()}
        >
          <Info className="size-3.5" />
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-xs text-xs font-normal leading-relaxed">
          {content}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}

function parseDurationSeconds(sec: number | null | undefined, days: number | null | undefined): { val: string; unit: DurationUnit } {
  if (sec !== null && sec !== undefined && sec > 0) {
    if (sec % (30 * 86400) === 0) {
      return { val: String(sec / (30 * 86400)), unit: "months" }
    }
    if (sec % 86400 === 0) {
      return { val: String(sec / 86400), unit: "days" }
    }
    if (sec % 3600 === 0) {
      return { val: String(sec / 3600), unit: "hours" }
    }
    if (sec % 60 === 0) {
      return { val: String(sec / 60), unit: "minutes" }
    }
    return { val: String(sec), unit: "days" }
  }
  if (days !== null && days !== undefined && days > 0) {
    return { val: String(days), unit: "days" }
  }
  return { val: "", unit: "days" }
}

function toDurationSeconds(valStr: string, unit: DurationUnit): { seconds?: number; days?: number } {
  const v = valStr.trim()
  if (!v) return {}
  const n = parseInt(v, 10)
  if (isNaN(n) || n <= 0) return {}

  if (unit === "minutes") return { seconds: n * 60 }
  if (unit === "hours") return { seconds: n * 3600 }
  if (unit === "days") return { seconds: n * 86400, days: n }
  if (unit === "months") return { seconds: n * 30 * 86400, days: n * 30 }
  return { seconds: n * 86400, days: n }
}

function normalizeJson(str?: string | null): string {
  if (!str) return "{}"
  try {
    return JSON.stringify(JSON.parse(str))
  } catch {
    return str.trim()
  }
}

function normalizePrice(val?: string | number | null): string {
  if (val === null || val === undefined || val === "") return "0"
  const n = parseFloat(String(val))
  return isNaN(n) ? String(val).trim() : String(n)
}

function buildServiceSnapshot(data: {
  name: string
  slug: string
  description?: string | null
  catalogId?: number | null
  price?: string | number | null
  currency?: string | null
  priceType: PriceType
  customMin?: string | null
  customMax?: string | null
  customStep?: string | null
  tierPlans?: FlatTierPlan[]
  compList?: ConfigurableComponent[]
  delivery?: "key" | "lua"
  luaScriptId?: string | number | null
  isActive: boolean
  paramsText?: string | null
  settingsText?: string | null
}) {
  const pType = data.priceType || "fixed"
  const delivery = data.delivery || "key"

  return JSON.stringify({
    name: (data.name || "").trim(),
    slug: (data.slug || "").trim(),
    description: (data.description || "").trim(),
    catalogId: data.catalogId ? Number(data.catalogId) : null,
    price: pType === "tiered" || pType === "custom" ? "" : normalizePrice(data.price),
    currency: (data.currency || "RUB").toUpperCase().trim(),
    priceType: pType,
    customMin: pType === "custom" ? normalizePrice(data.customMin ?? "100") : "",
    customMax: pType === "custom" ? normalizePrice(data.customMax ?? "5000") : "",
    customStep: pType === "custom" ? normalizePrice(data.customStep ?? "") : "",
    tierPlans:
      pType === "tiered"
        ? (data.tierPlans || []).map((t) => ({
            code: (t.code || "").trim(),
            title: (t.title || "").trim(),
            price: normalizePrice(t.price),
            durationValue: (t.durationValue || "1").trim(),
            durationUnit: t.durationUnit,
            group: t.group?.trim() || undefined,
            settings_override: t.settings_override || undefined,
          }))
        : [],
    compList: pType === "configurable" ? data.compList || [] : [],
    delivery,
    luaScriptId: delivery === "lua" && data.luaScriptId ? String(data.luaScriptId).trim() : "",
    isActive: Boolean(data.isActive),
    paramsText: normalizeJson(data.paramsText),
    settingsText: normalizeJson(data.settingsText),
  })
}

export function ServiceEditorPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { can } = useAuth()
  const qc = useQueryClient()

  const isNew = !id || id === "new"
  const serviceId = isNew ? null : Number(id)

  // Данные услуги
  const { data: service, isLoading: isServiceLoading } = useQuery({
    queryKey: ["admin-service", serviceId],
    queryFn: async () => (await api.get<ServiceAdmin>(`/v1/admin/services/${serviceId}`)).data,
    enabled: Boolean(serviceId && Number.isFinite(serviceId)),
  })

  // Список каталогов (древовидный)
  const { data: catalogs } = useQuery({
    queryKey: ["admin-catalogs"],
    queryFn: async () => (await api.get<CatalogItem[]>("/v1/admin/catalogs")).data,
    staleTime: 60_000,
  })

  // Вложения
  const { data: attachments } = useQuery({
    queryKey: ["admin-service-attachments", serviceId],
    queryFn: async () => (await api.get<Attachment[]>(`/v1/admin/services/${serviceId}/attachments`)).data,
    enabled: Boolean(serviceId),
  })

  // Остаток ключей
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

  // Состояние основной информации
  const [name, setName] = useState("")
  const [slug, setSlug] = useState("")
  const [description, setDescription] = useState("")
  const [catalogId, setCatalogId] = useState<number | null>(null)
  const [price, setPrice] = useState("0")
  const { currency: instanceCurrency } = useInstanceCurrency()
  const [currency, setCurrency] = useState("RUB")

  // Режим ценообразования
  const [priceType, setPriceType] = useState<PriceType>("fixed")

  // Режим: Custom
  const [customMin, setCustomMin] = useState("100")
  const [customMax, setCustomMax] = useState("5000")
  const [customStep, setCustomStep] = useState("1")

  // Режим: Tiered
  const [tierPlans, setTierPlans] = useState<FlatTierPlan[]>([])

  // Режим: Configurable
  const [compList, setCompList] = useState<ConfigurableComponent[]>([])
  const [expandedTechComps, setExpandedTechComps] = useState<Record<number, boolean>>({})

  // Выдача и скрипты
  const [delivery, setDelivery] = useState<"key" | "lua">("key")
  const [luaScriptId, setLuaScriptId] = useState<string>("")
  const [isActive, setIsActive] = useState(true)
  const [paramsText, setParamsText] = useState("{}")
  const [settingsText, setSettingsText] = useState("{}")
  const [slugManuallyEdited, setSlugManuallyEdited] = useState(false)
  const [hasSubmitted, setHasSubmitted] = useState(false)

  // Модальные окна
  const [mediaPickerOpen, setMediaPickerOpen] = useState(false)
  const [quickImportOpen, setQuickImportOpen] = useState(false)
  const [quickImportText, setQuickImportText] = useState("")
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false)
  const [deleteConfirmSlug, setDeleteConfirmSlug] = useState("")
  const [leaveConfirmOpen, setLeaveConfirmOpen] = useState(false)

  // Графические диалоги редактора JSON (на базе KeySecretEditor)
  const [jsonModalConfig, setJsonModalConfig] = useState<{
    open: boolean
    title: string
    description?: string
    text: string
    target: "params" | "settings" | { tierIdx: number }
  }>({
    open: false,
    title: "",
    text: "{}",
    target: "params",
  })

  const fileInputRef = useRef<HTMLInputElement>(null)
  const [initialSnapshot, setInitialSnapshot] = useState<string>("")
  const initializedServiceIdRef = useRef<number | null>(null)

  // Заполнение валюты по умолчанию для новой услуги
  useEffect(() => {
    if (isNew && instanceCurrency && !initialSnapshot) {
      setCurrency(instanceCurrency)
    }
  }, [isNew, instanceCurrency, initialSnapshot])

  // Заполнение полей при загрузке существующей услуги
  useEffect(() => {
    if (service) {
      if (initializedServiceIdRef.current === service.id) {
        return
      }
      initializedServiceIdRef.current = service.id

      setName(service.name)
      setSlug(service.slug)
      setDescription(service.description ?? "")
      setCatalogId(service.catalog_id ?? null)
      setPrice(service.price)
      setCurrency(service.currency)
      const pType = service.price_type || "fixed"
      setPriceType(pType)
      setDelivery(service.delivery as "key" | "lua")
      const scriptIdStr = service.lua_script_id ? String(service.lua_script_id) : ""
      setLuaScriptId(scriptIdStr)
      setIsActive(service.is_active)
      const pText = JSON.stringify(service.params || {}, null, 2)
      const sText = JSON.stringify(service.settings || {}, null, 2)
      setParamsText(pText)
      setSettingsText(sText)
      setSlugManuallyEdited(true)

      let loadedMin = "100"
      let loadedMax = "5000"
      let loadedStep = "50"
      let loadedTiers: FlatTierPlan[] = []
      let loadedComps: ConfigurableComponent[] = []

      const cfg = (service.pricing_config || {}) as Record<string, unknown>
      if (pType === "custom") {
        loadedMin = String(cfg.min ?? "100")
        loadedMax = String(cfg.max ?? "5000")
        loadedStep = cfg.step ? String(cfg.step) : ""
      } else if (pType === "tiered") {
        const rawTiers = (cfg.tiers as unknown[]) || []
        const flat: FlatTierPlan[] = []
        for (const item of rawTiers) {
          const t = item as Record<string, unknown>
          if (Array.isArray(t.subtiers)) {
            const grpTitle = String(t.title || "")
            for (const sub of t.subtiers as Record<string, unknown>[]) {
              const dur = parseDurationSeconds(
                sub.duration_seconds !== undefined ? Number(sub.duration_seconds) : undefined,
                sub.duration_days !== undefined ? Number(sub.duration_days) : undefined
              )
              flat.push({
                code: String(sub.code || ""),
                title: String(sub.title || ""),
                price: String(sub.price || "0"),
                durationValue: dur.val,
                durationUnit: dur.unit,
                group: grpTitle || undefined,
                settings_override: (sub.settings_override as Record<string, unknown>) || undefined,
              })
            }
          } else {
            const dur = parseDurationSeconds(
              t.duration_seconds !== undefined ? Number(t.duration_seconds) : undefined,
              t.duration_days !== undefined ? Number(t.duration_days) : undefined
            )
            flat.push({
              code: String(t.code || ""),
              title: String(t.title || ""),
              price: String(t.price || "0"),
              durationValue: dur.val,
              durationUnit: dur.unit,
              group: t.group ? String(t.group) : undefined,
              settings_override: (t.settings_override as Record<string, unknown>) || undefined,
            })
          }
        }
        loadedTiers = flat
      } else if (pType === "configurable") {
        loadedComps = (cfg.components as ConfigurableComponent[]) || []
      }

      setCustomMin(loadedMin)
      setCustomMax(loadedMax)
      setCustomStep(loadedStep)
      setTierPlans(loadedTiers)
      setCompList(loadedComps)

      const initial = buildServiceSnapshot({
        name: service.name,
        slug: service.slug,
        description: service.description ?? "",
        catalogId: service.catalog_id ?? null,
        price: service.price,
        currency: service.currency,
        priceType: pType,
        customMin: loadedMin,
        customMax: loadedMax,
        customStep: loadedStep,
        tierPlans: loadedTiers,
        compList: loadedComps,
        delivery: service.delivery as "key" | "lua",
        luaScriptId: scriptIdStr,
        isActive: service.is_active,
        paramsText: pText,
        settingsText: sText,
      })

      setInitialSnapshot(initial)
    } else if (isNew && !initialSnapshot) {
      const initial = buildServiceSnapshot({
        name: "",
        slug: "",
        description: "",
        catalogId: null,
        price: "0",
        currency: instanceCurrency || "RUB",
        priceType: "fixed",
        customMin: "100",
        customMax: "5000",
        customStep: "1",
        tierPlans: [],
        compList: [],
        delivery: "key",
        luaScriptId: "",
        isActive: true,
        paramsText: "{}",
        settingsText: "{}",
      })
      setInitialSnapshot(initial)
    }
  }, [service, isNew, instanceCurrency, initialSnapshot])

  // Автоматический пересчет цены в зависимости от режима
  const calculatedBasePrice = useMemo(() => {
    if (priceType === "tiered") {
      const validPrices = tierPlans
        .map((p) => parseFloat(p.price))
        .filter((n) => !isNaN(n) && n > 0)
      return validPrices.length > 0 ? String(Math.min(...validPrices)) : "0"
    }
    if (priceType === "custom") {
      return customMin || "0"
    }
    return price
  }, [priceType, tierPlans, customMin, price])

  // Переключение типа цены: для не-fixed режимов выдача key невозможна -> переключаем на lua
  const handlePriceTypeChange = (newType: PriceType) => {
    setPriceType(newType)
    if (newType !== "fixed" && delivery === "key") {
      setDelivery("lua")
    }
  }

  // Текущий снапшот формы
  const currentSnapshot = useMemo(() => {
    return buildServiceSnapshot({
      name,
      slug,
      description,
      catalogId,
      price: priceType === "tiered" || priceType === "custom" ? calculatedBasePrice : price,
      currency,
      priceType,
      customMin,
      customMax,
      customStep,
      tierPlans,
      compList,
      delivery,
      luaScriptId,
      isActive,
      paramsText,
      settingsText,
    })
  }, [
    name,
    slug,
    description,
    catalogId,
    price,
    currency,
    priceType,
    calculatedBasePrice,
    customMin,
    customMax,
    customStep,
    tierPlans,
    compList,
    delivery,
    luaScriptId,
    isActive,
    paramsText,
    settingsText,
  ])

  const isDirty = useMemo(() => {
    if (!initialSnapshot) return false
    return currentSnapshot !== initialSnapshot
  }, [initialSnapshot, currentSnapshot])

  // Защита от закрытия вкладки
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (isDirty) {
        e.preventDefault()
        e.returnValue = ""
      }
    }
    window.addEventListener("beforeunload", handleBeforeUnload)
    return () => window.removeEventListener("beforeunload", handleBeforeUnload)
  }, [isDirty])

  // Автогенерация slug для новой услуги
  const handleNameChange = (val: string) => {
    setName(val)
    if (isNew && !slugManuallyEdited) {
      setSlug(translit(val))
    }
  }

  // Инлайн валидация формы
  const validationErrors = useMemo(() => {
    const errors: Record<string, string> = {}

    if (!name.trim()) errors.name = "Название услуги обязательно"
    if (!slug.trim()) errors.slug = "Slug обязателен"

    // Цена
    if (priceType === "fixed" || priceType === "configurable") {
      const numPrice = parseFloat(price)
      if (isNaN(numPrice) || numPrice < 0) {
        errors.price = "Цена не может быть отрицательной"
      }
    }

    // Custom
    if (priceType === "custom") {
      const minN = parseFloat(customMin)
      const maxN = parseFloat(customMax)
      if (isNaN(minN) || minN <= 0) {
        errors.customMin = "Мин. сумма должна быть больше 0"
      }
      if (isNaN(maxN) || maxN <= 0) {
        errors.customMax = "Макс. сумма должна быть больше 0"
      } else if (!isNaN(minN) && maxN < minN) {
        errors.customMax = "Максимум не может быть меньше минимума"
      }
      if (customStep.trim()) {
        const stepN = parseFloat(customStep)
        if (isNaN(stepN) || stepN <= 0) {
          errors.customStep = "Шаг должен быть больше 0"
        } else if (!isNaN(minN) && !isNaN(maxN) && maxN > minN) {
          if (stepN > maxN - minN) {
            errors.customStep = "Шаг не может превышать разницу между максимумом и минимумом"
          } else {
            const rangeCents = Math.round((maxN - minN) * 100)
            const stepCents = Math.round(stepN * 100)
            if (rangeCents % stepCents !== 0) {
              errors.customStep = `Диапазон (${(maxN - minN).toFixed(2)}) не делится нацело на шаг ${stepN}`
            }
          }
        }
      }
    }

    // Tiered
    if (priceType === "tiered") {
      if (tierPlans.length === 0) {
        errors.tiers = "Добавьте хотя бы один тарифный план"
      } else {
        tierPlans.forEach((plan, idx) => {
          if (!plan.title.trim()) errors[`tier_${idx}_title`] = "Укажите название"
          if (!plan.code.trim()) errors[`tier_${idx}_code`] = "Укажите код"
          const p = parseFloat(plan.price)
          if (isNaN(p) || p <= 0) errors[`tier_${idx}_price`] = "Цена должна быть > 0"
        })
      }
    }

    // Configurable
    if (priceType === "configurable") {
      if (compList.length === 0) {
        errors.configurable = "Добавьте хотя бы один компонент"
      } else {
        compList.forEach((comp, idx) => {
          if (!comp.name.trim()) errors[`comp_${idx}_name`] = "Укажите название"
          if (!comp.code.trim()) errors[`comp_${idx}_code`] = "Укажите код"
          const up = parseFloat(comp.unit_price)
          if (isNaN(up) || up < 0) errors[`comp_${idx}_price`] = "Цена не может быть < 0"
        })
      }
    }

    // Delivery
    if (delivery === "lua" && !luaScriptId) {
      errors.delivery = "Выберите скрипт автоматизации для доставки"
    }

    return errors
  }, [
    name,
    slug,
    price,
    priceType,
    customMin,
    customMax,
    customStep,
    tierPlans,
    compList,
    delivery,
    luaScriptId,
  ])

  const hasErrors = Object.keys(validationErrors).length > 0

  // Мутация сохранения
  const saveMutation = useMutation({
    mutationFn: async () => {
      if (hasErrors) {
        const firstErr = Object.values(validationErrors)[0]
        throw new Error(`Проверьте форму: ${firstErr}`)
      }

      let params: unknown = {}
      let settings: unknown = {}
      try {
        params = JSON.parse(paramsText || "{}")
        settings = JSON.parse(settingsText || "{}")
      } catch {
        throw new Error("Некорректный JSON в параметрах или настройках")
      }

      let pricingConfig: Record<string, unknown> = {}
      if (priceType === "custom") {
        pricingConfig = {
          min: customMin,
          max: customMax,
          step: customStep.trim() ? customStep.trim() : undefined,
        }
      } else if (priceType === "tiered") {
        const backendTiers = tierPlans.map((tp) => {
          const dur = toDurationSeconds(tp.durationValue, tp.durationUnit)
          return {
            code: tp.code,
            title: tp.title,
            price: tp.price,
            duration_days: dur.days,
            duration_seconds: dur.seconds,
            group: tp.group || undefined,
            settings_override: tp.settings_override,
          }
        })
        pricingConfig = {
          tiers: backendTiers,
        }
      } else if (priceType === "configurable") {
        pricingConfig = {
          components: compList,
        }
      }

      const effectivePrice =
        priceType === "tiered" || priceType === "custom" ? calculatedBasePrice : price

      const payload = {
        name,
        description: description || null,
        catalog_id: catalogId,
        price: effectivePrice,
        currency,
        price_type: priceType,
        pricing_config: pricingConfig,
        delivery,
        lua_script_id: delivery === "lua" && luaScriptId ? Number(luaScriptId) : null,
        params,
        settings,
        is_active: isActive,
      }

      if (isNew) {
        return (await api.post("/v1/admin/services", { ...payload, slug })).data
      } else {
        return (await api.patch(`/v1/admin/services/${serviceId}`, payload)).data
      }
    },
    onSuccess: (data: ServiceAdmin) => {
      toastSuccess(isNew ? "Услуга успешно создана" : "Изменения сохранены")
      data.warnings?.forEach((w) => toastError("Предупреждение", w))
      setInitialSnapshot(currentSnapshot)
      void qc.invalidateQueries({ queryKey: ["admin-services"] })
      if (isNew) {
        navigate(`/services/${data.id}`, { replace: true })
      } else {
        void qc.invalidateQueries({ queryKey: ["admin-service", serviceId] })
      }
    },
    onError: (e) => {
      const detail = getErrorDetail(e)
      toastError("Ошибка сохранения", detail || (e as Error).message)
    },
  })

  const handleSave = () => {
    setHasSubmitted(true)
    if (hasErrors) {
      const firstErr = Object.values(validationErrors)[0]
      toastError("Проверьте форму", firstErr || "Заполните обязательные поля")
      return
    }
    saveMutation.mutate()
  }

  // Быстрое сохранение Ctrl+S
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault()
        if (isDirty || isNew) {
          handleSave()
        }
      }
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [isDirty, isNew, hasErrors, validationErrors])

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

  // Быстрый импорт ключей
  const quickImportMutation = useMutation({
    mutationFn: async () => {
      const values = quickImportText.split("\n").map((v) => v.trim()).filter(Boolean)
      return (await api.post(`/v1/admin/services/${serviceId}/keys/import`, { values })).data
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

  // Навигация назад
  const handleBack = () => {
    if (isDirty) {
      setLeaveConfirmOpen(true)
    } else {
      navigate("/services")
    }
  }

  // Подсчет настроенных параметров в JSON
  const paramsCount = useMemo(() => {
    try {
      const obj = JSON.parse(paramsText || "{}")
      return Object.keys(obj).length
    } catch {
      return 0
    }
  }, [paramsText])

  const settingsCount = useMemo(() => {
    try {
      const obj = JSON.parse(settingsText || "{}")
      return Object.keys(obj).length
    } catch {
      return 0
    }
  }, [settingsText])

  if (!isNew && isServiceLoading) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
        Загрузка параметров услуги…
      </div>
    )
  }

  return (
    <div className="space-y-6 max-w-6xl mx-auto pb-16">
      {/* Верхний бар навигации */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b pb-4">
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="icon"
            className="size-9 rounded-xl border hover:bg-muted"
            onClick={handleBack}
            title="Назад к списку услуг"
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
              {!isNew && !isDirty && (
                <span className="inline-flex items-center gap-1 text-[11px] text-emerald-600 bg-emerald-500/10 px-2 py-0.5 rounded-full font-medium">
                  <Check className="size-3" /> Сохранено
                </span>
              )}
              {isDirty && (
                <span className="inline-flex items-center gap-1 text-[11px] text-amber-600 bg-amber-500/10 px-2 py-0.5 rounded-full font-medium">
                  Есть несохраненные изменения
                </span>
              )}
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              {isNew
                ? "Заполните реквизиты, настройте ценообразование и выберите способ автоматической выдачи."
                : `ID товара: #${serviceId}`}
            </p>
          </div>
        </div>

        {/* Кнопка сохранения в шапке */}
        <div className="flex items-center gap-2">
          {(isDirty || isNew) ? (
            <Button
              onClick={handleSave}
              disabled={saveMutation.isPending}
              className="gap-2 shadow-xs transition-all"
            >
              <Save className="size-4" />
              {saveMutation.isPending ? "Сохранение…" : isNew ? "Создать услугу" : "Сохранить"}
              <kbd className="hidden sm:inline-block ml-1 px-1.5 py-0.5 text-[10px] font-mono bg-primary-foreground/20 rounded">
                Ctrl+S
              </kbd>
            </Button>
          ) : (
            <div className="hidden sm:flex items-center gap-1.5 text-xs text-muted-foreground px-3 py-1.5 border rounded-lg bg-muted/20">
              <Check className="size-3.5 text-emerald-500" /> Все изменения сохранены
            </div>
          )}
        </div>
      </div>

      {/* Основная сетка: единый естественный поток настройки на одной странице */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Левая колонка (2/3) */}
        <div className="space-y-6 lg:col-span-2">

          {/* 1. БЛОК: Основная информация (Название, slug, Каталог, Цена, Валюта, Описание) */}
          <Card className="bg-card/90 shadow-2xs border-border/80">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <Package className="size-4 text-primary" /> Основная информация
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label>Название услуги *</Label>
                  <Input
                    value={name}
                    onChange={(e) => handleNameChange(e.target.value)}
                    placeholder="Название услуги"
                    className={hasSubmitted && validationErrors.name ? "border-destructive focus-visible:ring-destructive" : ""}
                  />
                  {hasSubmitted && validationErrors.name && (
                    <p className="text-[11px] text-destructive flex items-center gap-1">
                      <AlertCircle className="size-3" /> {validationErrors.name}
                    </p>
                  )}
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
                    placeholder="slug-uslugi"
                    className={`font-mono text-xs ${hasSubmitted && validationErrors.slug ? "border-destructive focus-visible:ring-destructive" : ""}`}
                  />
                  {hasSubmitted && validationErrors.slug && (
                    <p className="text-[11px] text-destructive flex items-center gap-1">
                      <AlertCircle className="size-3" /> {validationErrors.slug}
                    </p>
                  )}
                </div>
              </div>

              <div className="grid gap-4 sm:grid-cols-3">
                {/* Кастомный древовидный селектор каталогов */}
                <div className="space-y-1.5 sm:col-span-1">
                  <Label>Каталог</Label>
                  <CatalogTreeSelect
                    catalogs={catalogs}
                    value={catalogId}
                    onChange={setCatalogId}
                  />
                </div>

                {/* Базовая цена: активна для fixed/configurable, неактивна для tiered/custom */}
                <div className="space-y-1.5 sm:col-span-1">
                  <Label>
                    {priceType === "fixed"
                      ? "Цена *"
                      : priceType === "configurable"
                      ? "Базовая цена («от») *"
                      : "Цена в каталоге («от»)"}
                  </Label>
                  <Input
                    type="number"
                    min="0"
                    step="0.01"
                    disabled={priceType === "tiered" || priceType === "custom"}
                    value={priceType === "tiered" || priceType === "custom" ? calculatedBasePrice : price}
                    onChange={(e) => setPrice(e.target.value)}
                    placeholder="0.00"
                    className={`font-mono text-xs ${
                      hasSubmitted && validationErrors.price ? "border-destructive focus-visible:ring-destructive" : ""
                    } ${priceType === "tiered" || priceType === "custom" ? "bg-muted/40 cursor-not-allowed text-muted-foreground" : ""}`}
                  />
                  {hasSubmitted && validationErrors.price && (
                    <p className="text-[11px] text-destructive flex items-center gap-1">
                      <AlertCircle className="size-3" /> {validationErrors.price}
                    </p>
                  )}
                </div>

                <div className="space-y-1.5 sm:col-span-1">
                  <Label>Валюта *</Label>
                  <CurrencySelect
                    value={currency}
                    onChange={setCurrency}
                    placeholder={instanceCurrency || "RUB"}
                  />
                </div>
              </div>

              {/* Описание товара прямо в основных параметрах */}
              <div className="space-y-1.5 pt-2 border-t border-border/50">
                <Label>Описание товара</Label>
                <Textarea
                  rows={4}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Описание товара, характеристики или инструкция по активации…"
                  className="leading-relaxed text-sm resize-y"
                />
              </div>
            </CardContent>
          </Card>

          {/* 2. БЛОК: Режим ценообразования */}
          <Card className="bg-card/90 shadow-2xs border-border/80">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold flex items-center justify-between">
                <span className="flex items-center gap-2">
                  <Coins className="size-4 text-primary" /> Режим ценообразования
                </span>
                <Badge variant="outline" className="text-[10px] font-mono uppercase">
                  {priceType}
                </Badge>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              {/* 4 карточки выбора режима */}
              <div className="grid gap-3 grid-cols-2 lg:grid-cols-4">
                {/* 1. Фиксированная */}
                <div
                  onClick={() => handlePriceTypeChange("fixed")}
                  className={`p-3.5 rounded-xl border cursor-pointer transition-all flex items-center justify-between min-h-[56px] select-none ${
                    priceType === "fixed"
                      ? "border-primary bg-primary/5 shadow-xs ring-1 ring-primary/40"
                      : "border-border/70 hover:border-border hover:bg-muted/40"
                  }`}
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <div
                      className={`size-7 rounded-lg flex items-center justify-center shrink-0 ${
                        priceType === "fixed"
                          ? "bg-primary text-primary-foreground"
                          : "bg-muted text-muted-foreground"
                      }`}
                    >
                      <Coins className="size-3.5" />
                    </div>
                    <span className="font-semibold text-xs text-foreground whitespace-nowrap">
                      Фиксированная
                    </span>
                  </div>
                  <InfoTip content="Единая постоянная цена на товар или услугу. Подходит для классических товаров, разовых покупок и выдачи ключей из пула." />
                </div>

                {/* 2. Произвольная */}
                <div
                  onClick={() => handlePriceTypeChange("custom")}
                  className={`p-3.5 rounded-xl border cursor-pointer transition-all flex items-center justify-between min-h-[56px] select-none ${
                    priceType === "custom"
                      ? "border-primary bg-primary/5 shadow-xs ring-1 ring-primary/40"
                      : "border-border/70 hover:border-border hover:bg-muted/40"
                  }`}
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <div
                      className={`size-7 rounded-lg flex items-center justify-center shrink-0 ${
                        priceType === "custom"
                          ? "bg-primary text-primary-foreground"
                          : "bg-muted text-muted-foreground"
                      }`}
                    >
                      <Sparkles className="size-3.5" />
                    </div>
                    <span className="font-semibold text-xs text-foreground whitespace-nowrap">
                      Произвольная
                    </span>
                  </div>
                  <InfoTip content="Покупатель самостоятельно вводит желаемую сумму пополнения, доната или депозита в заданном диапазоне." />
                </div>

                {/* 3. Тарифные планы */}
                <div
                  onClick={() => handlePriceTypeChange("tiered")}
                  className={`p-3.5 rounded-xl border cursor-pointer transition-all flex items-center justify-between min-h-[56px] select-none ${
                    priceType === "tiered"
                      ? "border-primary bg-primary/5 shadow-xs ring-1 ring-primary/40"
                      : "border-border/70 hover:border-border hover:bg-muted/40"
                  }`}
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <div
                      className={`size-7 rounded-lg flex items-center justify-center shrink-0 ${
                        priceType === "tiered"
                          ? "bg-primary text-primary-foreground"
                          : "bg-muted text-muted-foreground"
                      }`}
                    >
                      <Layers className="size-3.5" />
                    </div>
                    <span className="font-semibold text-xs text-foreground whitespace-nowrap">
                      Тарифные планы
                    </span>
                  </div>
                  <InfoTip content="Подписочная система с набором готовых тарифных планов по срокам (часы, дни, месяцы) или уровням подписки." />
                </div>

                {/* 4. Конфигуратор */}
                <div
                  onClick={() => handlePriceTypeChange("configurable")}
                  className={`p-3.5 rounded-xl border cursor-pointer transition-all flex items-center justify-between min-h-[56px] select-none ${
                    priceType === "configurable"
                      ? "border-primary bg-primary/5 shadow-xs ring-1 ring-primary/40"
                      : "border-border/70 hover:border-border hover:bg-muted/40"
                  }`}
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <div
                      className={`size-7 rounded-lg flex items-center justify-center shrink-0 ${
                        priceType === "configurable"
                          ? "bg-primary text-primary-foreground"
                          : "bg-muted text-muted-foreground"
                      }`}
                    >
                      <Sliders className="size-3.5" />
                    </div>
                    <span className="font-semibold text-xs text-foreground whitespace-nowrap">
                      Конфигуратор
                    </span>
                  </div>
                  <InfoTip content="Калькулятор ресурсов с динамическим расчетом стоимости выбранных компонентов." />
                </div>
              </div>

              {/* Секция: Фиксированная — нет лишней пустой рамки! */}

              {/* Секция: Произвольная сумма */}
              {priceType === "custom" && (
                <div className="space-y-3 rounded-xl border border-border/80 bg-muted/20 p-4">
                  <h4 className="text-xs font-semibold text-foreground">Диапазон произвольной суммы</h4>
                  <div className="grid gap-3 sm:grid-cols-3">
                    <div className="space-y-1.5">
                      <Label className="text-xs">Мин. сумма ({currency}) *</Label>
                      <Input
                        type="number"
                        min="0.01"
                        step="0.01"
                        value={customMin}
                        onChange={(e) => setCustomMin(e.target.value)}
                        className={`font-mono text-xs ${
                          hasSubmitted && validationErrors.customMin ? "border-destructive focus-visible:ring-destructive" : ""
                        }`}
                      />
                      {hasSubmitted && validationErrors.customMin && (
                        <p className="text-[11px] text-destructive flex items-center gap-1">
                          <AlertCircle className="size-3" /> {validationErrors.customMin}
                        </p>
                      )}
                    </div>

                    <div className="space-y-1.5">
                      <Label className="text-xs">Макс. сумма ({currency}) *</Label>
                      <Input
                        type="number"
                        min="0.01"
                        step="0.01"
                        value={customMax}
                        onChange={(e) => setCustomMax(e.target.value)}
                        className={`font-mono text-xs ${
                          hasSubmitted && validationErrors.customMax ? "border-destructive focus-visible:ring-destructive" : ""
                        }`}
                      />
                      {hasSubmitted && validationErrors.customMax && (
                        <p className="text-[11px] text-destructive flex items-center gap-1">
                          <AlertCircle className="size-3" /> {validationErrors.customMax}
                        </p>
                      )}
                    </div>

                    <div className="space-y-1.5">
                      <Label className="text-xs">Шаг суммы (step)</Label>
                      <Input
                        type="number"
                        min="0.01"
                        step="0.01"
                        value={customStep}
                        onChange={(e) => setCustomStep(e.target.value)}
                        placeholder="Опционально"
                        className={`font-mono text-xs ${
                          hasSubmitted && validationErrors.customStep ? "border-destructive focus-visible:ring-destructive" : ""
                        }`}
                      />
                      {hasSubmitted && validationErrors.customStep && (
                        <p className="text-[11px] text-destructive flex items-center gap-1">
                          <AlertCircle className="size-3" /> {validationErrors.customStep}
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* Секция: Тарифные планы (плоский список) */}
              {priceType === "tiered" && (
                <div className="space-y-3 rounded-xl border border-border/80 bg-muted/20 p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <h4 className="text-xs font-semibold text-foreground">Тарифные планы</h4>
                      <p className="text-[11px] text-muted-foreground">
                        Покупатель выбирает один из предложенных вариантов при оформлении заказа.
                      </p>
                    </div>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="h-7 text-xs gap-1"
                      onClick={() => {
                        setTierPlans([
                          ...tierPlans,
                          {
                            code: "",
                            title: "",
                            price: "",
                            durationValue: "",
                            durationUnit: "days",
                          },
                        ])
                      }}
                    >
                      <Plus className="size-3" /> Добавить тариф
                    </Button>
                  </div>

                  {hasSubmitted && validationErrors.tiers && (
                    <p className="text-xs text-destructive flex items-center gap-1">
                      <AlertCircle className="size-3.5" /> {validationErrors.tiers}
                    </p>
                  )}

                  {tierPlans.length === 0 ? (
                    <div className="text-center py-6 border border-dashed rounded-lg bg-card/40">
                      <p className="text-xs text-muted-foreground italic">
                        Тарифные планы пока не добавлены. Нажмите «Добавить тариф».
                      </p>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {tierPlans.map((plan, pIdx) => {
                        const titleErr = hasSubmitted ? validationErrors[`tier_${pIdx}_title`] : undefined
                        const codeErr = hasSubmitted ? validationErrors[`tier_${pIdx}_code`] : undefined
                        const priceErr = hasSubmitted ? validationErrors[`tier_${pIdx}_price`] : undefined

                        return (
                          <div
                            key={pIdx}
                            className="p-3.5 rounded-xl border border-border/70 bg-card/70 space-y-3"
                          >
                            {/* Верхняя строка: Название, Группа (опц.), Код (slug), и действия */}
                            <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
                              {/* Название */}
                              <div className="flex-1 w-full space-y-1">
                                <Label className="text-xs">Название тарифа *</Label>
                                <Input
                                  value={plan.title}
                                  onChange={(e) => {
                                    const next = [...tierPlans]
                                    next[pIdx].title = e.target.value
                                    if (!next[pIdx].code) {
                                      next[pIdx].code = translit(e.target.value)
                                    }
                                    setTierPlans(next)
                                  }}
                                  placeholder="Название тарифа (напр. Базовый, 1 мес., Pro)"
                                  className={`text-xs h-8 ${titleErr ? "border-destructive focus-visible:ring-destructive" : ""}`}
                                />
                                {titleErr && <span className="text-[10px] text-destructive">{titleErr}</span>}
                              </div>

                              {/* Группа (опционально) */}
                              <div className="w-full sm:w-36 space-y-1">
                                <Label className="text-xs text-muted-foreground">Группа (опц.)</Label>
                                <Input
                                  value={plan.group || ""}
                                  onChange={(e) => {
                                    const next = [...tierPlans]
                                    next[pIdx].group = e.target.value
                                    setTierPlans(next)
                                  }}
                                  placeholder="Премиум, СНГ…"
                                  className="text-xs h-8"
                                />
                              </div>

                              {/* Код (slug) */}
                              <div className="w-full sm:w-44 space-y-1">
                                <Label className="text-xs">Код (slug) *</Label>
                                <Input
                                  value={plan.code}
                                  onChange={(e) => {
                                    const next = [...tierPlans]
                                    next[pIdx].code = e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "")
                                    setTierPlans(next)
                                  }}
                                  placeholder="code_tarifa"
                                  className={`font-mono text-xs h-8 ${codeErr ? "border-destructive focus-visible:ring-destructive" : ""}`}
                                />
                                {codeErr && <span className="text-[10px] text-destructive">{codeErr}</span>}
                              </div>

                              {/* Действия */}
                              <div className="flex items-center gap-1 self-end sm:self-center pt-2 sm:pt-5 shrink-0">
                                <Button
                                  type="button"
                                  variant="outline"
                                  size="sm"
                                  title="Настройки тарифа (JSON)"
                                  className={`h-8 px-2.5 text-xs gap-1.5 ${
                                    plan.settings_override && Object.keys(plan.settings_override).length > 0
                                      ? "text-primary border-primary/40 bg-primary/5"
                                      : "text-muted-foreground"
                                  }`}
                                  onClick={() => {
                                    setJsonModalConfig({
                                      open: true,
                                      title: `Настройки тарифа «${plan.title || plan.code || "Новый тариф"}»`,
                                      description: "Переопределения service.settings для данного тарифа",
                                      text: plan.settings_override ? JSON.stringify(plan.settings_override, null, 2) : "{}",
                                      target: { tierIdx: pIdx },
                                    })
                                  }}
                                >
                                  <SlidersHorizontal className="size-3.5" />
                                  <span>
                                    {plan.settings_override && Object.keys(plan.settings_override).length > 0
                                      ? `Настройки (${Object.keys(plan.settings_override).length})`
                                      : "Настройки"}
                                  </span>
                                </Button>
                                <Button
                                  type="button"
                                  variant="ghost"
                                  size="icon"
                                  className="size-8 text-muted-foreground hover:text-destructive"
                                  onClick={() => {
                                    setTierPlans(tierPlans.filter((_, i) => i !== pIdx))
                                  }}
                                >
                                  <Trash2 className="size-3.5" />
                                </Button>
                              </div>
                            </div>

                            {/* Нижняя строка: Цена и Срок действия */}
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2.5 border-t border-border/40">
                              {/* Цена */}
                              <div className="space-y-1">
                                <Label className="text-xs">Цена ({currency}) *</Label>
                                <Input
                                  type="number"
                                  min="0.01"
                                  step="0.01"
                                  value={plan.price}
                                  onChange={(e) => {
                                    const next = [...tierPlans]
                                    next[pIdx].price = e.target.value
                                    setTierPlans(next)
                                  }}
                                  placeholder="0.00"
                                  className={`font-mono text-xs h-8 ${priceErr ? "border-destructive focus-visible:ring-destructive" : ""}`}
                                />
                                {priceErr && <span className="text-[10px] text-destructive">{priceErr}</span>}
                              </div>

                              {/* Срок: изначально пустое поле = «Бессрочно» + выбор единиц (часы/дни/месяцы) */}
                              <div className="space-y-1">
                                <div className="flex items-center justify-between">
                                  <Label className="text-xs">Срок действия</Label>
                                  <span className="text-[10px] text-muted-foreground">Пусто = Навсегда</span>
                                </div>
                                <div className="flex items-center gap-2">
                                  <Input
                                    type="number"
                                    min="1"
                                    value={plan.durationValue}
                                    onChange={(e) => {
                                      const next = [...tierPlans]
                                      next[pIdx].durationValue = e.target.value
                                      setTierPlans(next)
                                    }}
                                    placeholder="Бессрочно (навсегда)"
                                    className="font-mono text-xs h-8 flex-1"
                                  />
                                  <Select
                                    value={plan.durationUnit}
                                    onValueChange={(u) => {
                                      const next = [...tierPlans]
                                      next[pIdx].durationUnit = u as DurationUnit
                                      setTierPlans(next)
                                    }}
                                  >
                                    <SelectTrigger className="h-8 text-xs w-28 px-2 shrink-0">
                                      <SelectValue>
                                        {plan.durationUnit === "hours"
                                          ? "часов"
                                          : plan.durationUnit === "minutes"
                                          ? "минут"
                                          : plan.durationUnit === "months"
                                          ? "мес."
                                          : "дней"}
                                      </SelectValue>
                                    </SelectTrigger>
                                    <SelectContent>
                                      <SelectItem value="days">дней</SelectItem>
                                      <SelectItem value="hours">часов</SelectItem>
                                      <SelectItem value="minutes">минут</SelectItem>
                                      <SelectItem value="months">мес.</SelectItem>
                                    </SelectContent>
                                  </Select>
                                </div>
                              </div>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>
              )}

              {/* Секция: Конфигуратор (чистый дизайн без каши инпутов) */}
              {priceType === "configurable" && (
                <div className="space-y-4 rounded-xl border border-border/80 bg-muted/20 p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <h4 className="text-xs font-semibold text-foreground">Компоненты калькулятора</h4>
                      <p className="text-[11px] text-muted-foreground">
                        Опции и ресурсы, доступные покупателю для конфигурирования.
                      </p>
                    </div>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="h-7 text-xs gap-1"
                      onClick={() => {
                        setCompList([
                          ...compList,
                          {
                            code: "",
                            name: "",
                            type: "slider",
                            unit: "",
                            unit_price: "",
                            min: "",
                            max: "",
                            step: "",
                            default: "",
                            path: "",
                          },
                        ])
                      }}
                    >
                      <Plus className="size-3" /> Добавить опцию
                    </Button>
                  </div>

                  {hasSubmitted && validationErrors.configurable && (
                    <p className="text-xs text-destructive flex items-center gap-1">
                      <AlertCircle className="size-3.5" /> {validationErrors.configurable}
                    </p>
                  )}

                  {compList.length === 0 ? (
                    <div className="text-center py-6 border border-dashed rounded-lg bg-card/40">
                      <p className="text-xs text-muted-foreground italic">
                        Компоненты калькулятора пока не добавлены. Нажмите «Добавить опцию».
                      </p>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {compList.map((comp, cIdx) => (
                        <div key={cIdx} className="rounded-lg border border-border/80 bg-card/60 p-3 space-y-3 text-xs">
                          {/* Верхняя строка: Название, Тип выбора, Удалить */}
                          <div className="grid grid-cols-1 sm:grid-cols-12 gap-2 items-center">
                            <div className="sm:col-span-7 space-y-1">
                              <Label className="text-[10px] text-muted-foreground">Название опции *</Label>
                              <Input
                                value={comp.name}
                                onChange={(e) => {
                                  const next = [...compList]
                                  next[cIdx].name = e.target.value
                                  if (!next[cIdx].code) {
                                    const autoCode = translit(e.target.value)
                                    next[cIdx].code = autoCode
                                    next[cIdx].path = `resources.${autoCode}`
                                  }
                                  setCompList(next)
                                }}
                                placeholder="Название опции"
                                className="text-xs h-8"
                              />
                            </div>

                            <div className="sm:col-span-4 space-y-1">
                              <Label className="text-[10px] text-muted-foreground">Тип выбора</Label>
                              <Select
                                value={comp.type}
                                onValueChange={(v) => {
                                  const next = [...compList]
                                  next[cIdx].type = v || "slider"
                                  setCompList(next)
                                }}
                              >
                                <SelectTrigger className="h-8 text-xs">
                                  <SelectValue>
                                    {comp.type === "slider"
                                      ? "Ползунок (Slider)"
                                      : comp.type === "select"
                                      ? "Список вариантов (Select)"
                                      : comp.type === "switch"
                                      ? "Переключатель Да/Нет (Switch)"
                                      : "Шагомер +/- (Stepper)"}
                                  </SelectValue>
                                </SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="slider">Ползунок (Slider)</SelectItem>
                                  <SelectItem value="select">Список вариантов (Select)</SelectItem>
                                  <SelectItem value="switch">Переключатель Да/Нет (Switch)</SelectItem>
                                  <SelectItem value="stepper">Шагомер +/- (Stepper)</SelectItem>
                                </SelectContent>
                              </Select>
                            </div>

                            <div className="sm:col-span-1 flex justify-end pt-4">
                              <Button
                                type="button"
                                variant="ghost"
                                size="icon"
                                className="size-8 text-muted-foreground hover:text-destructive"
                                onClick={() => {
                                  setCompList(compList.filter((_, i) => i !== cIdx))
                                }}
                              >
                                <Trash2 className="size-3.5" />
                              </Button>
                            </div>
                          </div>

                          {/* Адаптивные поля параметров под выбранный тип контрола */}
                          {comp.type === "switch" ? (
                            /* Переключатель Да/Нет: только доплата к цене */
                            <div className="pt-2 border-t border-border/50 max-w-xs space-y-1">
                              <Label className="text-[10px] text-muted-foreground">
                                Надбавка к цене при включении ({currency}) *
                              </Label>
                              <Input
                                type="number"
                                min="0"
                                step="0.01"
                                value={comp.unit_price}
                                onChange={(e) => {
                                  const next = [...compList]
                                  next[cIdx].unit_price = e.target.value
                                  setCompList(next)
                                }}
                                placeholder="0.00"
                                className="font-mono text-xs h-8"
                              />
                            </div>
                          ) : comp.type !== "select" ? (
                            /* Числовые контролы (Slider / Stepper): только числовые параметры */
                            <div className="grid grid-cols-2 sm:grid-cols-6 gap-2 pt-2 border-t border-border/50">
                              <div className="space-y-1">
                                <Label className="text-[10px] text-muted-foreground">Ед. изм.</Label>
                                <Input
                                  value={comp.unit}
                                  onChange={(e) => {
                                    const next = [...compList]
                                    next[cIdx].unit = e.target.value
                                    setCompList(next)
                                  }}
                                  placeholder="ед."
                                  className="text-xs h-7"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-[10px] text-muted-foreground">Цена/ед ({currency}) *</Label>
                                <Input
                                  type="number"
                                  min="0"
                                  step="0.01"
                                  value={comp.unit_price}
                                  onChange={(e) => {
                                    const next = [...compList]
                                    next[cIdx].unit_price = e.target.value
                                    setCompList(next)
                                  }}
                                  placeholder="0.00"
                                  className="font-mono text-xs h-7"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-[10px] text-muted-foreground">Мин</Label>
                                <Input
                                  type="number"
                                  value={comp.min ?? ""}
                                  onChange={(e) => {
                                    const next = [...compList]
                                    next[cIdx].min = e.target.value || undefined
                                    setCompList(next)
                                  }}
                                  placeholder="0"
                                  className="font-mono text-xs h-7"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-[10px] text-muted-foreground">Макс</Label>
                                <Input
                                  type="number"
                                  value={comp.max ?? ""}
                                  onChange={(e) => {
                                    const next = [...compList]
                                    next[cIdx].max = e.target.value || undefined
                                    setCompList(next)
                                  }}
                                  placeholder="100"
                                  className="font-mono text-xs h-7"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-[10px] text-muted-foreground">Шаг</Label>
                                <Input
                                  type="number"
                                  value={comp.step ?? ""}
                                  onChange={(e) => {
                                    const next = [...compList]
                                    next[cIdx].step = e.target.value || undefined
                                    setCompList(next)
                                  }}
                                  placeholder="1"
                                  className="font-mono text-xs h-7"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-[10px] text-muted-foreground">По умолч.</Label>
                                <Input
                                  value={comp.default}
                                  onChange={(e) => {
                                    const next = [...compList]
                                    next[cIdx].default = e.target.value
                                    setCompList(next)
                                  }}
                                  placeholder="0"
                                  className="font-mono text-xs h-7"
                                />
                              </div>
                            </div>
                          ) : (
                            /* Список вариантов (Select) */
                            <div className="space-y-2 pt-2 border-t border-border/50">
                              <div className="flex items-center justify-between">
                                <span className="text-[11px] font-medium text-muted-foreground">Варианты выбора:</span>
                                <Button
                                  type="button"
                                  variant="ghost"
                                  size="sm"
                                  className="h-6 text-[11px] text-primary hover:text-primary gap-1"
                                  onClick={() => {
                                    const next = [...compList]
                                    if (!next[cIdx].options) next[cIdx].options = []
                                    next[cIdx].options!.push({
                                      value: "",
                                      label: "",
                                      price_delta: "0.00",
                                    })
                                    setCompList(next)
                                  }}
                                >
                                  <Plus className="size-3" /> Добавить вариант
                                </Button>
                              </div>
                              {(comp.options || []).map((opt, oIdx) => (
                                <div key={oIdx} className="flex items-center gap-2">
                                  <Input
                                    value={opt.label}
                                    onChange={(e) => {
                                      const next = [...compList]
                                      next[cIdx].options![oIdx].label = e.target.value
                                      if (!next[cIdx].options![oIdx].value) {
                                        next[cIdx].options![oIdx].value = translit(e.target.value)
                                      }
                                      setCompList(next)
                                    }}
                                    placeholder="Название варианта"
                                    className="text-xs h-7 flex-1"
                                  />
                                  <Input
                                    value={opt.value}
                                    onChange={(e) => {
                                      const next = [...compList]
                                      next[cIdx].options![oIdx].value = e.target.value
                                      setCompList(next)
                                    }}
                                    placeholder="Значение"
                                    className="font-mono text-xs h-7 w-28"
                                  />
                                  <div className="flex items-center gap-1 w-28">
                                    <Input
                                      type="number"
                                      step="0.01"
                                      value={opt.price_delta}
                                      onChange={(e) => {
                                        const next = [...compList]
                                        next[cIdx].options![oIdx].price_delta = e.target.value
                                        setCompList(next)
                                      }}
                                      placeholder="+0.00"
                                      className="font-mono text-xs h-7"
                                    />
                                    <span className="text-[10px] text-muted-foreground">{currency}</span>
                                  </div>
                                  <Button
                                    type="button"
                                    variant="ghost"
                                    size="icon"
                                    className="size-7 text-muted-foreground hover:text-destructive"
                                    onClick={() => {
                                      const next = [...compList]
                                      next[cIdx].options = next[cIdx].options!.filter((_, i) => i !== oIdx)
                                      setCompList(next)
                                    }}
                                  >
                                    <Trash2 className="size-3" />
                                  </Button>
                                </div>
                              ))}
                            </div>
                          )}

                          {/* Скрываемые технические параметры (код и путь в settings) */}
                          <div className="pt-1 border-t border-border/30">
                            <button
                              type="button"
                              onClick={() => {
                                setExpandedTechComps((prev) => ({
                                  ...prev,
                                  [cIdx]: !prev[cIdx],
                                }))
                              }}
                              className="text-[10px] text-muted-foreground hover:text-foreground inline-flex items-center gap-1"
                            >
                              <Code2 className="size-3" />
                              {expandedTechComps[cIdx] ? "Скрыть технические параметры" : "Технические параметры (код и путь)"}
                            </button>

                            {expandedTechComps[cIdx] && (
                              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-2 p-2 rounded bg-muted/30 border border-border/50">
                                <div className="space-y-1">
                                  <Label className="text-[10px] text-muted-foreground">Системный код *</Label>
                                  <Input
                                    value={comp.code}
                                    onChange={(e) => {
                                      const next = [...compList]
                                      next[cIdx].code = e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "")
                                      setCompList(next)
                                    }}
                                    placeholder="code_resursa"
                                    className="font-mono text-xs h-7"
                                  />
                                </div>
                                <div className="space-y-1">
                                  <Label className="text-[10px] text-muted-foreground">Путь в settings</Label>
                                  <Input
                                    value={comp.path}
                                    onChange={(e) => {
                                      const next = [...compList]
                                      next[cIdx].path = e.target.value
                                      setCompList(next)
                                    }}
                                    placeholder="resources.code"
                                    className="font-mono text-xs h-7"
                                  />
                                </div>
                              </div>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>

          {/* 3. БЛОК: Выдача товара покупателю */}
          <Card className="bg-card/90 shadow-2xs border-border/80">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <KeyRound className="size-4 text-primary" /> Выдача товара покупателю
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Переключатель способа выдачи */}
              <div className="grid gap-3 sm:grid-cols-2">
                {/* 1. Цифровые ключи */}
                <div
                  onClick={() => {
                    if (priceType === "fixed") {
                      setDelivery("key")
                    }
                  }}
                  className={`p-3.5 rounded-xl border transition-all flex flex-col justify-between ${
                    priceType !== "fixed"
                      ? "opacity-40 cursor-not-allowed bg-muted/10 border-dashed"
                      : delivery === "key"
                      ? "border-primary bg-primary/5 shadow-xs ring-1 ring-primary/40 cursor-pointer"
                      : "border-border/70 hover:border-border hover:bg-muted/40 cursor-pointer"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2.5">
                      <div
                        className={`size-8 rounded-lg flex items-center justify-center ${
                          delivery === "key" && priceType === "fixed"
                            ? "bg-primary text-primary-foreground"
                            : "bg-muted text-muted-foreground"
                        }`}
                      >
                        <KeyRound className="size-4" />
                      </div>
                      <div>
                        <div className="text-sm font-semibold">Цифровые ключи</div>
                        <div className="text-[11px] text-muted-foreground">Пул лицензий</div>
                      </div>
                    </div>
                    {priceType !== "fixed" && (
                      <Badge variant="outline" className="text-[10px] text-muted-foreground border-dashed">
                        Только для фиксированной
                      </Badge>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground mt-2">
                    {priceType === "fixed"
                      ? "Автоматическая выдача ключа покупателю из пула сразу после оплаты."
                      : "Выдача ключей из пула доступна только для фиксированной цены."}
                  </p>
                </div>

                {/* 2. Lua-скрипт автоматизации */}
                <div
                  onClick={() => setDelivery("lua")}
                  className={`p-3.5 rounded-xl border cursor-pointer transition-all flex flex-col justify-between ${
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
                      <div className="text-sm font-semibold">Автоматизация (скрипт)</div>
                      <div className="text-[11px] text-muted-foreground">Обработка через скрипт</div>
                    </div>
                  </div>
                  <p className="text-xs text-muted-foreground mt-2">
                    Вызов скрипта: выдача ролей, обращение к API ботов или генерация ссылок.
                  </p>
                </div>
              </div>

              {/* Настройки пула ключей */}
              {delivery === "key" && (
                <div className="p-3.5 rounded-xl bg-muted/30 border border-border/80 space-y-2.5">
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
                      <span>Ключи закончились. Продажи товара остановлены до пополнения пула.</span>
                    </div>
                  )}
                </div>
              )}

              {/* Настройки Lua-скрипта */}
              {delivery === "lua" && (
                <div className="space-y-3 p-3.5 rounded-xl bg-muted/20 border border-border/80">
                  <div className="space-y-1.5">
                    <Label>Скрипт автоматизации *</Label>
                    <LuaScriptSelect
                      scripts={luaScripts}
                      value={luaScriptId}
                      onChange={setLuaScriptId}
                      kind={["service", "generic"]}
                      hasError={Boolean(hasSubmitted && validationErrors.delivery)}
                    />
                    {hasSubmitted && validationErrors.delivery && (
                      <p className="text-[11px] text-destructive flex items-center gap-1">
                        <AlertCircle className="size-3" /> {validationErrors.delivery}
                      </p>
                    )}
                  </div>

                  {/* Кнопки графического редактора JSON параметров вместо черных textarea */}
                  <div className="grid gap-3 sm:grid-cols-2 pt-1 border-t border-border/40">
                    <div className="flex items-center justify-between p-2.5 rounded-lg border bg-card/60">
                      <div className="space-y-0.5 min-w-0 pr-2">
                        <div className="text-xs font-semibold text-foreground">Параметры доставки</div>
                        <div className="text-[10px] text-muted-foreground font-mono">
                          {paramsCount > 0 ? `${paramsCount} параметров` : "По умолчанию ({})"}
                        </div>
                      </div>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="h-7 text-xs gap-1.5 shrink-0"
                        onClick={() => {
                          setJsonModalConfig({
                            open: true,
                            title: "Параметры доставки (Params JSON)",
                            description: "Параметры и схема доставки товара",
                            text: paramsText,
                            target: "params",
                          })
                        }}
                      >
                        <SlidersHorizontal className="size-3" /> Настроить
                      </Button>
                    </div>

                    <div className="flex items-center justify-between p-2.5 rounded-lg border bg-card/60">
                      <div className="space-y-0.5 min-w-0 pr-2">
                        <div className="text-xs font-semibold text-foreground">Настройки скрипта</div>
                        <div className="text-[10px] text-muted-foreground font-mono">
                          {settingsCount > 0 ? `${settingsCount} параметров` : "По умолчанию ({})"}
                        </div>
                      </div>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="h-7 text-xs gap-1.5 shrink-0"
                        onClick={() => {
                          setJsonModalConfig({
                            open: true,
                            title: "Настройки скрипта (Settings JSON)",
                            description: "Конфигурация сервиса, передаваемая в скрипт",
                            text: settingsText,
                            target: "settings",
                          })
                        }}
                      >
                        <SlidersHorizontal className="size-3" /> Настроить
                      </Button>
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* 4. БЛОК: Медиа карточки товара */}
          <Card className="bg-card/90 shadow-2xs border-border/80">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold">Медиа карточки товара</CardTitle>
            </CardHeader>
            <CardContent>
              {isNew ? (
                <p className="text-xs text-muted-foreground">
                  Медиафайлы можно будет прикрепить к карточке сразу после сохранения услуги.
                </p>
              ) : (
                <ServiceMediaWidget
                  serviceId={serviceId!}
                  serviceName={name || `Услуга #${serviceId}`}
                  attachments={attachments ?? []}
                  onRefresh={() => {
                    void qc.invalidateQueries({ queryKey: ["admin-service-attachments", serviceId] })
                  }}
                />
              )}
            </CardContent>
          </Card>
        </div>

        {/* Правая колонка: Панель управления и статус (Sticky) */}
        <div className="space-y-4">
          <div className="sticky top-6 space-y-4">
            <Card className="bg-card/95 shadow-xs border-border/80 backdrop-blur-xs">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-semibold">Управление товаром</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Активность товара */}
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
                {(isDirty || isNew) ? (
                  <Button
                    onClick={handleSave}
                    disabled={saveMutation.isPending}
                    className="w-full h-11 text-sm font-semibold gap-2 shadow-sm"
                  >
                    <Save className="size-4" />
                    {saveMutation.isPending ? "Сохранение…" : isNew ? "Создать товар" : "Сохранить изменения"}
                  </Button>
                ) : (
                  <div className="w-full h-11 flex items-center justify-center gap-2 rounded-lg border bg-muted/20 text-xs text-muted-foreground font-medium">
                    <Check className="size-4 text-emerald-500" /> Все изменения сохранены
                  </div>
                )}

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
                        onClick={() => {
                          setDeleteConfirmSlug("")
                          setDeleteConfirmOpen(true)
                        }}
                      >
                        <Trash2 className="size-4" />
                        Удалить услугу
                      </Button>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Мета-информация */}
            {!isNew && service && (
              <Card className="bg-muted/30 border-border/60 text-xs text-muted-foreground p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <span>Режим цен:</span>
                  <Badge variant="outline" className="font-mono uppercase text-[10px]">
                    {priceType}
                  </Badge>
                </div>
                <div className="flex items-center justify-between">
                  <span>Доставка:</span>
                  <span className="font-mono text-foreground">{delivery}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span>Статус пула:</span>
                  <span className="font-medium text-foreground">
                    {delivery === "key" ? (stock?.out_of_stock ? "Закончились" : "В наличии") : "Lua"}
                  </span>
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
        onSelect={() => setMediaPickerOpen(false)}
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

      {/* Диалог подтверждения удаления услуги со slug */}
      <Dialog open={deleteConfirmOpen} onOpenChange={setDeleteConfirmOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="text-destructive flex items-center gap-2">
              <Trash2 className="size-5" /> Удалить услугу?
            </DialogTitle>
            <DialogDescription>
              Услуга «{name}» (#{serviceId}) будет удалена безвозвратно.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-2 py-2">
            <p className="text-xs text-muted-foreground">
              Для подтверждения введите slug услуги:{" "}
              <code className="font-mono font-bold text-foreground bg-muted px-1.5 py-0.5 rounded">
                {slug}
              </code>
            </p>
            <Input
              value={deleteConfirmSlug}
              onChange={(e) => setDeleteConfirmSlug(e.target.value)}
              placeholder={slug}
              className="font-mono text-xs"
            />
          </div>

          <DialogFooter>
            <Button variant="ghost" onClick={() => setDeleteConfirmOpen(false)}>
              Отмена
            </Button>
            <Button
              variant="destructive"
              disabled={deleteConfirmSlug !== slug || deleteMutation.isPending}
              onClick={() => deleteMutation.mutate()}
            >
              {deleteMutation.isPending ? "Удаление…" : "Удалить услугу"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Диалог предупреждения о несохраненных изменениях при выходе */}
      <Dialog open={leaveConfirmOpen} onOpenChange={setLeaveConfirmOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertCircle className="size-5 text-amber-500" /> Несохраненные изменения
            </DialogTitle>
            <DialogDescription>
              На странице есть несохраненные изменения. Вы уверены, что хотите уйти без сохранения?
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" onClick={() => setLeaveConfirmOpen(false)}>
              Остаться
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                setLeaveConfirmOpen(false)
                navigate("/services")
              }}
            >
              Уйти без сохранения
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Графический диалог редактирования JSON (на базе KeySecretEditor) */}
      <Dialog
        open={jsonModalConfig.open}
        onOpenChange={(open) => {
          if (!open) {
            setJsonModalConfig((prev) => ({ ...prev, open: false }))
          }
        }}
      >
        <DialogContent className="sm:max-w-3xl w-full">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <SlidersHorizontal className="size-5 text-primary" /> {jsonModalConfig.title}
            </DialogTitle>
            {jsonModalConfig.description && (
              <DialogDescription>{jsonModalConfig.description}</DialogDescription>
            )}
          </DialogHeader>

          <div className="py-2">
            <KeySecretEditor
              title="Параметры конфигурации"
              description="Редактируйте параметры по строкам или переключитесь в режим JSON"
              value={jsonModalConfig.text}
              onChange={(_, text) => {
                setJsonModalConfig((prev) => ({ ...prev, text }))
              }}
            />
          </div>

          <DialogFooter>
            <Button
              variant="ghost"
              onClick={() => setJsonModalConfig((prev) => ({ ...prev, open: false }))}
            >
              Отмена
            </Button>
            <Button
              onClick={() => {
                const text = jsonModalConfig.text || "{}"
                if (jsonModalConfig.target === "params") {
                  setParamsText(text)
                } else if (jsonModalConfig.target === "settings") {
                  setSettingsText(text)
                } else if (typeof jsonModalConfig.target === "object" && "tierIdx" in jsonModalConfig.target) {
                  const idx = jsonModalConfig.target.tierIdx
                  try {
                    const parsed = JSON.parse(text)
                    const next = [...tierPlans]
                    next[idx].settings_override = Object.keys(parsed).length > 0 ? parsed : undefined
                    setTierPlans(next)
                  } catch {
                    toastError("Ошибка JSON", "Некорректный JSON")
                    return
                  }
                }
                setJsonModalConfig((prev) => ({ ...prev, open: false }))
              }}
            >
              Применить
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
