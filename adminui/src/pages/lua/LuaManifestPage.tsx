import { useEffect, useRef, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import * as monaco from "monaco-editor"
import { ArrowLeft, Check, Code2, Eye, Save, Sparkles } from "lucide-react"

import { api } from "@/api/api.ts"
import { getErrorDetail } from "@/lib/api-error.ts"
import { ensureMonacoWorkers } from "@/lib/monaco-setup"
import { toastError, toastSuccess } from "@/lib/toast"
import { Button } from "@/components/shadsnui/button"
import { ManifestLivePreview } from "@unvislate/sbui-sdk"

interface LuaScriptDetail {
  id: number
  slug: string
  name?: string | null
  kind: string
  settings: Record<string, unknown>
  lock_version: number
}

const TEMPLATES: Record<string, any> = {
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

  // Fetch script details
  const { data: script } = useQuery({
    queryKey: ["admin-lua-script", scriptId ? Number(scriptId) : null],
    queryFn: async () => (await api.get<LuaScriptDetail>(`/v1/admin/lua/${scriptId}`)).data,
    enabled: Boolean(scriptId),
  })

  // Initialize Monaco Editor once
  useEffect(() => {
    ensureMonacoWorkers()
    if (!editorHostRef.current) return

    const editor = monaco.editor.create(editorHostRef.current, {
      value: manifestJson,
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

  // Sync script data into Monaco editor when loaded
  useEffect(() => {
    if (!script) return
    const s = script.settings || {}
    const m = (s as any).manifest || ((s as any).client_order_form || (s as any).settings_form ? s : null)
    const text = m ? JSON.stringify(m, null, 2) : "{\n  \n}"

    setManifestJson(text)
    setParseError(null)
    setDirty(false)

    if (editorRef.current) {
      isUpdatingFromCode.current = true
      editorRef.current.setValue(text)
      isUpdatingFromCode.current = false
    }
  }, [script])

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
        Object.keys(parsed).length === 0 ||
        (!parsed.client_order_form?.length && !parsed.settings_form?.length && !parsed.prefill)

      if (isEmpty) {
        delete currentSettings.manifest
      } else {
        currentSettings.manifest = parsed
      }

      return (
        await api.patch(`/v1/admin/lua/${scriptId}`, {
          settings: currentSettings,
          lock_version: script?.lock_version,
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
            <span className="text-muted-foreground">Скрипты</span>
            <span className="text-muted-foreground">/</span>
            <span className="font-mono text-muted-foreground truncate">{script?.slug}</span>
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
          </div>
          <div className="flex-1 overflow-y-auto p-6">
            <div className="max-w-xl mx-auto rounded-xl border border-border/60 bg-card/60 p-4">
              <ManifestLivePreview
                manifest={manifestJson}
                previewType={script?.kind === "payment" ? "settings_form" : "client_order_form"}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
