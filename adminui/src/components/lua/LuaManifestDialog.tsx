import { useEffect, useRef, useState } from "react"
import * as monaco from "monaco-editor"
import { Eye, Layers, Sparkles, Code2, Check } from "lucide-react"

import { ensureMonacoWorkers } from "@/lib/monaco-setup"
import { Button } from "@/components/shadsnui/button"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/shadsnui/dialog"
import { ManifestLivePreview } from "@unvislate/sbui-sdk"

interface LuaManifestDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  settingsText: string
  onSaveSettings: (nextSettingsText: string) => void
  scriptKind?: string
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
          { value: "windows-server-2025", label: "Windows Server 2025 Standard", price_delta: 500 },
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

export function LuaManifestDialog({
  open,
  onOpenChange,
  settingsText,
  onSaveSettings,
  scriptKind = "service",
}: LuaManifestDialogProps) {
  const editorHostRef = useRef<HTMLDivElement>(null)
  const editorRef = useRef<monaco.editor.IStandaloneCodeEditor | null>(null)
  const [manifestJson, setManifestJson] = useState("{}")
  const [parseError, setParseError] = useState<string | null>(null)

  // Extract manifest on open (strictly from settings, zero magic fallbacks)
  useEffect(() => {
    if (open) {
      try {
        const s = JSON.parse(settingsText || "{}")
        const m = s.manifest || (s.client_order_form || s.settings_form ? s : null)
        const text = m ? JSON.stringify(m, null, 2) : "{\n  \n}"
        setManifestJson(text)
        setParseError(null)
        if (editorRef.current) {
          editorRef.current.setValue(text)
        }
      } catch {
        const text = "{\n  \n}"
        setManifestJson(text)
        if (editorRef.current) {
          editorRef.current.setValue(text)
        }
      }
    }
  }, [open, settingsText])

  // Initialize Monaco Editor
  useEffect(() => {
    if (!open) return
    ensureMonacoWorkers()

    const timer = setTimeout(() => {
      if (!editorHostRef.current) return
      if (editorRef.current) {
        editorRef.current.setValue(manifestJson)
        return
      }

      const editor = monaco.editor.create(editorHostRef.current, {
        value: manifestJson,
        language: "json",
        theme: "vs-dark",
        automaticLayout: true,
        minimap: { enabled: false },
        fontSize: 12,
        tabSize: 2,
        scrollBeyondLastLine: false,
      })
      editorRef.current = editor

      editor.onDidChangeModelContent(() => {
        const val = editor.getValue()
        setManifestJson(val)
        try {
          JSON.parse(val)
          setParseError(null)
        } catch (e) {
          setParseError((e as Error).message)
        }
      })
    }, 50)

    return () => {
      clearTimeout(timer)
      if (editorRef.current) {
        editorRef.current.dispose()
        editorRef.current = null
      }
    }
  }, [open])

  const handleApplyTemplate = (key: string) => {
    const tmpl = TEMPLATES[key]
    if (!tmpl) return
    const text = JSON.stringify(tmpl, null, 2)
    setManifestJson(text)
    if (editorRef.current) {
      editorRef.current.setValue(text)
    }
  }

  const handleSave = () => {
    try {
      const parsedManifest = JSON.parse(manifestJson)
      const currentSettings = JSON.parse(settingsText || "{}")
      currentSettings.manifest = parsedManifest
      onSaveSettings(JSON.stringify(currentSettings, null, 2))
      onOpenChange(false)
    } catch {
      setParseError("Некорректный синтаксис JSON")
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh] flex flex-col p-4 sm:p-5 overflow-hidden">
        <DialogHeader className="pb-1">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div className="flex items-center gap-2">
              <div className="size-7 rounded-md bg-primary/10 text-primary flex items-center justify-center">
                <Layers className="size-4" />
              </div>
              <DialogTitle className="text-sm font-semibold">
                Манифест формы
              </DialogTitle>
            </div>

            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-7 text-xs gap-1"
              onClick={() => handleApplyTemplate(scriptKind === "payment" ? "payment" : "vps")}
            >
              <Sparkles className="size-3" /> Шаблон: {scriptKind === "payment" ? "Платёж" : "VPS"}
            </Button>
          </div>
        </DialogHeader>

        {/* Two-column layout: Editor on left, Preview on right */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 flex-1 min-h-[380px] overflow-hidden py-1">
          {/* Left: JSON Editor */}
          <div className="flex flex-col rounded-lg border border-border/80 overflow-hidden bg-background">
            <div className="px-3 py-1.5 bg-muted/40 border-b border-border/60 flex items-center justify-between text-[11px] font-medium text-muted-foreground">
              <span className="flex items-center gap-1.5">
                <Code2 className="size-3 text-primary" /> Редактор
              </span>
              {parseError ? (
                <span className="text-red-500 text-[10px]">Ошибка синтаксиса</span>
              ) : (
                <span className="text-emerald-500 text-[10px] flex items-center gap-1">
                  <Check className="size-2.5" /> JSON OK
                </span>
              )}
            </div>
            <div ref={editorHostRef} className="flex-1 w-full min-h-[320px]" />
          </div>

          {/* Right: Preview */}
          <div className="flex flex-col rounded-lg border border-border/80 overflow-hidden bg-zinc-950/40">
            <div className="px-3 py-1.5 bg-muted/40 border-b border-border/60 flex items-center justify-between text-[11px] font-medium text-muted-foreground">
              <span className="flex items-center gap-1.5">
                <Eye className="size-3 text-primary" /> Превью
              </span>
            </div>
            <div className="flex-1 overflow-y-auto p-2">
              <ManifestLivePreview manifest={manifestJson} previewType="client_order_form" />
            </div>
          </div>
        </div>

        <DialogFooter className="pt-2 border-t border-border/60">
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            Отмена
          </Button>
          <Button
            size="sm"
            disabled={Boolean(parseError)}
            onClick={handleSave}
            className="bg-primary text-primary-foreground hover:bg-primary/90"
          >
            Сохранить
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
