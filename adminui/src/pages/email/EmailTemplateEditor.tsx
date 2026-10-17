import { useEffect, useRef, useState, useMemo, useCallback } from "react"
import * as monaco from "monaco-editor"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import {
  Check,
  Code2,
  Copy,
  ExternalLink,
  Eye,
  Laptop,
  Mail,
  MoreVertical,
  Pencil,
  Save,
  Smartphone,
  Sparkles,
} from "lucide-react"

import { api } from "@/api/api"
import { ensureMonacoWorkers } from "@/lib/monaco-setup"
import { getErrorDetail } from "@/lib/api-error"
import { toastError, toastSuccess } from "@/lib/toast"
import { Badge } from "@/components/shadsnui/badge"
import { Button } from "@/components/shadsnui/button"
import { Input } from "@/components/shadsnui/input"
import { Switch } from "@/components/shadsnui/switch"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/shadsnui/tooltip"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/shadsnui/dropdown-menu"
import { EditEmailTemplateDialog } from "@/components/email/EditEmailTemplateDialog"
import { cn } from "@/lib/utils"

export interface TemplateDetail {
  id: number
  slug: string
  name: string | null
  subject: string
  body: string
  is_html: boolean
  is_active: boolean
  description?: string | null
}

const SAMPLE_CONTEXT: Record<string, string | number> = {
  "user.login": "alex_dev",
  "user.email": "alex@example.com",
  "user.id": "42",
  "user.balance": "1 500.00 ₽",
  "user.bonus_balance": "250.00 ₽",
  "order.id": "1089",
  "order.service_name": "Premium VPN 1 Month",
  "order.amount": "499.00 ₽",
  "order.status": "Выдан",
  "service.name": "Premium VPN",
  "reset_link": "https://saviorbill.example/reset-password?token=sample_token_xyz123",
  "verify_link": "https://saviorbill.example/verify-email?token=sample_verify_xyz",
  "code": "849201",
  "site_name": "SaviorBill",
  "support_email": "support@saviorbill.test",
  "year": new Date().getFullYear(),
}

function interpolateVariables(text: string): string {
  let res = text
  for (const [k, v] of Object.entries(SAMPLE_CONTEXT)) {
    const re = new RegExp(`{{\\s*${k.replace(".", "\\.")}\\s*}}`, "g")
    res = res.replace(re, String(v))
  }
  // Заменяем оставшиеся переменные Jinja2 на аккуратный бейдж
  res = res.replace(
    /{{\s*([^}]+)\s*}}/g,
    '<span style="color: #6366f1; background: #eef2ff; padding: 2px 4px; border-radius: 4px; font-family: monospace; font-size: 0.85em;">[$1]</span>',
  )
  // Удаляем Jinja2 теги управления {% ... %}
  res = res.replace(/{%\s*([^%]+)\s*%}/g, "")
  return res
}

function buildEmailDocument(content: string, isHtml: boolean): string {
  const interpolated = interpolateVariables(content)

  if (!isHtml) {
    return `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      font-size: 14px;
      line-height: 1.6;
      color: #1f2937;
      background: #ffffff;
      padding: 24px;
      white-space: pre-wrap;
      word-break: break-word;
      margin: 0;
    }
  </style>
</head>
<body>${interpolated}</body>
</html>`
  }

  // Если HTML не содержит <html> обёртки, добавляем стандартную основу email
  if (!interpolated.toLowerCase().includes("<html")) {
    return `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      margin: 0;
      padding: 24px;
      background: #ffffff;
      color: #1f2937;
      line-height: 1.5;
    }
    img { max-width: 100%; height: auto; }
    a { color: #2563eb; text-decoration: underline; }
  </style>
</head>
<body>${interpolated}</body>
</html>`
  }

  return interpolated
}

export function EmailTemplateEditor({
  template,
  canEdit,
}: {
  template: TemplateDetail
  canEdit: boolean
}) {
  const qc = useQueryClient()
  const editorHostRef = useRef<HTMLDivElement>(null)
  const editorRef = useRef<monaco.editor.IStandaloneCodeEditor | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  const [name, setName] = useState(template.name ?? "")
  const [description, setDescription] = useState(template.description ?? "")
  const [subject, setSubject] = useState(template.subject)
  const [isHtml, setIsHtml] = useState(template.is_html)
  const [isActive, setIsActive] = useState(template.is_active)
  const [bodyCode, setBodyCode] = useState(template.body)
  const [copied, setCopied] = useState(false)
  const [viewMode, setViewMode] = useState<"desktop" | "mobile">("desktop")

  const [editMetaOpen, setEditMetaOpen] = useState(false)
  const [isPreviewCollapsed, setIsPreviewCollapsed] = useState(() => {
    return localStorage.getItem("sb_email_preview_collapsed") === "true"
  })
  const [splitPercent, setSplitPercent] = useState<number>(() => {
    const saved = localStorage.getItem("sb_email_split_percent")
    return saved ? Number(saved) : 50
  })
  const [isDragging, setIsDragging] = useState(false)

  // Синхронизация при смене открытого шаблона
  useEffect(() => {
    setName(template.name ?? "")
    setDescription(template.description ?? "")
    setSubject(template.subject)
    setIsHtml(template.is_html)
    setIsActive(template.is_active)
    setBodyCode(template.body)
    if (editorRef.current && editorRef.current.getValue() !== template.body) {
      editorRef.current.setValue(template.body)
    }
  }, [template])

  // Сохранение состояния сплита и сворачивания в localStorage
  useEffect(() => {
    localStorage.setItem("sb_email_preview_collapsed", String(isPreviewCollapsed))
  }, [isPreviewCollapsed])

  useEffect(() => {
    localStorage.setItem("sb_email_split_percent", String(splitPercent))
  }, [splitPercent])

  // Проверка изменений
  const isDirty =
    name !== (template.name ?? "") ||
    description !== (template.description ?? "") ||
    subject !== template.subject ||
    isHtml !== template.is_html ||
    isActive !== template.is_active ||
    bodyCode !== template.body

  // Инициализация Monaco редактора
  useEffect(() => {
    ensureMonacoWorkers()
    if (!editorHostRef.current) return

    const editor = monaco.editor.create(editorHostRef.current, {
      value: template.body,
      language: isHtml ? "html" : "plaintext",
      theme: "vs-dark",
      automaticLayout: true,
      minimap: { enabled: false },
      fontSize: 13,
      readOnly: !canEdit,
      scrollBeyondLastLine: false,
      tabSize: 2,
      wordWrap: "on",
      lineNumbers: "on",
    })
    editorRef.current = editor

    const sub = editor.onDidChangeModelContent(() => {
      setBodyCode(editor.getValue())
    })

    return () => {
      sub.dispose()
      editor.dispose()
      editorRef.current = null
    }
  }, [template.id, isHtml, canEdit, template.body])

  // Сохранение изменений
  const save = useMutation({
    mutationFn: async () => {
      await api.patch(`/v1/admin/email/templates/${template.id}`, {
        name: name.trim() || null,
        description: description.trim() || null,
        subject: subject.trim(),
        is_html: isHtml,
        is_active: isActive,
      })
      await api.put(`/v1/admin/email/templates/${template.id}/body`, {
        body: bodyCode,
      })
    },
    onSuccess: () => {
      toastSuccess("Шаблон сохранён")
      void qc.invalidateQueries({ queryKey: ["admin-email-templates"] })
      void qc.invalidateQueries({ queryKey: ["admin-email-template-detail", template.id] })
    },
    onError: (e: unknown) => {
      toastError("Ошибка сохранения", getErrorDetail(e))
    },
  })

  // Горячая клавиша Ctrl+S / Cmd+S
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault()
        if (canEdit && isDirty && !save.isPending) {
          save.mutate()
        }
      }
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [canEdit, isDirty, save])

  // Логика перетаскивания разделителя (drag resize)
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    setIsDragging(true)

    const onMouseMove = (moveEvent: MouseEvent) => {
      if (!containerRef.current) return
      const rect = containerRef.current.getBoundingClientRect()
      const newPercent = ((moveEvent.clientX - rect.left) / rect.width) * 100
      // Ограничиваем от 20% до 80%
      setSplitPercent(Math.min(80, Math.max(20, newPercent)))
    }

    const onMouseUp = () => {
      setIsDragging(false)
      window.removeEventListener("mousemove", onMouseMove)
      window.removeEventListener("mouseup", onMouseUp)
    }

    window.addEventListener("mousemove", onMouseMove)
    window.addEventListener("mouseup", onMouseUp)
  }, [])

  const previewDocument = useMemo(() => {
    return buildEmailDocument(bodyCode, isHtml)
  }, [bodyCode, isHtml])

  const previewSubject = useMemo(() => {
    return interpolateVariables(subject)
  }, [subject])

  function handleCopyCode() {
    void navigator.clipboard.writeText(bodyCode)
    setCopied(true)
    toastSuccess("Код скопирован в буфер")
    setTimeout(() => setCopied(false), 2000)
  }

  function handleOpenNewTab() {
    const blob = new Blob([previewDocument], { type: "text/html;charset=utf-8" })
    const url = URL.createObjectURL(blob)
    window.open(url, "_blank")
  }

  return (
    <div className="flex h-full flex-col gap-2.5 min-h-0">
      {/* 1. Верхняя панель: Название + Действия (троеточие, тумблеры, сохранить) */}
      <div className="flex items-center justify-between gap-3 rounded-xl border bg-card px-4 py-2.5 shadow-xs shrink-0">
        <div className="flex items-center gap-2.5 min-w-0">
          <h1 className="text-base font-semibold text-foreground truncate">
            {name || template.slug}
          </h1>
          <Badge variant="outline" className="font-mono text-xs text-muted-foreground shrink-0">
            {template.slug}
          </Badge>
          {isDirty && (
            <span className="flex items-center gap-1 text-xs text-amber-500 font-medium animate-pulse shrink-0">
              ● Не сохранено
            </span>
          )}
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          {/* Если предпросмотр свёрнут — кнопка развернуть */}
          {isPreviewCollapsed && (
            <Tooltip>
              <TooltipTrigger
                render={
                  <Button
                    type="button"
                    variant="outline"
                    size="icon"
                    className="size-8 text-muted-foreground hover:text-foreground"
                    onClick={() => setIsPreviewCollapsed(false)}
                  >
                    <Eye className="size-4" />
                  </Button>
                }
              />
              <TooltipContent>Развернуть предпросмотр</TooltipContent>
            </Tooltip>
          )}

          {/* Троеточие с выпадающим меню */}
          <DropdownMenu>
            <DropdownMenuTrigger
              render={
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="size-8 text-muted-foreground hover:text-foreground"
                  aria-label="Настройки шаблона"
                >
                  <MoreVertical className="size-4" />
                </Button>
              }
            />
            <DropdownMenuContent align="end" className="w-56">
              {canEdit && (
                <DropdownMenuItem onClick={() => setEditMetaOpen(true)}>
                  <Pencil className="size-4 mr-2" />
                  <span>Редактировать...</span>
                </DropdownMenuItem>
              )}
              <DropdownMenuSeparator />
              <div
                className="flex items-center justify-between px-2.5 py-1.5 text-xs text-foreground cursor-pointer"
                onClick={() => canEdit && setIsHtml(!isHtml)}
              >
                <span>HTML-формат</span>
                <Switch
                  checked={isHtml}
                  onCheckedChange={setIsHtml}
                  disabled={!canEdit}
                  onClick={(e) => e.stopPropagation()}
                />
              </div>
              <div
                className="flex items-center justify-between px-2.5 py-1.5 text-xs text-foreground cursor-pointer"
                onClick={() => canEdit && setIsActive(!isActive)}
              >
                <span>Активен</span>
                <Switch
                  checked={isActive}
                  onCheckedChange={setIsActive}
                  disabled={!canEdit}
                  onClick={(e) => e.stopPropagation()}
                />
              </div>
            </DropdownMenuContent>
          </DropdownMenu>

          {/* Сохранить — ТОЛЬКО иконка, с всплывающим тултипом "Сохранить (Ctrl+S)" */}
          {canEdit && (
            <Tooltip>
              <TooltipTrigger
                render={
                  <span tabIndex={0} className="inline-flex">
                    <Button
                      size="icon"
                      className={cn(
                        "size-8 transition-all",
                        isDirty ? "bg-primary text-primary-foreground shadow-sm hover:bg-primary/90" : "opacity-60",
                      )}
                      onClick={() => save.mutate()}
                      disabled={!isDirty || save.isPending}
                      aria-label="Сохранить (Ctrl+S)"
                    >
                      <Save className="size-4" />
                    </Button>
                  </span>
                }
              />
              <TooltipContent>Сохранить (Ctrl+S)</TooltipContent>
            </Tooltip>
          )}
        </div>
      </div>

      {/* 2. Рабочее пространство с изменяемым сплитом */}
      <div
        ref={containerRef}
        className={cn(
          "flex flex-1 min-h-0 w-full overflow-hidden relative select-none",
          !isDragging && "select-text",
        )}
      >
        {/* Оверлей при перетаскивании для предотвращения захвата событий мыши iframe */}
        {isDragging && <div className="fixed inset-0 z-50 cursor-col-resize select-none" />}

        {/* Столбик 1 (Слева): Тема письма + Редактор кода */}
        <div
          className="flex flex-col gap-2 min-h-0 min-w-0"
          style={{ width: isPreviewCollapsed ? "100%" : `${splitPercent}%` }}
        >
          {/* Поле темы письма */}
          <div className="flex items-center gap-2 rounded-lg border bg-muted/20 px-3 py-1.5 shadow-2xs shrink-0">
            <span className="text-xs font-medium text-muted-foreground shrink-0">
              Тема письма (Jinja2):
            </span>
            <Input
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="Например: Сброс пароля для {{ user.login }}"
              disabled={!canEdit}
              className="h-7 border-0 bg-transparent px-1 font-mono text-xs focus-visible:ring-0 shadow-none"
            />
          </div>

          {/* Карточка Monaco Редактора */}
          <div className="flex flex-1 flex-col rounded-xl border bg-card shadow-xs min-h-[300px] overflow-hidden">
            <div className="flex items-center justify-between border-b bg-muted/40 px-3 py-2 text-xs shrink-0">
              <div className="flex items-center gap-2 font-medium text-foreground">
                <Code2 className="size-4 text-primary" />
                <span>Редактор кода ({isHtml ? "HTML" : "Текст"})</span>
              </div>
              <div className="flex items-center gap-1">
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-xs"
                  className="size-6 text-muted-foreground hover:text-foreground"
                  onClick={handleCopyCode}
                  title="Скопировать код"
                >
                  {copied ? <Check className="size-3 text-emerald-500" /> : <Copy className="size-3" />}
                </Button>
              </div>
            </div>
            <div ref={editorHostRef} className="flex-1 min-h-0 w-full" />
          </div>
        </div>

        {/* Разделитель (Draggable Splitter Handle) */}
        {!isPreviewCollapsed && (
          <div
            role="separator"
            tabIndex={0}
            aria-orientation="vertical"
            aria-label="Изменить пропорции колонок"
            onMouseDown={handleMouseDown}
            className={cn(
              "w-2 relative flex items-center justify-center cursor-col-resize group select-none shrink-0 transition-colors mx-0.5",
              isDragging && "cursor-col-resize",
            )}
          >
            <div
              className={cn(
                "w-1 h-8 rounded-full bg-border transition-all duration-150 group-hover:bg-primary group-hover:w-1.5 group-hover:h-12",
                isDragging && "bg-primary w-1.5 h-12",
              )}
            />
          </div>
        )}

        {/* Столбик 2 (Справа): Живой предпросмотр */}
        {!isPreviewCollapsed && (
          <div
            className="flex flex-col rounded-xl border bg-card shadow-xs min-h-[300px] overflow-hidden min-w-0"
            style={{ width: `${100 - splitPercent}%` }}
          >
            {/* Панель управления предпросмотром */}
            <div className="flex items-center justify-between border-b bg-muted/40 px-3 py-2 text-xs shrink-0">
              <div className="flex items-center gap-2 font-medium text-foreground truncate">
                <Eye className="size-4 text-emerald-500 shrink-0" />
                <span className="truncate">Предпросмотр письма</span>
                <span className="hidden sm:inline-flex items-center gap-1 rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground shrink-0">
                  <Sparkles className="size-2.5 text-primary" /> Демо-данные
                </span>
              </div>

              <div className="flex items-center gap-1.5 shrink-0">
                <div className="flex items-center rounded-lg border bg-background p-0.5 shadow-2xs">
                  <button
                    type="button"
                    onClick={() => setViewMode("desktop")}
                    className={cn(
                      "flex size-6 items-center justify-center rounded-md transition",
                      viewMode === "desktop"
                        ? "bg-muted text-foreground"
                        : "text-muted-foreground hover:text-foreground",
                    )}
                    title="Десктоп"
                  >
                    <Laptop className="size-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => setViewMode("mobile")}
                    className={cn(
                      "flex size-6 items-center justify-center rounded-md transition",
                      viewMode === "mobile"
                        ? "bg-muted text-foreground"
                        : "text-muted-foreground hover:text-foreground",
                    )}
                    title="Мобильный (380px)"
                  >
                    <Smartphone className="size-3.5" />
                  </button>
                </div>

                <Button
                  type="button"
                  variant="ghost"
                  size="icon-xs"
                  className="size-6 text-muted-foreground hover:text-foreground"
                  onClick={handleOpenNewTab}
                  title="Открыть в новой вкладке"
                >
                  <ExternalLink className="size-3" />
                </Button>

                {/* Глазик: свернуть предпросмотр */}
                <Tooltip>
                  <TooltipTrigger
                    render={
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon-xs"
                        className="size-6 text-muted-foreground hover:text-foreground"
                        onClick={() => setIsPreviewCollapsed(true)}
                        aria-label="Свернуть предпросмотр"
                      >
                        <Eye className="size-3.5" />
                      </Button>
                    }
                  />
                  <TooltipContent>Свернуть предпросмотр</TooltipContent>
                </Tooltip>
              </div>
            </div>

            {/* Визуальная имитация почтового клиента */}
            <div className="flex flex-1 flex-col overflow-hidden bg-muted/20 min-h-0">
              <div className="border-b bg-background/80 px-4 py-2.5 text-xs space-y-1 shrink-0">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-semibold text-sm text-foreground truncate">
                    {previewSubject || "Без темы"}
                  </span>
                  <span className="text-[11px] text-muted-foreground shrink-0">
                    Сегодня, {new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                  </span>
                </div>
                <div className="flex items-center gap-1 text-[11px] text-muted-foreground truncate">
                  <Mail className="size-3 shrink-0" />
                  <span className="font-medium text-foreground">SaviorBill</span>
                  <span>&lt;noreply@saviorbill.test&gt;</span>
                  <span className="mx-1">→</span>
                  <span className="truncate">alex_dev &lt;alex@example.com&gt;</span>
                </div>
              </div>

              {/* Тело письма */}
              <div className="flex-1 overflow-auto p-3 flex justify-center items-start min-h-0">
                <div
                  className={cn(
                    "h-full overflow-hidden rounded-lg bg-white shadow-md border transition-all duration-200",
                    viewMode === "desktop" ? "w-full" : "w-[380px] max-w-full",
                  )}
                >
                  <iframe
                    title="Email Live Preview"
                    srcDoc={previewDocument}
                    className="size-full border-0 bg-white"
                    sandbox="allow-same-origin"
                  />
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Диалог редактирования метаданных */}
      {editMetaOpen && (
        <EditEmailTemplateDialog
          open={editMetaOpen}
          onOpenChange={setEditMetaOpen}
          template={{
            id: template.id,
            slug: template.slug,
            name,
            description,
          }}
          onUpdated={(updatedName, updatedDesc) => {
            setName(updatedName)
            if (updatedDesc !== undefined) setDescription(updatedDesc)
          }}
        />
      )}
    </div>
  )
}
