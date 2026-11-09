import { useEffect, useRef, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import * as monaco from "monaco-editor"
import { ArrowLeft, Code2, Eye, FileUp, Save, Sparkles } from "lucide-react"

import { api } from "@/api/api.ts"
import { getErrorDetail } from "@/lib/api-error.ts"
import { ensureMonacoWorkers } from "@/lib/monaco-setup"
import { toastError, toastSuccess } from "@/lib/toast"
import { Button } from "@/components/shadsnui/button"
import { MarkdownPreview } from "@/components/common/MarkdownPreview"

interface ServiceDetail {
  id: number
  slug: string
  name?: string | null
  delivery: string
  settings?: Record<string, unknown>
  params?: Record<string, unknown>
  lock_version: number
}

const TEMPLATES: Record<string, string> = {
  key: `### 🔑 Инструкция по активации лицензионного ключа

Благодарим за покупку! Ваш персональный ключ доступа отображен выше.

#### Быстрый старт:
1. Перейдите на официальный сайт сервиса или откройте установленное приложение.
2. Авторизуйтесь в свой личный профиль.
3. Откройте раздел **«Активация кода / Redeem Code»** и введите полученный ключ.
4. Подтвердите активацию нажатием кнопки **«Применить»**.

> **Важно:** Сохраняйте этот ключ в надежном месте. При возникновении вопросов или задержек обратитесь в службу технической поддержки через раздел тикетов.
`,
  server: `### 🚀 Доступ к виртуальному серверу (VPS)

Ваш сервер успешно сконфигурирован и готов к работе!

#### Реквизиты подключения:
- **IP-адрес:** \`{ip_address}\`
- **Порт SSH:** \`22\`
- **Пользователь:** \`root\`
- **Авторизация:** по указанному вами SSH-ключу или временному паролю из письма.

#### Подключение через консоль (Linux / macOS / PowerShell):
\`\`\`bash
ssh root@{ip_address}
\`\`\`

#### Первоначальная настройка:
Рекомендуется сразу обновить пакеты системы:
\`\`\`bash
apt update && apt upgrade -y
\`\`\`

> **Безопасность:** Не передавайте реквизиты доступа третьим лицам.
`,
}

export function ServiceInstructionPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()

  const editorHostRef = useRef<HTMLDivElement>(null)
  const editorRef = useRef<monaco.editor.IStandaloneCodeEditor | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const isUpdatingFromCode = useRef(false)

  const [markdown, setMarkdown] = useState("")
  const [dirty, setDirty] = useState(false)

  // Fetch service details
  const { data: service } = useQuery({
    queryKey: ["admin-service", id ? Number(id) : null],
    queryFn: async () => (await api.get<ServiceDetail>(`/v1/admin/services/${id}`)).data,
    enabled: Boolean(id),
  })

  // Initialize Monaco Markdown Editor once
  useEffect(() => {
    ensureMonacoWorkers()
    if (!editorHostRef.current) return

    const editor = monaco.editor.create(editorHostRef.current, {
      value: markdown,
      language: "markdown",
      theme: "vs-dark",
      automaticLayout: true,
      wordWrap: "on",
      minimap: { enabled: false },
      fontSize: 13,
      tabSize: 2,
      scrollBeyondLastLine: false,
    })
    editorRef.current = editor

    const sub = editor.onDidChangeModelContent(() => {
      if (isUpdatingFromCode.current) return
      const val = editor.getValue()
      setMarkdown(val)
      setDirty(true)
    })

    return () => {
      sub.dispose()
      editor.dispose()
      editorRef.current = null
    }
  }, [])

  // Populate initial markdown from service settings
  useEffect(() => {
    if (!service) return
    const s = service.settings || {}
    const text = String((s as any).instructions_md || "")

    setMarkdown(text)
    setDirty(false)

    if (editorRef.current) {
      isUpdatingFromCode.current = true
      editorRef.current.setValue(text)
      isUpdatingFromCode.current = false
    }
  }, [service])

  const handleApplyTemplate = (key: string) => {
    const tmpl = TEMPLATES[key]
    if (!tmpl) return
    setMarkdown(tmpl)
    setDirty(true)
    if (editorRef.current) {
      isUpdatingFromCode.current = true
      editorRef.current.setValue(tmpl)
      isUpdatingFromCode.current = false
    }
  }

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    const reader = new FileReader()
    reader.onload = (event) => {
      const text = String(event.target?.result || "")
      setMarkdown(text)
      setDirty(true)
      if (editorRef.current) {
        isUpdatingFromCode.current = true
        editorRef.current.setValue(text)
        isUpdatingFromCode.current = false
      }
    }
    reader.readAsText(file)
    e.target.value = ""
  }

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!id) throw new Error("ID услуги не определён")
      const currentSettings = { ...(service?.settings || {}) }
      if (markdown.trim()) {
        currentSettings.instructions_md = markdown.trim()
      } else {
        delete currentSettings.instructions_md
      }

      return (
        await api.patch(`/v1/admin/services/${id}`, {
          settings: currentSettings,
          lock_version: service?.lock_version,
        })
      ).data
    },
    onSuccess: () => {
      setDirty(false)
      toastSuccess("Инструкция сохранена")
      void qc.invalidateQueries({ queryKey: ["admin-service", Number(id)] })
      void qc.invalidateQueries({ queryKey: ["admin-services"] })
    },
    onError: (e) => {
      toastError("Ошибка сохранения", getErrorDetail(e))
    },
  })

  return (
    <div className="-m-6 flex h-[calc(100vh-3rem)] flex-col bg-background">
      {/* Hidden file input */}
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileUpload}
        accept=".md,.markdown,.txt,text/markdown,text/plain"
        className="hidden"
      />

      {/* Top Bar */}
      <header className="flex h-12 items-center justify-between border-b border-border/60 px-4 sm:px-6 bg-muted/10 shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs"
            onClick={() => navigate(`/services/${id}`)}
          >
            <ArrowLeft className="size-3.5 mr-1" /> К услуге
          </Button>
          <div className="h-4 w-px bg-border/60" />
          <div className="flex items-center gap-1.5 text-xs truncate">
            <span className="text-muted-foreground">Услуги</span>
            <span className="text-muted-foreground">/</span>
            <span className="font-mono text-muted-foreground truncate">
              {service?.name || service?.slug || `#${id}`}
            </span>
            <span className="text-muted-foreground">/</span>
            <span className="font-semibold text-foreground">Инструкция (Markdown)</span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-7 text-xs gap-1"
            onClick={() => fileInputRef.current?.click()}
          >
            <FileUp className="size-3" /> Загрузить .md
          </Button>

          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-7 text-xs gap-1"
            onClick={() =>
              handleApplyTemplate(service?.delivery === "key" ? "key" : "server")
            }
          >
            <Sparkles className="size-3" /> Шаблон:{" "}
            {service?.delivery === "key" ? "Ключ" : "Сервер"}
          </Button>

          <Button
            type="button"
            size="sm"
            disabled={saveMutation.isPending || !dirty}
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
              <Code2 className="size-3.5 text-primary" /> Редактор Markdown
            </span>
            <span className="text-[11px] font-mono text-muted-foreground">
              {markdown.length} символов · {markdown.split("\n").length} строк
            </span>
          </div>
          <div ref={editorHostRef} className="flex-1 w-full min-h-0" />
        </div>

        {/* Right: Live Formatted Preview */}
        <div className="flex flex-col overflow-hidden bg-zinc-950/40">
          <div className="flex h-8 items-center justify-between border-b border-border/60 px-4 text-xs text-muted-foreground bg-muted/20 shrink-0">
            <span className="flex items-center gap-1.5 font-medium">
              <Eye className="size-3.5 text-primary" /> Превью для покупателя
            </span>
          </div>
          <div className="flex-1 overflow-y-auto p-6">
            <div className="max-w-2xl mx-auto rounded-xl border border-border/60 bg-card/60 p-5">
              {markdown.trim() ? (
                <MarkdownPreview content={markdown} />
              ) : (
                <div className="text-center py-12 text-xs text-muted-foreground">
                  Инструкция пуста. Введите текст слева или загрузите .md файл.
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
