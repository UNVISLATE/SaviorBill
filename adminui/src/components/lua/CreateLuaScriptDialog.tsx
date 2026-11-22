import { useRef, useState, type DragEvent } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "react-router-dom"
import { FileCode2, FileUp, UploadCloud, X } from "lucide-react"

import { api } from "@/api/api.ts"
import { getErrorDetail } from "@/lib/api-error.ts"
import { toastError, toastSuccess } from "@/lib/toast"
import { cn } from "@/lib/utils"
import { Button } from "@/components/shadsnui/button"
import { Checkbox } from "@/components/shadsnui/checkbox"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/shadsnui/dialog"
import { Field, FieldLabel } from "@/components/shadsnui/field"
import { Input } from "@/components/shadsnui/input"
import { Textarea } from "@/components/shadsnui/textarea"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/shadsnui/select"

type Kind = "service" | "payment" | "auth" | "trigger" | "email" | "generic"

/** Действия, доступные для выбора по виду скрипта, и обязательные среди них
 * (см. `SystemScriptsMngr._check_actions` на backend — тот же список). */
const ACTIONS_BY_KIND: Record<Kind, { value: string; mandatory?: boolean }[]> = {
  service: [
    { value: "create" },
    { value: "renew" },
    { value: "stop" },
    { value: "delete" },
    { value: "freeze" },
  ],
  payment: [
    { value: "create", mandatory: true },
    { value: "callback", mandatory: true },
    { value: "check" },
    { value: "refund" },
  ],
  auth: [
    { value: "start", mandatory: true },
    { value: "callback", mandatory: true },
  ],
  email: [
    { value: "send", mandatory: true },
    { value: "test" },
  ],
  trigger: [],
  generic: [],
}

const KIND_TITLES: Record<Kind, string> = {
  service: "Услуга (доставка товара)",
  payment: "Платёж (провайдер оплаты)",
  auth: "OAuth (вход через провайдера)",
  email: "Почта (транспорт отправки email)",
  trigger: "Триггер (действие по событию)",
  generic: "Прочее",
}

/** Пустой шаблон — один и тот же для всех видов: скрипт сам ветвится по
 * `ctx.action` внутри `handle`, поэтому нет нужды в разных заготовках. */
const BLANK_TEMPLATE = `return {
  handle = function(ctx)
    -- ctx.action, ctx.user, ctx.service/payment/provider/trigger — см. документацию контекста
    return { public = {} }
  end,
}
`

const SLUG_RE = /^[a-z0-9][a-z0-9_-]{1,63}$/

function defaultActionsFor(kind: Kind): string[] {
  return ACTIONS_BY_KIND[kind].filter((a) => a.mandatory).map((a) => a.value)
}

/** Диалог создания Lua-скрипта: либо загрузить существующий файл (кнопка
 * или drag&drop), либо начать с чистого шаблона в редакторе — раньше
 * создать скрипт можно было только сырым вызовом API, в UI такой
 * возможности не было вообще (см. PLAN.md). */
export function CreateLuaScriptDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
}) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const manifestInputRef = useRef<HTMLInputElement>(null)

  const [slug, setSlug] = useState("")
  const [name, setName] = useState("")
  const [kind, setKind] = useState<Kind>("service")
  const [actions, setActions] = useState<string[]>(() => defaultActionsFor("service"))
  const [code, setCode] = useState<string | null>(null)
  const [settingsText, setSettingsText] = useState("{}")
  const [fileName, setFileName] = useState<string | null>(null)
  const [manifestText, setManifestText] = useState<string | null>(null)
  const [manifestFileName, setManifestFileName] = useState<string | null>(null)
  const [dragActive, setDragActive] = useState(false)

  function resetAndClose() {
    setSlug("")
    setName("")
    setKind("service")
    setActions(defaultActionsFor("service"))
    setCode(null)
    setSettingsText("{}")
    setFileName(null)
    setManifestText(null)
    setManifestFileName(null)
    onOpenChange(false)
  }

  function changeKind(next: Kind) {
    setKind(next)
    setActions(defaultActionsFor(next))
  }

  function toggleAction(value: string, mandatory: boolean | undefined) {
    if (mandatory) return
    setActions((prev) => (prev.includes(value) ? prev.filter((a) => a !== value) : [...prev, value]))
  }

  async function loadManifestFile(file: File) {
    try {
      const text = await file.text()
      const parsed = JSON.parse(text)
      setManifestText(text)
      setManifestFileName(file.name)

      // Автозаполнение полей из манифеста, если они ещё не заполнены
      if (!slug && (parsed.slug || parsed.id)) {
        const s = String(parsed.slug || parsed.id).toLowerCase().replace(/[^a-z0-9_-]/g, "-")
        if (SLUG_RE.test(s)) setSlug(s)
      }
      if (!name && parsed.name) {
        setName(String(parsed.name))
      }
      if (Array.isArray(parsed.actions) && parsed.actions.length > 0) {
        setActions(parsed.actions.map(String))
      }
      toastSuccess(`Манифест ${file.name} загружен`)
    } catch {
      toastError("Файл манифеста должен содержать валидный JSON")
    }
  }

  async function loadFile(file: File) {
    if (file.name.endsWith(".json")) {
      await loadManifestFile(file)
      return
    }
    if (!file.name.endsWith(".lua") && file.type && !file.type.startsWith("text/")) {
      toastError("Ожидается текстовый файл .lua или .json")
      return
    }
    const text = await file.text()
    setCode(text)
    setFileName(file.name)
    if (!slug) {
      const guess = file.name.replace(/\.lua$/i, "").toLowerCase().replace(/[^a-z0-9_-]/g, "-")
      if (SLUG_RE.test(guess)) setSlug(guess)
    }
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    setDragActive(false)
    const files = Array.from(e.dataTransfer.files || [])
    for (const f of files) {
      if (f.name.endsWith(".json")) {
        void loadManifestFile(f)
      } else if (f.name.endsWith(".lua") || (f.type && f.type.startsWith("text/"))) {
        void loadFile(f)
      }
    }
  }

  const create = useMutation({
    mutationFn: async () => {
      let settings: Record<string, unknown>
      try {
        const parsed = JSON.parse(settingsText || "{}")
        if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
          throw new Error("Настройки скрипта должны быть JSON-объектом")
        }
        settings = parsed as Record<string, unknown>
      } catch {
        throw new Error("Настройки скрипта должны быть валидным JSON")
      }

      if (manifestText) {
        try {
          settings.manifest = JSON.parse(manifestText)
        } catch {
          throw new Error("Манифест содержит невалидный JSON")
        }
      }

      return (
        await api.post<{ id: number }>("/v1/admin/lua", {
          slug,
          name: name.trim() || undefined,
          kind,
          actions,
          code: code ?? BLANK_TEMPLATE,
          settings,
        })
      ).data
    },
    onSuccess: (created) => {
      toastSuccess("Скрипт создан")
      void qc.invalidateQueries({ queryKey: ["admin-lua-scripts"] })
      resetAndClose()
      navigate(`/lua/${created.id}`)
    },
    onError: (err: unknown) => {
      toastError("Не удалось создать скрипт", getErrorDetail(err))
    },
  })

  const slugValid = SLUG_RE.test(slug)

  return (
    <Dialog open={open} onOpenChange={(v) => (v ? onOpenChange(v) : resetAndClose())}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Новый Lua-скрипт</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <Field>
            <FieldLabel htmlFor="new-slug">Slug (уникальный идентификатор)</FieldLabel>
            <Input
              id="new-slug"
              value={slug}
              onChange={(e) => setSlug(e.target.value.toLowerCase())}
              placeholder="my-service-integration"
              className="font-mono text-sm"
            />
          </Field>

          <Field>
            <FieldLabel htmlFor="new-name">Название (опционально)</FieldLabel>
            <Input id="new-name" value={name} onChange={(e) => setName(e.target.value)} />
          </Field>

          <Field>
            <FieldLabel>Вид скрипта</FieldLabel>
            <Select value={kind} onValueChange={(v) => v && changeKind(v as Kind)}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(Object.keys(KIND_TITLES) as Kind[]).map((k) => (
                  <SelectItem key={k} value={k}>
                    {KIND_TITLES[k]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>

          {ACTIONS_BY_KIND[kind].length > 0 && (
            <Field>
              <FieldLabel>Поддерживаемые действия</FieldLabel>
              <div className="flex flex-wrap gap-3">
                {ACTIONS_BY_KIND[kind].map((a) => (
                  <label
                    key={a.value}
                    className={cn(
                      "flex items-center gap-1.5 text-sm",
                      a.mandatory && "text-muted-foreground",
                    )}
                  >
                    <Checkbox
                      checked={actions.includes(a.value)}
                      disabled={a.mandatory}
                      onCheckedChange={() => toggleAction(a.value, a.mandatory)}
                    />
                    {a.value}
                    {a.mandatory && " (обязательно)"}
                  </label>
                ))}
              </div>
            </Field>
          )}

          <Field>
            <FieldLabel>Код скрипта</FieldLabel>
            <div
              className={cn(
                "flex flex-col items-center gap-2 rounded-md border border-dashed p-4 text-center transition-colors",
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
                  <FileUp className="size-6 text-muted-foreground" />
                  <p className="text-sm font-medium">{fileName}</p>
                  <p className="text-xs text-muted-foreground">
                    {(code ?? "").length} символов — будет содержимым первой версии
                  </p>
                  <Button size="sm" variant="ghost" onClick={() => { setCode(null); setFileName(null) }}>
                    Убрать файл
                  </Button>
                </>
              ) : (
                <>
                  <UploadCloud className="size-6 text-muted-foreground" />
                  <p className="text-sm text-muted-foreground">
                    Перетащите .lua-файл сюда или
                  </p>
                  <Button size="sm" variant="outline" onClick={() => fileInputRef.current?.click()}>
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
                accept=".lua,text/plain"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0]
                  if (file) void loadFile(file)
                  e.target.value = ""
                }}
              />
            </div>
          </Field>

          {/* Манифест (manifest.json) */}
          <Field>
            <div className="flex items-center justify-between">
              <FieldLabel>Манифест форм (manifest.json)</FieldLabel>
              <span className="text-[11px] text-muted-foreground">Опционально</span>
            </div>
            {manifestFileName ? (
              <div className="flex items-center justify-between p-3 rounded-lg border bg-muted/20">
                <div className="flex items-center gap-2 min-w-0">
                  <FileCode2 className="size-4 text-primary shrink-0" />
                  <div className="min-w-0">
                    <p className="text-xs font-semibold text-foreground truncate">{manifestFileName}</p>
                    <p className="text-[10px] text-emerald-500 font-medium">Манифест валиден (JSON OK)</p>
                  </div>
                </div>
                <Button
                  size="icon"
                  variant="ghost"
                  className="size-7"
                  onClick={() => {
                    setManifestText(null)
                    setManifestFileName(null)
                  }}
                  title="Удалить манифест"
                >
                  <X className="size-3.5" />
                </Button>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="w-full text-xs gap-1.5 h-9"
                  onClick={() => manifestInputRef.current?.click()}
                >
                  <FileCode2 className="size-3.5 text-primary" />
                  <span>Прикрепить manifest.json</span>
                </Button>
                <input
                  ref={manifestInputRef}
                  type="file"
                  accept=".json,application/json"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0]
                    if (file) void loadManifestFile(file)
                    e.target.value = ""
                  }}
                />
              </div>
            )}
          </Field>

          <Field>
            <FieldLabel htmlFor="new-settings">Настройки скрипта (`ctx.lua.settings`)</FieldLabel>
            <Textarea
              id="new-settings"
              value={settingsText}
              onChange={(e) => setSettingsText(e.target.value)}
              rows={4}
              className="font-mono text-xs"
              placeholder="{}"
            />
            <p className="text-xs text-muted-foreground">
              Общая конфигурация скрипта. Секреты храните в защищенных настройках
              провайдера, а не в этом JSON.
            </p>
          </Field>
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
