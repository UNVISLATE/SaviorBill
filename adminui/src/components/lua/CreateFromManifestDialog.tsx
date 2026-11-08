import { useEffect, useMemo, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "react-router-dom"
import { Package, CreditCard, Layers } from "lucide-react"

import { api } from "@/api/api.ts"
import { getErrorDetail } from "@/lib/api-error.ts"
import { toastError, toastSuccess } from "@/lib/toast"
import { Input } from "@/components/shadsnui/input"
import { Label } from "@/components/shadsnui/label"
import { Textarea } from "@/components/shadsnui/textarea"
import { TabbedDialog, type TabbedDialogTab } from "@/components/common/TabbedDialog"
import { ManifestLivePreview } from "@unvislate/sbui-sdk"

export interface ScriptLike {
  id: number
  slug: string
  name?: string | null
  kind: string
  settings?: Record<string, unknown>
}

interface CreateFromManifestDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  script: ScriptLike | null
}

export function CreateFromManifestDialog({
  open,
  onOpenChange,
  script,
}: CreateFromManifestDialogProps) {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [activeTab, setActiveTab] = useState("general")

  // Extract manifest & prefill
  const manifest = useMemo(() => {
    if (!script?.settings) return null
    const s = script.settings
    if (s.manifest && typeof s.manifest === "object") return s.manifest as Record<string, any>
    if (s.client_order_form || s.settings_form || s.prefill) return s as Record<string, any>
    return null
  }, [script])

  const prefill = manifest?.prefill as Record<string, any> | undefined
  const isPayment = script?.kind === "payment"

  // Form states
  const [name, setName] = useState("")
  const [slug, setSlug] = useState("")
  const [description, setDescription] = useState("")
  const [price, setPrice] = useState("0")
  const [currency, setCurrency] = useState("RUB")
  const [settingsJson, setSettingsJson] = useState("{}")
  const [paramsJson, setParamsJson] = useState("{}")

  // Initialize values whenever dialog opens with script
  useEffect(() => {
    if (open && script) {
      setActiveTab("general")
      const initialName = prefill?.name || script.name || script.slug
      setName(initialName)
      setSlug(prefill?.slug || script.slug)
      setDescription(prefill?.description || manifest?.description || "")
      setPrice("0")
      setCurrency("RUB")

      // Extract default settings from settings_form if present
      const defaultSettings: Record<string, any> = {}
      if (Array.isArray(manifest?.settings_form)) {
        for (const field of manifest.settings_form) {
          if (field.id && field.default !== undefined) {
            defaultSettings[field.id] = field.default
          }
        }
      }
      if (prefill?.scopes && Array.isArray(prefill.scopes)) {
        defaultSettings._scopes = prefill.scopes
      }
      setSettingsJson(JSON.stringify(defaultSettings, null, 2))

      // Extract default params from client_order_form if present
      const defaultParams: Record<string, any> = {}
      if (Array.isArray(manifest?.client_order_form)) {
        for (const field of manifest.client_order_form) {
          if (field.id && field.default !== undefined) {
            defaultParams[field.id] = field.default
          }
        }
      }
      setParamsJson(JSON.stringify(defaultParams, null, 2))
    }
  }, [open, script, manifest, prefill])

  // Mutation to create entity
  const createMutation = useMutation({
    mutationFn: async () => {
      if (!script) throw new Error("Скрипт не выбран")
      if (!name.trim()) throw new Error("Укажите название")
      if (!slug.trim()) throw new Error("Укажите уникальный идентификатор (slug)")

      let parsedSettings = {}
      let parsedParams = {}
      try {
        parsedSettings = JSON.parse(settingsJson || "{}")
        parsedParams = JSON.parse(paramsJson || "{}")
      } catch {
        throw new Error("Некорректный синтаксис JSON на вкладке настроек")
      }

      if (isPayment) {
        // Create Payment Provider
        const payload = {
          slug: slug.trim(),
          name: name.trim(),
          lua_script_id: script.id,
          is_active: true,
          settings: parsedSettings,
        }
        return (await api.post("/v1/admin/purchases/providers", payload)).data
      } else {
        // Create Catalog Service
        const payload = {
          name: name.trim(),
          slug: slug.trim(),
          description: description.trim() || null,
          price: price.trim() || "0",
          currency,
          price_type: "fixed",
          pricing_config: {},
          delivery: "lua",
          lua_script_id: script.id,
          params: parsedParams,
          settings: parsedSettings,
          is_active: true,
        }
        return (await api.post("/v1/admin/services", payload)).data
      }
    },
    onSuccess: (data: any) => {
      toastSuccess(
        isPayment ? "Провайдер создан" : "Услуга создана",
        `Сущность "${name}" успешно добавлена`
      )
      onOpenChange(false)
      if (isPayment) {
        void qc.invalidateQueries({ queryKey: ["admin-payment-providers"] })
        navigate("/providers/payment")
      } else {
        void qc.invalidateQueries({ queryKey: ["admin-services"] })
        if (data?.id) {
          navigate(`/services/${data.id}`)
        }
      }
    },
    onError: (e) => {
      const detail = getErrorDetail(e)
      toastError("Ошибка создания", detail || (e as Error).message)
    },
  })

  if (!script) return null

  const tabs: TabbedDialogTab[] = [
    {
      id: "general",
      label: "Параметры",
      icon: isPayment ? CreditCard : Package,
      content: (
        <div className="space-y-4 py-2">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Название *</Label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Название услуги или шлюза"
                className="h-8 text-xs"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Идентификатор (Slug) *</Label>
              <Input
                value={slug}
                onChange={(e) => setSlug(e.target.value)}
                placeholder="slug-code"
                className="h-8 text-xs font-mono"
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">Описание</Label>
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Краткое описание для витрины..."
              rows={2}
              className="text-xs"
            />
          </div>

          {!isPayment && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label className="text-xs">Базовая цена</Label>
                <Input
                  type="number"
                  value={price}
                  onChange={(e) => setPrice(e.target.value)}
                  className="h-8 text-xs"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Валюта</Label>
                <Input
                  value={currency}
                  onChange={(e) => setCurrency(e.target.value)}
                  className="h-8 text-xs"
                />
              </div>
            </div>
          )}

          <div className="rounded-md border border-border/60 bg-muted/30 p-2.5 text-xs text-muted-foreground">
            Автоматическая связка: доставка через скрипт{" "}
            <span className="font-mono text-foreground font-semibold">{script.slug}</span> (id: {script.id}).
          </div>
        </div>
      ),
    },
    {
      id: "manifest",
      label: "Предустановки",
      icon: Layers,
      content: (
        <div className="space-y-4 py-2">
          {manifest && (
            <div className="rounded-md border border-border/80 overflow-hidden bg-zinc-950/40">
              <div className="px-3 py-1.5 bg-muted/40 border-b border-border/60 text-[11px] font-medium text-muted-foreground">
                Превью
              </div>
              <div className="p-3">
                <ManifestLivePreview manifest={manifest} previewType="client_order_form" />
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Настройки (settings JSON)</Label>
              <Textarea
                value={settingsJson}
                onChange={(e) => setSettingsJson(e.target.value)}
                rows={4}
                className="font-mono text-[11px]"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Параметры (params JSON)</Label>
              <Textarea
                value={paramsJson}
                onChange={(e) => setParamsJson(e.target.value)}
                rows={4}
                className="font-mono text-[11px]"
              />
            </div>
          </div>
        </div>
      ),
    },
  ]

  return (
    <TabbedDialog
      open={open}
      onOpenChange={onOpenChange}
      title={`Создание ${isPayment ? "провайдера" : "услуги"} из манифеста`}
      description={`Предустановки из скрипта ${script.slug}`}
      tabs={tabs}
      activeTab={activeTab}
      onTabChange={setActiveTab}
      maxWidth="max-w-2xl"
      height="h-[560px]"
      primaryAction={{
        label: createMutation.isPending ? "Создание..." : `Создать ${isPayment ? "провайдера" : "услугу"}`,
        onClick: () => createMutation.mutate(),
        disabled: createMutation.isPending || !name.trim() || !slug.trim(),
        loading: createMutation.isPending,
      }}
      secondaryAction={{
        label: "Отмена",
        onClick: () => onOpenChange(false),
      }}
    />
  )
}
