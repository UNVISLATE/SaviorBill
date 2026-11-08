import React, { useRef, useState } from "react"
import { Eye, Edit3, Columns, FileUp, Sparkles } from "lucide-react"
import { Button } from "@/components/shadsnui/button"
import { Textarea } from "@/components/shadsnui/textarea"
import { MarkdownPreview } from "./MarkdownPreview"

interface MarkdownEditorProps {
  value: string
  onChange: (value: string) => void
  label?: string
  description?: string
  placeholder?: string
  className?: string
}

const KEY_DELIVERY_TEMPLATE = `### 🔑 Инструкция по активации ключа

Спасибо за покупку! Ваш лицензионный ключ отображен выше.

#### Шаги для активации:
1. Перейдите на официальный сайт сервиса или откройте приложение.
2. Авторизуйтесь под своей учетной записью.
3. В разделе **«Активация кода / Redeem Code»** вставьте полученный ключ.
4. Нажмите кнопку **«Применить»**.

> **Важно:** Сохраняйте этот ключ в надежном месте. При возникновении проблем обратитесь в службу поддержки.
`

export function MarkdownEditor({
  value,
  onChange,
  label = "Инструкция к товару (Markdown)",
  description = "Инструкция отобразится покупателю в окне статуса заказа после успешной оплаты",
  placeholder = "Введите текст инструкции в формате Markdown...",
  className = "",
}: MarkdownEditorProps) {
  const [viewMode, setViewMode] = useState<"edit" | "preview" | "split">("edit")
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    const reader = new FileReader()
    reader.onload = (event) => {
      const text = event.target?.result
      if (typeof text === "string") {
        onChange(text)
      }
    }
    reader.readAsText(file)
    // reset input
    e.target.value = ""
  }

  return (
    <div className={`space-y-2 rounded-xl border border-border/80 bg-muted/20 p-3.5 ${className}`}>
      {/* Header with title & actions */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <div className="text-xs font-semibold text-foreground flex items-center gap-1.5">
            {label}
          </div>
          {description && <div className="text-[11px] text-muted-foreground">{description}</div>}
        </div>

        <div className="flex items-center gap-1.5">
          {/* Hidden File Input */}
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileUpload}
            accept=".md,.markdown,.txt,text/markdown,text/plain"
            className="hidden"
          />

          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-7 text-xs gap-1"
            onClick={() => fileInputRef.current?.click()}
          >
            <FileUp className="size-3.5" /> Загрузить .md
          </Button>

          {!value && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-7 text-xs gap-1"
              onClick={() => onChange(KEY_DELIVERY_TEMPLATE)}
            >
              <Sparkles className="size-3.5" /> Вставить шаблон
            </Button>
          )}

          {/* View mode toggle */}
          <div className="flex items-center rounded-lg border border-border/60 bg-muted/40 p-0.5">
            <button
              type="button"
              onClick={() => setViewMode("edit")}
              className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors flex items-center gap-1 ${
                viewMode === "edit" ? "bg-background text-foreground shadow-xs" : "text-muted-foreground hover:text-foreground"
              }`}
              title="Режим редактирования"
            >
              <Edit3 className="size-3" /> Редактор
            </button>
            <button
              type="button"
              onClick={() => setViewMode("preview")}
              className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors flex items-center gap-1 ${
                viewMode === "preview" ? "bg-background text-foreground shadow-xs" : "text-muted-foreground hover:text-foreground"
              }`}
              title="Предпросмотр"
            >
              <Eye className="size-3" /> Предпросмотр
            </button>
            <button
              type="button"
              onClick={() => setViewMode("split")}
              className={`hidden sm:flex px-2 py-0.5 rounded text-[11px] font-medium transition-colors items-center gap-1 ${
                viewMode === "split" ? "bg-background text-foreground shadow-xs" : "text-muted-foreground hover:text-foreground"
              }`}
              title="Раздельный просмотр (Split)"
            >
              <Columns className="size-3" /> Сплит
            </button>
          </div>
        </div>
      </div>

      {/* Content Area */}
      {viewMode === "edit" && (
        <div className="space-y-1">
          <Textarea
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder={placeholder}
            rows={7}
            className="font-mono text-xs leading-relaxed resize-y bg-background/80"
          />
          <div className="flex items-center justify-between text-[10px] text-muted-foreground px-1">
            <span>Поддерживается разметка Markdown (заголовки, списки, цитаты, код)</span>
            <span>{value.length} символов</span>
          </div>
        </div>
      )}

      {viewMode === "preview" && (
        <MarkdownPreview content={value} className="min-h-[160px]" />
      )}

      {viewMode === "split" && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
          <div className="space-y-1">
            <Textarea
              value={value}
              onChange={(e) => onChange(e.target.value)}
              placeholder={placeholder}
              rows={9}
              className="font-mono text-xs leading-relaxed resize-y bg-background/80 h-full min-h-[180px]"
            />
          </div>
          <div className="overflow-auto max-h-[280px]">
            <MarkdownPreview content={value} className="h-full" />
          </div>
        </div>
      )}
    </div>
  )
}
