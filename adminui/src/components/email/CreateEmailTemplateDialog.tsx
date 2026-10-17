import { useRef, useState, type DragEvent } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "react-router-dom"
import { FileUp, UploadCloud } from "lucide-react"

import { api } from "@/api/api.ts"
import { getErrorDetail } from "@/lib/api-error.ts"
import { toastError, toastSuccess } from "@/lib/toast"
import { cn } from "@/lib/utils"
import { Button } from "@/components/shadsnui/button"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/shadsnui/dialog"
import { Input } from "@/components/shadsnui/input"
import { Label } from "@/components/shadsnui/label"
import { Switch } from "@/components/shadsnui/switch"

const SLUG_RE = /^[a-z0-9][a-z0-9_.-]{1,63}$/

const DEFAULT_HTML_TEMPLATE = `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #1f2937; margin: 0; padding: 24px; background: #ffffff;">
  <h2 style="margin-top: 0; color: #111827;">Здравствуйте, {{ user.login }}!</h2>
  <p>Текст вашего письма...</p>
</body>
</html>
`

const DEFAULT_TEXT_TEMPLATE = `Здравствуйте, {{ user.login }}!

Текст вашего письма...
`

export function CreateEmailTemplateDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  onCreated?: (id: number) => void
}) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [slug, setSlug] = useState("")
  const [name, setName] = useState("")
  const [subject, setSubject] = useState("")
  const [isHtml, setIsHtml] = useState(true)
  const [body, setBody] = useState<string | null>(null)
  const [fileName, setFileName] = useState<string | null>(null)
  const [dragActive, setDragActive] = useState(false)

  const resetAndClose = () => {
    setSlug("")
    setName("")
    setSubject("")
    setIsHtml(true)
    setBody(null)
    setFileName(null)
    setDragActive(false)
    onOpenChange(false)
  }

  const loadFile = async (file: File) => {
    const text = await file.text()
    setBody(text)
    setFileName(file.name)
    // Если имя файла заканчивается на .txt, переключаем на текст
    if (file.name.toLowerCase().endsWith(".txt")) {
      setIsHtml(false)
    } else if (file.name.toLowerCase().endsWith(".html") || file.name.toLowerCase().endsWith(".htm")) {
      setIsHtml(true)
    }
    // Если слаг пустой, пробуем сформировать из имени файла
    if (!slug) {
      const base = file.name.replace(/\.[^.]+$/, "").toLowerCase().replace(/[^a-z0-9_.-]/g, "-")
      if (base) setSlug(base)
    }
  }

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setDragActive(false)
    const file = e.dataTransfer.files?.[0]
    if (file) void loadFile(file)
  }

  const create = useMutation({
    mutationFn: async () => {
      const finalSubject = subject.trim() || name.trim() || slug.trim() || "Без темы"
      const defaultBody = isHtml ? DEFAULT_HTML_TEMPLATE : DEFAULT_TEXT_TEMPLATE
      const finalBody = body !== null && body.trim().length > 0 ? body : defaultBody

      return (
        await api.post<{ id: number }>("/v1/admin/email/templates", {
          slug: slug.trim().toLowerCase(),
          name: name.trim() || null,
          subject: finalSubject,
          body: finalBody,
          is_html: isHtml,
        })
      ).data
    },
    onSuccess: (created) => {
      toastSuccess("Шаблон создан")
      void qc.invalidateQueries({ queryKey: ["admin-email-templates"] })
      resetAndClose()
      if (onCreated) {
        onCreated(created.id)
      } else {
        navigate(`/emailtemplate/${created.id}`)
      }
    },
    onError: (err: unknown) => {
      toastError("Не удалось создать шаблон", getErrorDetail(err))
    },
  })

  const slugValid = SLUG_RE.test(slug.trim().toLowerCase())

  return (
    <Dialog open={open} onOpenChange={(v) => (v ? onOpenChange(v) : resetAndClose())}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Новый email-шаблон</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1">
            <Label htmlFor="tpl-slug">Слаг (уникальный идентификатор)</Label>
            <Input
              id="tpl-slug"
              value={slug}
              onChange={(e) => setSlug(e.target.value.toLowerCase())}
              placeholder="order.delivered"
              className="font-mono text-sm"
              autoFocus
            />
            <p className="text-[11px] text-muted-foreground">
              Используется в коде для вызова отправки письма
            </p>
          </div>

          <div className="space-y-1">
            <Label htmlFor="tpl-name">Название (опционально)</Label>
            <Input
              id="tpl-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Уведомление о заказе"
            />
          </div>

          <div className="space-y-1">
            <Label htmlFor="tpl-subject">Тема письма (опционально)</Label>
            <Input
              id="tpl-subject"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="Ваш заказ {{ order.id }} выдан"
            />
            <p className="text-[11px] text-muted-foreground">
              Можно указать позже в редакторе (по умолчанию совпадает с названием)
            </p>
          </div>

          <div className="flex items-center justify-between rounded-lg border bg-muted/20 px-3 py-2">
            <div>
              <Label htmlFor="tpl-html" className="font-medium text-xs">
                HTML-формат
              </Label>
              <p className="text-[11px] text-muted-foreground">
                Верстка письма на HTML или простой текст
              </p>
            </div>
            <Switch
              id="tpl-html"
              checked={isHtml}
              onCheckedChange={setIsHtml}
            />
          </div>

          <div className="space-y-1.5">
            <Label>Тело письма (файл шаблона)</Label>
            <div
              className={cn(
                "flex flex-col items-center gap-2 rounded-lg border border-dashed p-4 text-center transition-colors",
                dragActive ? "border-primary bg-primary/5" : "border-muted-foreground/30",
              )}
              onDragOver={(e) => {
                e.preventDefault()
                setDragActive(true)
              }}
              onDragLeave={() => setDragActive(false)}
              onDrop={onDrop}
            >
              {fileName ? (
                <>
                  <FileUp className="size-6 text-primary" />
                  <p className="text-sm font-medium">{fileName}</p>
                  <p className="text-xs text-muted-foreground">
                    {(body ?? "").length} символов — загружено как тело шаблона
                  </p>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      setBody(null)
                      setFileName(null)
                    }}
                  >
                    Убрать файл
                  </Button>
                </>
              ) : (
                <>
                  <UploadCloud className="size-6 text-muted-foreground" />
                  <p className="text-sm text-muted-foreground">
                    Перетащите .html / .txt файл сюда или
                  </p>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => fileInputRef.current?.click()}
                  >
                    Выбрать файл
                  </Button>
                  <p className="text-xs text-muted-foreground">
                    …или оставьте пустым — откроется чистый шаблон в редакторе
                  </p>
                </>
              )}
              <input
                ref={fileInputRef}
                type="file"
                accept=".html,.htm,.txt,.jinja2,text/plain,text/html"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0]
                  if (file) void loadFile(file)
                  e.target.value = ""
                }}
              />
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={resetAndClose}>
            Отмена
          </Button>
          <Button
            disabled={!slugValid || create.isPending}
            onClick={() => create.mutate()}
          >
            {create.isPending ? "Создание…" : "Создать"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
