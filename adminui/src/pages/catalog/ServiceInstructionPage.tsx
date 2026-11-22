import { useEffect, useRef, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import * as monaco from "monaco-editor"
import {
  ArrowLeft,
  Code2,
  Eye,
  FileUp,
  Image as ImageIcon,
  Loader2,
  Save,
  Sparkles,
  Upload,
} from "lucide-react"

import { api } from "@/api/api.ts"
import { getErrorDetail } from "@/lib/api-error.ts"
import { ensureMonacoWorkers } from "@/lib/monaco-setup"
import { toastError, toastSuccess } from "@/lib/toast"
import { Button } from "@/components/shadsnui/button"
import { MarkdownPreview } from "@/components/common/MarkdownPreview"
import { MediaPickerDialog, type MediaPickerItem } from "@/components/media/MediaPickerDialog"
import { uploadOwnMedia } from "@/api/media-upload"

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
  const imageFileInputRef = useRef<HTMLInputElement>(null)
  const isUpdatingFromCode = useRef(false)

  const [markdown, setMarkdown] = useState("")
  const [dirty, setDirty] = useState(false)
  const [isMediaPickerOpen, setIsMediaPickerOpen] = useState(false)
  const [isUploadingImage, setIsUploadingImage] = useState(false)

  // Fetch service details
  const { data: service } = useQuery({
    queryKey: ["admin-service", id ? Number(id) : null],
    queryFn: async () => (await api.get<ServiceDetail>(`/v1/admin/services/${id}`)).data,
    enabled: Boolean(id),
  })

  const insertTextIntoMonaco = (textToInsert: string) => {
    const editor = editorRef.current
    if (!editor) return
    const selection = editor.getSelection()
    const range = selection || new monaco.Range(1, 1, 1, 1)
    editor.executeEdits("insert-image", [
      {
        range,
        text: textToInsert,
        forceMoveMarkers: true,
      },
    ])
    editor.focus()
  }

  const handleSelectMedia = (media: MediaPickerItem) => {
    const alt = media.name || media.tag || "изображение"
    insertTextIntoMonaco(`![${alt}](${media.url})\n`)
    setIsMediaPickerOpen(false)
  }

  const handleImageFile = async (file: File) => {
    if (!file.type.startsWith("image/")) {
      toastError("Ошибка", "Поддерживаются только изображения")
      return
    }

    setIsUploadingImage(true)
    try {
      const res = await uploadOwnMedia(file)
      const cleanName = file.name.replace(/\.[^/.]+$/, "") || "изображение"
      insertTextIntoMonaco(`![${cleanName}](/api/media/${res.token})\n`)
      toastSuccess("Изображение загружено и вставлено")
    } catch (e) {
      toastError("Не удалось загрузить изображение", getErrorDetail(e))
    } finally {
      setIsUploadingImage(false)
    }
  }

  const handleImageInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      void handleImageFile(file)
    }
    e.target.value = ""
  }

  // Initialize Monaco Markdown Editor once
  useEffect(() => {
    ensureMonacoWorkers()
    if (!editorHostRef.current) return

    const editor = monaco.editor.create(editorHostRef.current, {
      value: "",
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

    // Add context menu action for media library
    editor.addAction({
      id: "action-insert-media-picker",
      label: "🖼️ Выбрать изображение из медиатеки...",
      keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.KeyI],
      contextMenuGroupId: "9_media",
      contextMenuOrder: 1,
      run: () => {
        setIsMediaPickerOpen(true)
      },
    })

    // Add context menu action for uploading image file
    editor.addAction({
      id: "action-upload-media-file",
      label: "📤 Загрузить изображение с устройства...",
      keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyMod.Alt | monaco.KeyCode.KeyI],
      contextMenuGroupId: "9_media",
      contextMenuOrder: 2,
      run: () => {
        imageFileInputRef.current?.click()
      },
    })

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

  // Clipboard paste and drag-and-drop listener for images
  useEffect(() => {
    const el = editorHostRef.current
    if (!el) return

    const handlePaste = (e: ClipboardEvent) => {
      const items = e.clipboardData?.items
      if (!items) return
      for (let i = 0; i < items.length; i++) {
        if (items[i].type.startsWith("image/")) {
          const file = items[i].getAsFile()
          if (file) {
            e.preventDefault()
            void handleImageFile(file)
            break
          }
        }
      }
    }

    const handleDragOver = (e: DragEvent) => {
      if (e.dataTransfer?.types.includes("Files")) {
        e.preventDefault()
      }
    }

    const handleDrop = (e: DragEvent) => {
      const files = e.dataTransfer?.files
      if (files && files.length > 0) {
        const file = files[0]
        if (file.type.startsWith("image/")) {
          e.preventDefault()
          void handleImageFile(file)
        }
      }
    }

    el.addEventListener("paste", handlePaste)
    el.addEventListener("dragover", handleDragOver)
    el.addEventListener("drop", handleDrop)

    return () => {
      el.removeEventListener("paste", handlePaste)
      el.removeEventListener("dragover", handleDragOver)
      el.removeEventListener("drop", handleDrop)
    }
  }, [])

  // Populate initial markdown from service settings
  useEffect(() => {
    if (!service) return
    const s = (service.settings || {}) as Record<string, unknown>
    const text = typeof s.instructions_md === "string" ? s.instructions_md : ""

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
      {/* Hidden file input for markdown import */}
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileUpload}
        accept=".md,.markdown,.txt,text/markdown,text/plain"
        className="hidden"
      />

      {/* Hidden file input for direct image upload */}
      <input
        type="file"
        ref={imageFileInputRef}
        onChange={handleImageInputChange}
        accept="image/*"
        className="hidden"
      />

      {/* Media Picker Dialog */}
      <MediaPickerDialog
        open={isMediaPickerOpen}
        onOpenChange={setIsMediaPickerOpen}
        onSelect={handleSelectMedia}
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
            onClick={() => setIsMediaPickerOpen(true)}
            title="Выбрать изображение из медиатеки"
          >
            <ImageIcon className="size-3" /> Медиатека
          </Button>

          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-7 text-xs gap-1"
            disabled={isUploadingImage}
            onClick={() => imageFileInputRef.current?.click()}
            title="Загрузить изображение с устройства"
          >
            {isUploadingImage ? <Loader2 className="size-3 animate-spin" /> : <Upload className="size-3" />}
            <span>{isUploadingImage ? "Загрузка..." : "Загрузить фото"}</span>
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
        <div className="flex flex-col overflow-hidden bg-background/50">
          <div className="flex h-8 items-center justify-between border-b border-border/60 px-4 text-xs text-muted-foreground bg-muted/20 shrink-0">
            <span className="flex items-center gap-1.5 font-medium">
              <Eye className="size-3.5 text-primary" /> Превью для покупателя
            </span>
          </div>
          <div className="flex-1 overflow-y-auto p-6 lg:p-8">
            <div className="max-w-2xl mx-auto">
              {markdown.trim() ? (
                <MarkdownPreview content={markdown} bare />
              ) : (
                <div className="text-center py-16 text-xs text-muted-foreground border border-dashed border-border/60 rounded-xl p-8">
                  Инструкция пуста. Введите текст слева, выберите шаблон или вставьте изображение.
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
