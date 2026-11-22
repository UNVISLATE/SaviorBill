import { useEffect, useMemo, useRef, useState } from "react"
import { Link, useNavigate, useParams } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import * as monaco from "monaco-editor"
import { ArrowLeft, Check, Code2, Eye, LayoutList, QrCode, Save, Sliders, Sparkles } from "lucide-react"

import { api } from "@/api/api.ts"
import { getErrorDetail } from "@/lib/api-error.ts"
import { ensureMonacoWorkers } from "@/lib/monaco-setup"
import { extractScriptManifest } from "@/lib/script-manifest"
import { useBreadcrumbExtra } from "@/hooks/use-breadcrumb"
import { toastError, toastSuccess } from "@/lib/toast"
import { Button } from "@/components/shadsnui/button"
import { KeySecretEditor } from "@/components/common/forms/KeySecretEditor"
import { ManifestLivePreview } from "@unvislate/sbui-sdk"

interface LuaScriptDetail {
  id: number
  slug: string
  name?: string | null
  kind: string
  settings: Record<string, unknown>
  lock_version: number
}

const TEMPLATES: Record<string, Record<string, unknown>> = {
  vps: {
    version: "1.0",
    name: "Облачный VPS сервер",
    slug: "cloud-vps",
    description: "Автоматический заказ виртуального сервера с выбором ОС и SSH-ключа",
    author: "UNVI Cloud",
    prefill: {
      name: "Облачный VPS Стандарт",
      description: "Быстрый NVMe сервер с гарантированными ресурсами",
      scopes: ["vps.manage", "billing.read"],
    },
    client_order_form: [
      {
        id: "hostname",
        type: "text",
        label: "Имя сервера (Hostname)",
        placeholder: "myserver.example.com",
        required: true,
        regex: "^[a-z0-9.-]+$",
        regex_error: "Разрешены только строчные латинские буквы, цифры и дефис",
      },
      {
        id: "os",
        type: "select",
        label: "Операционная система",
        required: true,
        default: "ubuntu-24-04",
        options: [
          { value: "ubuntu-24-04", label: "Ubuntu 24.04 LTS" },
          { value: "debian-12", label: "Debian 12 Bookworm" },
          { value: "alpine-3-20", label: "Alpine Linux 3.20" },
        ],
      },
      {
        id: "ssh_key",
        type: "text",
        label: "Публичный SSH-ключ",
        placeholder: "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5...",
        required: true,
        description: "Ваш открытый SSH ключ для входа root без пароля",
      },
      {
        id: "enable_backup",
        type: "toggle",
        label: "Автоматическое ежедневное резервное копирование",
        default: true,
      },
    ],
  },
  payment: {
    version: "1.0",
    name: "Платёжный шлюз",
    slug: "custom-gateway",
    description: "Интеграция платёжного провайдера с проверкой подписи webhook",
    author: "UNVI Payments",
    prefill: {
      name: "Кастомный эквайринг",
      description: "Приём платежей через внешний API",
    },
    settings_form: [
      {
        id: "merchant_id",
        type: "text",
        label: "Идентификатор мерчанта (Merchant ID)",
        required: true,
      },
      {
        id: "api_key",
        type: "password",
        label: "Секретный API-ключ",
        required: true,
      },
      {
        id: "test_mode",
        type: "toggle",
        label: "Песочница (Тестовый режим)",
        default: false,
      },
    ],
  },
}

export function LuaManifestPage() {
  const { scriptId } = useParams()
  const navigate = useNavigate()
  const qc = useQueryClient()

  const editorHostRef = useRef<HTMLDivElement>(null)
  const editorRef = useRef<monaco.editor.IStandaloneCodeEditor | null>(null)
  const isUpdatingFromCode = useRef(false)

  const [manifestJson, setManifestJson] = useState("{\n  \n}")
  const [parseError, setParseError] = useState<string | null>(null)
  const [dirty, setDirty] = useState(false)
  const [activeTab, setActiveTab] = useState<"settings_form" | "client_order_form" | "view_layout">("settings_form")
  const [previewSettingsData, setPreviewSettingsData] = useState<Record<string, unknown>>({})

  const parsedManifest = useMemo(() => {
    try {
      return JSON.parse(manifestJson)
    } catch {
      return null
    }
  }, [manifestJson])

  const manifestData = useMemo(() => {
    if (!parsedManifest || typeof parsedManifest !== "object") return null
    return (parsedManifest.manifest || parsedManifest) as Record<string, any>
  }, [parsedManifest])

  const hasSettingsForm = Array.isArray(manifestData?.settings_form) && manifestData.settings_form.length > 0
  const hasOrderForm =
    (Array.isArray(manifestData?.client_order_form) && manifestData.client_order_form.length > 0) ||
    (Array.isArray(manifestData?.order_form) && manifestData.order_form.length > 0)
  const hasViewLayout = Boolean(manifestData?.view_layout || manifestData?.client_view_form || manifestData?.layout)

  // Fetch script details
  const { data: script } = useQuery({
    queryKey: ["admin-lua-script", scriptId ? Number(scriptId) : null],
    queryFn: async () => (await api.get<LuaScriptDetail>(`/v1/admin/lua/${scriptId}`)).data,
    enabled: Boolean(scriptId),
  })

  const scriptTitle = script
    ? (script.name ?? script.slug)
    : scriptId
      ? `#${scriptId}`
      : null

  const breadcrumbSegments = useMemo(
    () =>
      scriptTitle
        ? [
            { title: scriptTitle, path: scriptId ? `/lua/${scriptId}` : "/lua" },
            { title: "Манифест" },
          ]
        : [{ title: "Манифест" }],
    [scriptTitle, scriptId],
  )
  useBreadcrumbExtra(breadcrumbSegments)

  const initialManifestText = useMemo(() => {
    if (!script) return "{\n  \n}"
    const manifestObj = extractScriptManifest(script.settings)
    return manifestObj ? JSON.stringify(manifestObj, null, 2) : "{\n  \n}"
  }, [script])

  const latestManifestRef = useRef("{\n  \n}")

  // Initialize Monaco Editor once (reading ref inside effect so StrictMode & cached queries work cleanly)
  useEffect(() => {
    ensureMonacoWorkers()
    if (!editorHostRef.current) return

    const initialValue = latestManifestRef.current
    const editor = monaco.editor.create(editorHostRef.current, {
      value: initialValue,
      language: "json",
      theme: "vs-dark",
      automaticLayout: true,
      minimap: { enabled: false },
      fontSize: 13,
      tabSize: 2,
      scrollBeyondLastLine: false,
    })
    editorRef.current = editor

    const sub = editor.onDidChangeModelContent(() => {
      if (isUpdatingFromCode.current) return
      const val = editor.getValue()
      setManifestJson(val)
      setDirty(true)
      try {
        JSON.parse(val)
        setParseError(null)
      } catch (e) {
        setParseError((e as Error).message)
      }
    })

    return () => {
      sub.dispose()
      editor.dispose()
      editorRef.current = null
    }
  }, [])

  // Sync script data into Monaco editor when loaded or changed
  useEffect(() => {
    if (!script) return
    latestManifestRef.current = initialManifestText
    setManifestJson(initialManifestText)
    setParseError(null)
    setDirty(false)

    if (editorRef.current && editorRef.current.getValue() !== initialManifestText) {
      isUpdatingFromCode.current = true
      editorRef.current.setValue(initialManifestText)
      isUpdatingFromCode.current = false
    }
  }, [script, initialManifestText])

  const handleApplyTemplate = (key: string) => {
    const tmpl = TEMPLATES[key]
    if (!tmpl) return
    const text = JSON.stringify(tmpl, null, 2)
    setManifestJson(text)
    setDirty(true)
    setParseError(null)
    if (editorRef.current) {
      isUpdatingFromCode.current = true
      editorRef.current.setValue(text)
      isUpdatingFromCode.current = false
    }
  }

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!scriptId) throw new Error("ID скрипта не определён")
      const parsed = JSON.parse(manifestJson)
      const currentSettings = { ...(script?.settings || {}) }
      const isEmpty =
        !parsed ||
        typeof parsed !== "object" ||
        Array.isArray(parsed) ||
        (Object.keys(parsed).length === 0 &&
          !parsed.client_view_form &&
          !parsed.layout &&
          !parsed.client_order_form)

      if (isEmpty) {
        delete currentSettings.manifest
      } else {
        currentSettings.manifest = parsed
      }

      return (
        await api.patch(`/v1/admin/lua/${scriptId}`, {
          settings: currentSettings,
        })
      ).data
    },
    onSuccess: () => {
      setDirty(false)
      toastSuccess("Манифест сохранён")
      void qc.invalidateQueries({ queryKey: ["admin-lua-script", Number(scriptId)] })
      void qc.invalidateQueries({ queryKey: ["admin-lua-scripts"] })
    },
    onError: (e) => {
      toastError("Ошибка сохранения", getErrorDetail(e))
    },
  })

  return (
    <div className="-m-6 flex h-[calc(100vh-3rem)] flex-col bg-background">
      {/* Top Bar */}
      <header className="flex h-12 items-center justify-between border-b border-border/60 px-4 sm:px-6 bg-muted/10 shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs"
            onClick={() => navigate(`/lua/${scriptId}`)}
          >
            <ArrowLeft className="size-3.5 mr-1" /> К скрипту
          </Button>
          <div className="h-4 w-px bg-border/60" />
          <div className="flex items-center gap-1.5 text-xs truncate">
            <Link to="/lua" className="text-muted-foreground hover:text-foreground transition-colors">
              Скрипты
            </Link>
            <span className="text-muted-foreground">/</span>
            <Link
              to={scriptId ? `/lua/${scriptId}` : "/lua"}
              className="text-muted-foreground hover:text-foreground transition-colors truncate max-w-[16rem]"
            >
              {scriptTitle}
            </Link>
            <span className="text-muted-foreground">/</span>
            <span className="font-semibold text-foreground">Манифест</span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-7 text-xs gap-1"
            onClick={() => handleApplyTemplate(script?.kind === "payment" ? "payment" : "vps")}
          >
            <Sparkles className="size-3" /> Шаблон: {script?.kind === "payment" ? "Платёж" : "VPS"}
          </Button>
          <Button
            type="button"
            size="sm"
            disabled={Boolean(parseError) || saveMutation.isPending || !dirty}
            onClick={() => saveMutation.mutate()}
            className="h-7 text-xs gap-1.5 bg-primary text-primary-foreground hover:bg-primary/90 shadow-2xs"
          >
            <Save className="size-3" />
            <span>{saveMutation.isPending ? "Сохранение..." : "Сохранить"}</span>
          </Button>
        </div>
      </header>

      {/* Split View */}
      <div className="grid grid-cols-1 md:grid-cols-2 flex-1 min-h-0 overflow-hidden">
        {/* Left: Editor */}
        <div className="flex flex-col border-r border-border/60 overflow-hidden bg-background">
          <div className="flex h-8 items-center justify-between border-b border-border/60 px-4 text-xs text-muted-foreground bg-muted/20 shrink-0">
            <span className="flex items-center gap-1.5 font-medium">
              <Code2 className="size-3.5 text-primary" /> Редактор
            </span>
            {parseError ? (
              <span className="text-red-500 text-[11px]">Ошибка синтаксиса</span>
            ) : (
              <span className="text-emerald-500 text-[11px] flex items-center gap-1">
                <Check className="size-3" /> JSON OK
              </span>
            )}
          </div>
          <div ref={editorHostRef} className="flex-1 w-full min-h-0" />
        </div>

        {/* Right: Preview */}
        <div className="flex flex-col overflow-hidden bg-zinc-950/40">
          <div className="flex h-8 items-center justify-between border-b border-border/60 px-4 text-xs text-muted-foreground bg-muted/20 shrink-0">
            <span className="flex items-center gap-1.5 font-medium">
              <Eye className="size-3.5 text-primary" /> Превью
            </span>

            {/* Вкладки переключения между типами форм */}
            <div className="flex items-center rounded-lg border border-border/80 bg-muted/40 p-0.5">
              <button
                type="button"
                onClick={() => setActiveTab("settings_form")}
                className={`flex items-center gap-1.5 rounded-md px-2 py-0.5 text-[11px] font-medium transition-all cursor-pointer ${
                  activeTab === "settings_form"
                    ? "bg-background text-foreground shadow-2xs"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <span>Настройки админки</span>
                {hasSettingsForm && <span className="size-1.5 rounded-full bg-emerald-500" />}
              </button>

              <button
                type="button"
                onClick={() => setActiveTab("client_order_form")}
                className={`flex items-center gap-1.5 rounded-md px-2 py-0.5 text-[11px] font-medium transition-all cursor-pointer ${
                  activeTab === "client_order_form"
                    ? "bg-background text-foreground shadow-2xs"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <span>Форма заказа</span>
                {hasOrderForm && <span className="size-1.5 rounded-full bg-emerald-500" />}
              </button>

              <button
                type="button"
                onClick={() => setActiveTab("view_layout")}
                className={`flex items-center gap-1.5 rounded-md px-2 py-0.5 text-[11px] font-medium transition-all cursor-pointer ${
                  activeTab === "view_layout"
                    ? "bg-background text-foreground shadow-2xs"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <span>Карточка в ЛК</span>
                {hasViewLayout && <span className="size-1.5 rounded-full bg-emerald-500" />}
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-6">
            <div className="max-w-xl mx-auto">
              {activeTab === "settings_form" ? (
                hasSettingsForm ? (
                  /* Настройки для админки — чистые нативные поля админки */
                  <KeySecretEditor
                    title="Настройки интеграции"
                    description="Сгенерированная форма параметров интеграции для администратора"
                    value={previewSettingsData}
                    schema={manifestData?.settings_form}
                    variant="flat"
                    onChange={(parsed) => setPreviewSettingsData(parsed)}
                  />
                ) : (
                  <div className="rounded-xl border border-dashed border-border/80 bg-muted/10 p-6 text-center space-y-3">
                    <div className="mx-auto size-10 rounded-full bg-primary/10 flex items-center justify-center text-primary">
                      <Sliders className="size-5" />
                    </div>
                    <div className="space-y-1">
                      <h4 className="text-sm font-semibold text-foreground">Секция settings_form отсутствует в манифесте</h4>
                      <p className="text-xs text-muted-foreground max-w-md mx-auto leading-relaxed">
                        Секция <code className="text-primary font-mono">settings_form</code> задаёт форму параметров интеграции, которую настраивает администратор при привязке скрипта к услуге (домен панели, токены доступа, API-ключи, режим sandbox/mock).
                      </p>
                    </div>
                  </div>
                )
              ) : activeTab === "client_order_form" ? (
                hasOrderForm ? (
                  /* Форма заказа на витрине */
                  <ManifestLivePreview
                    manifest={manifestJson}
                    previewType="client_order_form"
                  />
                ) : (
                  <div className="rounded-xl border border-dashed border-border/80 bg-muted/10 p-6 text-center space-y-3">
                    <div className="mx-auto size-10 rounded-full bg-primary/10 flex items-center justify-center text-primary">
                      <LayoutList className="size-5" />
                    </div>
                    <div className="space-y-1">
                      <h4 className="text-sm font-semibold text-foreground">Секция client_order_form отсутствует в манифесте</h4>
                      <p className="text-xs text-muted-foreground max-w-md mx-auto leading-relaxed">
                        Секция <code className="text-primary font-mono">client_order_form</code> генерирует интерактивную форму заказа на витрине магазина перед покупкой (логин, регион, публичный SSH-ключ, выбор ОС, конфигурация).
                      </p>
                    </div>
                  </div>
                )
              ) : activeTab === "view_layout" ? (
                hasViewLayout ? (
                  /* Виджет карточки выданной услуги в личном кабинете */
                  <ManifestLivePreview
                    manifest={manifestJson}
                    previewType="view_layout"
                  />
                ) : (
                  <div className="rounded-xl border border-dashed border-border/80 bg-muted/10 p-6 text-center space-y-3">
                    <div className="mx-auto size-10 rounded-full bg-primary/10 flex items-center justify-center text-primary">
                      <QrCode className="size-5" />
                    </div>
                    <div className="space-y-1">
                      <h4 className="text-sm font-semibold text-foreground">Схема view_layout отсутствует в манифесте</h4>
                      <p className="text-xs text-muted-foreground max-w-md mx-auto leading-relaxed">
                        Схема <code className="text-primary font-mono">view_layout</code> (Server-Driven UI) используется для отображения выданной услуги в личном кабинете покупателя (QR-код для подключения, кнопки копирования ссылок и ключей, бейджи статуса, инструкции).
                      </p>
                    </div>
                  </div>
                )
              ) : null}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}