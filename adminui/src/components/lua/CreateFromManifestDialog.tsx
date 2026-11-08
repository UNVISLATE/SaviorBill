import { useEffect, useMemo, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "react-router-dom"
import {
  Sparkles,
  Package,
  CreditCard,
  Layers,
  CheckCircle2,
  Eye,
} from "lucide-react"

import { api } from "@/api/api.ts"
import { getErrorDetail } from "@/lib/api-error.ts"
import { toastError, toastSuccess } from "@/lib/toast"
import { Button } from "@/components/shadsnui/button"
import { Input } from "@/components/shadsnui/input"
import { Label } from "@/components/shadsnui/label"
import { Textarea } from "@/components/shadsnui/textarea"
import { Badge } from "@/components/shadsnui/badge"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/shadsnui/dialog"
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
  const [activeTab, setActiveTab] = useState<"general" | "manifest">("general")

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
        isPayment ? "Платёжный провайдер создан" : "Услуга создана из манифеста",
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

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <div className="size-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center">
              <Sparkles className="size-4" />
            </div>
            <div>
              <DialogTitle className="text-base font-semibold">
                Создание {isPayment ? "провайдера" : "услуги"} из манифеста
              </DialogTitle>
              <DialogDescription className="text-xs">
                Скрипт <span className="font-mono text-foreground font-semibold">{script.slug}</span> содержит готовые предустановки
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        {/* Tab navigation */}
        <div className="flex items-center border-b border-border/60 gap-1 pb-1">
          <button
            type="button"
            onClick={() => setActiveTab("general")}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors flex items-center gap-1.5 ${
              activeTab === "general"
                ? "bg-primary/15 text-primary border border-primary/30"
                : "text-muted-foreground hover:text-foreground hover:bg-muted/40"
            }`}
          >
            {isPayment ? <CreditCard className="size-3.5" /> : <Package className="size-3.5" />}
            1. Основные параметры
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("manifest")}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors flex items-center gap-1.5 ${
              activeTab === "manifest"
                ? "bg-primary/15 text-primary border border-primary/30"
                : "text-muted-foreground hover:text-foreground hover:bg-muted/40"
            }`}
          >
            <Layers className="size-3.5" />
            2. Предустановки манифеста (SDUI)
            {manifest?.client_order_form && (
              <Badge variant="outline" className="text-[10px] py-0 px-1 ml-1 bg-muted/60">
                {manifest.client_order_form.length} полей
              </Badge>
            )}
          </button>
        </div>

        {/* Tab 1: General Settings */}
        {activeTab === "general" && (
          <div className="space-y-4 py-2">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="create-name" className="text-xs">
                  Название *
                </Label>
                <Input
                  id="create-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Название услуги или шлюза"
                  className="h-8 text-xs"
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="create-slug" className="text-xs">
                  Уникальный идентификатор (Slug) *
                </Label>
                <Input
                  id="create-slug"
                  value={slug}
                  onChange={(e) => setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, ""))}
                  placeholder="vpn-standard"
                  className="h-8 text-xs font-mono"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="create-desc" className="text-xs">
                Описание
              </Label>
              <Textarea
                id="create-desc"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Краткое описание товара для витрины..."
                rows={3}
                className="text-xs resize-none"
              />
            </div>

            {!isPayment && (
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor="create-price" className="text-xs">
                    Базовая цена
                  </Label>
                  <Input
                    id="create-price"
                    type="number"
                    value={price}
                    onChange={(e) => setPrice(e.target.value)}
                    placeholder="0"
                    className="h-8 text-xs font-mono"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="create-curr" className="text-xs">
                    Валюта
                  </Label>
                  <Input
                    id="create-curr"
                    value={currency}
                    onChange={(e) => setCurrency(e.target.value.toUpperCase())}
                    className="h-8 text-xs font-mono"
                  />
                </div>
              </div>
            )}

            <div className="p-3 rounded-lg border border-primary/20 bg-primary/5 flex items-start gap-2.5 text-xs text-muted-foreground">
              <CheckCircle2 className="size-4 text-primary shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold text-foreground">Автоматическая связка со скриптом:</span>
                {" "}Товар будет настроен на доставку через скрипт <code className="text-primary font-mono font-semibold">{script.slug}</code> (id: {script.id}).
              </div>
            </div>
          </div>
        )}

        {/* Tab 2: Manifest & Presets */}
        {activeTab === "manifest" && (
          <div className="space-y-4 py-2">
            {manifest ? (
              <>
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span className="flex items-center gap-1">
                    <Sparkles className="size-3.5 text-primary" />
                    Манифест версии {manifest.version || "1.0"}
                  </span>
                  {manifest.author && <span>Автор: {manifest.author}</span>}
                </div>

                {/* Live SDUI preview */}
                <div className="rounded-xl border border-border/80 bg-zinc-950/60 p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                      <Eye className="size-3.5 text-primary" /> Предпросмотр витринного диалога
                    </span>
                    <Badge variant="outline" className="text-[10px]">
                      Live SDUI Preview
                    </Badge>
                  </div>
                  <div className="rounded-lg border border-border/50 bg-background/50 overflow-hidden">
                    <ManifestLivePreview manifest={manifest} previewType="client_order_form" />
                  </div>
                </div>

                {/* Preconfigured JSONs */}
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="space-y-1.5">
                    <Label className="text-xs flex items-center justify-between">
                      <span>Настройки скрипта (settings)</span>
                      <span className="text-[10px] text-muted-foreground font-mono">JSON</span>
                    </Label>
                    <Textarea
                      value={settingsJson}
                      onChange={(e) => setSettingsJson(e.target.value)}
                      rows={5}
                      className="font-mono text-xs resize-none"
                    />
                  </div>

                  {!isPayment && (
                    <div className="space-y-1.5">
                      <Label className="text-xs flex items-center justify-between">
                        <span>Параметры доставки (params)</span>
                        <span className="text-[10px] text-muted-foreground font-mono">JSON</span>
                      </Label>
                      <Textarea
                        value={paramsJson}
                        onChange={(e) => setParamsJson(e.target.value)}
                        rows={5}
                        className="font-mono text-xs resize-none"
                      />
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="p-8 text-center text-xs text-muted-foreground border border-dashed rounded-lg">
                Скрипт не содержит явного блока manifest.json в настройках
              </div>
            )}
          </div>
        )}

        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            Отмена
          </Button>
          <Button
            size="sm"
            disabled={createMutation.isPending || !name.trim()}
            onClick={() => createMutation.mutate()}
            className="gap-1.5 bg-primary text-primary-foreground hover:bg-primary/90"
          >
            <Sparkles className="size-3.5" />
            {createMutation.isPending ? "Создание…" : `Создать ${isPayment ? "провайдера" : "услугу"}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
