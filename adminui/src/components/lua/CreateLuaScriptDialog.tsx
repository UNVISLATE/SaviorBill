import { useRef, useState, type DragEvent } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "react-router-dom"
import { FileUp, UploadCloud } from "lucide-react"

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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/shadsnui/select"

type Kind = "service" | "payment" | "auth" | "trigger" | "generic"

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
  trigger: [],
  generic: [],
}

const KIND_TITLES: Record<Kind, string> = {
  service: "Услуга (доставка товара)",
  payment: "Платёж (провайдер оплаты)",
  auth: "OAuth (вход через провайдера)",
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

  const [slug, setSlug] = useState("")
  const [name, setName] = useState("")
  const [kind, setKind] = useState<Kind>("service")
  const [actions, setActions] = useState<string[]>(() => defaultActionsFor("service"))
  const [code, setCode] = useState<string | null>(null)
  const [fileName, setFileName] = useState<string | null>(null)
  const [dragActive, setDragActive] = useState(false)

  function resetAndClose() {
    setSlug("")
    setName("")
    setKind("service")
    setActions(defaultActionsFor("service"))
    setCode(null)
    setFileName(null)
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

  async function loadFile(file: File) {
    if (!file.name.endsWith(".lua") && file.type && !file.type.startsWith("text/")) {
      toastError("Ожидается текстовый файл .lua")
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
    const file = e.dataTransfer.files?.[0]
    if (file) void loadFile(file)
  }

  const create = useMutation({
    mutationFn: async () =>
      (
        await api.post<{ id: number }>("/v1/admin/lua", {
          slug,
          name: name.trim() || undefined,
          kind,
          actions,
          code: code ?? BLANK_TEMPLATE,
        })
      ).data,
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
