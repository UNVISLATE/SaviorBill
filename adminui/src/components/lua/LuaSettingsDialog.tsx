import { useEffect, useMemo, useRef, useState } from "react"
import * as monaco from "monaco-editor"
import { Plus, Trash2 } from "lucide-react"

import { ensureMonacoWorkers } from "@/lib/monaco-setup"
import { Button } from "@/components/shadsnui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/shadsnui/dialog"
import { Input } from "@/components/shadsnui/input"

type JsonObject = Record<string, unknown>
type SettingsMode = "fields" | "advanced"

function isObject(value: unknown): value is JsonObject {
  return value !== null && typeof value === "object" && !Array.isArray(value)
}

function parseObject(text: string): { value?: JsonObject; error?: string } {
  try {
    const parsed: unknown = JSON.parse(text || "{}")
    if (!isObject(parsed)) return { error: "Настройки должны быть JSON-объектом" }
    return { value: parsed }
  } catch {
    return { error: "Некорректный JSON" }
  }
}

function deleteAtPath(value: JsonObject, path: string[]): JsonObject {
  if (path.length === 0) return {}
  const [head, ...tail] = path
  if (tail.length === 0) {
    const next = { ...value }
    delete next[head]
    return next
  }
  if (!isObject(value[head])) return value
  return { ...value, [head]: deleteAtPath(value[head], tail) }
}

function displayValue(value: unknown): string {
  if (typeof value === "string") return value
  if (typeof value === "number" || typeof value === "boolean") return String(value)
  return JSON.stringify(value)
}

function FieldRows({
  value,
  onChange,
}: {
  value: JsonObject
  onChange: (value: JsonObject) => void
}) {
  const entries = Object.entries(value)
  return (
    <div className="space-y-2">
      {entries.map(([key, current]) => {
        const complex = typeof current === "object" && current !== null
        return (
          <div key={key} className="flex items-center gap-2">
            <Input
              defaultValue={key}
              className="h-8 min-w-0 flex-1 font-mono text-xs"
              aria-label={`Ключ ${key}`}
              onBlur={(event) => {
                const nextKey = event.target.value.trim()
                if (nextKey && nextKey !== key) {
                  const next = { ...value }
                  delete next[key]
                  next[nextKey] = current
                  onChange(next)
                }
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter") event.currentTarget.blur()
              }}
            />
            <span className="text-muted-foreground">:</span>
            <Input
              value={complex ? "[Сложное значение — редактируйте в JSON]" : displayValue(current)}
              readOnly={complex}
              onChange={(event) => {
                const raw = event.target.value
                const next =
                  typeof current === "number" ? Number(raw) :
                  typeof current === "boolean" ? raw === "true" : raw
                onChange({ ...value, [key]: next })
              }}
              className={`h-8 min-w-0 flex-1 font-mono text-xs ${complex ? "cursor-not-allowed text-muted-foreground" : ""}`}
              aria-label={`Значение ${key}`}
              title={complex ? "Переключитесь в расширенный режим для изменения сложного значения" : undefined}
            />
            <Button
              type="button"
              size="icon"
              variant="ghost"
              className="size-8 shrink-0 text-muted-foreground hover:text-destructive"
              aria-label={`Удалить ${key}`}
              onClick={() => onChange(deleteAtPath(value, path))}
            >
              <Trash2 className="size-3.5" />
            </Button>
          </div>
        )
      })}
    </div>
  )
}

function AddField({ onAdd }: { onAdd: (key: string) => void }) {
  const [key, setKey] = useState("")
  return (
    <div className="flex items-center gap-2">
      <Input
        value={key}
        onChange={(event) => setKey(event.target.value)}
        placeholder="Новый ключ"
        className="h-8 font-mono text-xs"
        onKeyDown={(event) => {
          if (event.key !== "Enter" || !key.trim()) return
          onAdd(key.trim())
          setKey("")
        }}
      />
      <Button
        type="button"
        size="sm"
        variant="ghost"
        disabled={!key.trim()}
        onClick={() => {
          onAdd(key.trim())
          setKey("")
        }}
      >
        <Plus className="size-3.5" /> Добавить параметр
      </Button>
    </div>
  )
}

export function LuaSettingsDialog({
  open,
  onOpenChange,
  value,
  onChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  value: string
  onChange: (value: string) => void
}) {
  const [mode, setMode] = useState<SettingsMode>("fields")
  const [draft, setDraft] = useState(value)
  const hostRef = useRef<HTMLDivElement>(null)
  const editorRef = useRef<monaco.editor.IStandaloneCodeEditor | null>(null)
  const parsed = useMemo(() => parseObject(draft), [draft])

  useEffect(() => {
    if (!open || mode !== "advanced" || !hostRef.current) return
    ensureMonacoWorkers()
    const editor = monaco.editor.create(hostRef.current, {
      value: draft,
      language: "json",
      theme: "vs-dark",
      automaticLayout: true,
      minimap: { enabled: false },
      fontSize: 13,
      scrollBeyondLastLine: false,
    })
    editorRef.current = editor
    const subscription = editor.onDidChangeModelContent(() => onChangeDraft(editor.getValue()))
    return () => {
      subscription.dispose()
      editor.dispose()
      editorRef.current = null
    }
  }, [mode, open]) // eslint-disable-line react-hooks/exhaustive-deps

  function onChangeDraft(next: string) {
    setDraft(next)
    onChange(next)
  }

  function switchMode(next: SettingsMode) {
    if (next === mode) return
    if (next === "fields" && !parsed.value) return
    setMode(next)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-full max-w-[640px]">
        <DialogHeader className="pr-10">
          <div className="space-y-2">
            <DialogTitle>Настройки скрипта</DialogTitle>
            <DialogDescription>
              Значения доступны Lua-коду через <code>ctx.lua.settings</code>.
            </DialogDescription>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="absolute top-3 right-12"
            onClick={() => switchMode(mode === "fields" ? "advanced" : "fields")}
          >
            {mode === "fields" ? "Расширенный режим" : "Простой режим"}
          </Button>
        </DialogHeader>
        {mode === "fields" && parsed.value ? (
          <div className="h-[320px] overflow-y-auto rounded-md border p-3">
            <FieldRows value={parsed.value} onChange={(next) => onChangeDraft(JSON.stringify(next, null, 2))} />
          </div>
        ) : (
          <div className="space-y-2">
            <div ref={hostRef} className="h-[320px] overflow-hidden rounded-md border" />
            {parsed.error && <p className="text-xs text-destructive">{parsed.error}</p>}
          </div>
        )}
        {mode === "fields" && parsed.value && (
          <AddField onAdd={(key) => onChangeDraft(JSON.stringify({ ...parsed.value, [key]: "" }, null, 2))} />
        )}
        <DialogFooter>
          <Button variant="outline" disabled={Boolean(parsed.error)} onClick={() => onOpenChange(false)}>
            Готово
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
