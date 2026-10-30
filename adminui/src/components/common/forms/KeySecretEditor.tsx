import { useState, useEffect, useRef } from "react"
import { Eye, EyeOff, Plus, Trash2, Copy, Check, Code2, SlidersHorizontal } from "lucide-react"
import { Button } from "@/components/shadsnui/button"
import { Input } from "@/components/shadsnui/input"
import { Label } from "@/components/shadsnui/label"
import { Textarea } from "@/components/shadsnui/textarea"

interface KeyRow {
  id: string
  key: string
  value: string
  isSecret: boolean
}

interface KeySecretEditorProps {
  value: Record<string, unknown> | string
  onChange: (parsed: Record<string, unknown>, jsonText: string) => void
  title?: string
  description?: string
  readOnly?: boolean
}

let rowCounter = 0
function generateRowId(): string {
  rowCounter += 1
  return `key-row-${Date.now()}-${rowCounter}`
}

export function KeySecretEditor({
  value,
  onChange,
  title = "Параметры и секреты",
  description = "Значения шифруются и защищены от несанкционированного доступа",
  readOnly = false,
}: KeySecretEditorProps) {
  const [mode, setMode] = useState<"visual" | "json">("visual")
  const [jsonText, setJsonText] = useState("")
  const [jsonError, setJsonError] = useState<string | null>(null)
  const [rows, setRows] = useState<KeyRow[]>([])
  const [visibleSecrets, setVisibleSecrets] = useState<Record<string, boolean>>({})
  const [copiedKey, setCopiedKey] = useState<string | null>(null)

  // Хранит последнее сериализованное значение, чтобы отличать внешние обновления от внутренних
  const lastSerializedTextRef = useRef<string>("")

  // Синхронизация внешнего value только когда оно реально отличается от внутреннего состояния
  useEffect(() => {
    let parsed: Record<string, unknown> = {}
    let text = "{}"

    if (typeof value === "string") {
      text = value.trim() || "{}"
      try {
        parsed = JSON.parse(text)
      } catch {
        parsed = {}
      }
    } else if (value && typeof value === "object") {
      parsed = value
      text = JSON.stringify(value, null, 2)
    }

    // Если значение пришло в результате нашего собственного onChange, не пересоздаём строки
    if (text === lastSerializedTextRef.current) {
      return
    }

    lastSerializedTextRef.current = text
    setJsonText(text)
    setJsonError(null)

    const newRows: KeyRow[] = Object.entries(parsed).map(([k, v]) => ({
      id: generateRowId(),
      key: k,
      value: typeof v === "object" ? JSON.stringify(v) : String(v ?? ""),
      isSecret: /secret|password|token|key|hash|pass|cert/i.test(k),
    }))
    setRows(newRows)
  }, [value])

  const notifyChange = (nextRows: KeyRow[]) => {
    const obj: Record<string, unknown> = {}
    for (const r of nextRows) {
      if (!r.key.trim()) continue
      let val: unknown = r.value
      if (val === "true") val = true
      else if (val === "false") val = false
      else if (!isNaN(Number(val)) && val !== "") val = Number(val)
      obj[r.key.trim()] = val
    }
    const text = JSON.stringify(obj, null, 2)
    lastSerializedTextRef.current = text
    setJsonText(text)
    setJsonError(null)
    onChange(obj, text)
  }

  const handleRowChange = (id: string, field: "key" | "value", val: string) => {
    setRows((prev) => {
      const next = prev.map((r) => {
        if (r.id !== id) return r
        const isSecret =
          field === "key" ? /secret|password|token|key|hash|pass|cert/i.test(val) : r.isSecret
        return { ...r, [field]: val, isSecret }
      })
      notifyChange(next)
      return next
    })
  }

  const handleAddRow = () => {
    setRows((prev) => {
      const next: KeyRow[] = [
        ...prev,
        {
          id: generateRowId(),
          key: "",
          value: "",
          isSecret: false,
        },
      ]
      notifyChange(next)
      return next
    })
  }

  const handleRemoveRow = (id: string) => {
    setRows((prev) => {
      const next = prev.filter((r) => r.id !== id)
      notifyChange(next)
      return next
    })
  }

  const handleJsonChange = (text: string) => {
    setJsonText(text)
    lastSerializedTextRef.current = text

    if (!text.trim()) {
      setJsonError(null)
      setRows([])
      onChange({}, "{}")
      return
    }

    try {
      const parsed = JSON.parse(text)
      if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
        setJsonError("JSON должен быть объектом { key: value }")
        return
      }
      setJsonError(null)
      const nextRows: KeyRow[] = Object.entries(parsed).map(([k, v]) => ({
        id: generateRowId(),
        key: k,
        value: typeof v === "object" ? JSON.stringify(v) : String(v ?? ""),
        isSecret: /secret|password|token|key|hash|pass|cert/i.test(k),
      }))
      setRows(nextRows)
      onChange(parsed, text)
    } catch (e) {
      setJsonError(e instanceof Error ? e.message : "Некорректный JSON")
    }
  }

  const toggleSecretVisibility = (id: string) => {
    setVisibleSecrets((prev) => ({ ...prev, [id]: !prev[id] }))
  }

  const copyToClipboard = (text: string, id: string) => {
    void navigator.clipboard.writeText(text)
    setCopiedKey(id)
    setTimeout(() => setCopiedKey(null), 1500)
  }

  return (
    <div className="space-y-3 rounded-xl border border-border/70 bg-card/60 p-4 shadow-2xs">
      {/* Шапка с переключателем режима */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 pb-3">
        <div>
          <h4 className="text-sm font-semibold tracking-tight">{title}</h4>
          {description && (
            <p className="text-xs text-muted-foreground">{description}</p>
          )}
        </div>

        <div className="flex items-center gap-2">
          <div className="flex items-center rounded-lg border border-border/80 bg-muted/40 p-0.5">
            <button
              type="button"
              onClick={() => setMode("visual")}
              className={`flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition-all cursor-pointer ${
                mode === "visual"
                  ? "bg-background text-foreground shadow-2xs"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <SlidersHorizontal className="size-3" />
              <span>Поля</span>
            </button>
            <button
              type="button"
              onClick={() => setMode("json")}
              className={`flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition-all cursor-pointer ${
                mode === "json"
                  ? "bg-background text-foreground shadow-2xs"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <Code2 className="size-3" />
              <span>JSON</span>
            </button>
          </div>
        </div>
      </div>

      {/* Режим 1: Визуальный редактор полей */}
      {mode === "visual" && (
        <div className="space-y-2.5">
          {rows.length === 0 ? (
            <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border/80 py-6 text-center">
              <p className="text-xs text-muted-foreground mb-2">
                Параметры и ключи не заданы
              </p>
              {!readOnly && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={handleAddRow}
                  className="h-7 text-xs gap-1.5"
                >
                  <Plus className="size-3.5" />
                  <span>Добавить параметр</span>
                </Button>
              )}
            </div>
          ) : (
            <div className="space-y-2">
              {rows.map((row) => {
                const isVisible = visibleSecrets[row.id] || !row.isSecret
                return (
                  <div
                    key={row.id}
                    className="group flex flex-col sm:flex-row sm:items-center gap-2 rounded-lg border border-border/60 bg-muted/20 p-2 transition-colors hover:border-border"
                  >
                    <div className="w-full sm:w-1/3">
                      <Label className="text-[10px] text-muted-foreground block mb-0.5 sm:hidden">
                        Ключ (Параметр)
                      </Label>
                      <Input
                        value={row.key}
                        disabled={readOnly}
                        onChange={(e) => handleRowChange(row.id, "key", e.target.value)}
                        placeholder="название_ключа"
                        className="h-8 font-mono text-xs"
                      />
                    </div>

                    <div className="relative flex-1">
                      <Label className="text-[10px] text-muted-foreground block mb-0.5 sm:hidden">
                        Значение
                      </Label>
                      <Input
                        type={isVisible ? "text" : "password"}
                        value={row.value}
                        disabled={readOnly}
                        onChange={(e) => handleRowChange(row.id, "value", e.target.value)}
                        placeholder="значение..."
                        className="h-8 pr-16 text-xs font-mono"
                      />
                      <div className="absolute right-1 top-1/2 -translate-y-1/2 flex items-center gap-0.5">
                        {row.isSecret && (
                          <button
                            type="button"
                            onClick={() => toggleSecretVisibility(row.id)}
                            className="p-1 text-muted-foreground hover:text-foreground rounded cursor-pointer"
                            title={isVisible ? "Скрыть значение" : "Показать значение"}
                          >
                            {isVisible ? <EyeOff className="size-3.5" /> : <Eye className="size-3.5" />}
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => copyToClipboard(row.value, row.id)}
                          className="p-1 text-muted-foreground hover:text-foreground rounded cursor-pointer"
                          title="Скопировать значение"
                        >
                          {copiedKey === row.id ? (
                            <Check className="size-3.5 text-emerald-500" />
                          ) : (
                            <Copy className="size-3.5" />
                          )}
                        </button>
                      </div>
                    </div>

                    {!readOnly && (
                      <div className="flex sm:self-center">
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          onClick={() => handleRemoveRow(row.id)}
                          className="h-8 w-8 text-muted-foreground hover:text-destructive cursor-pointer"
                          title="Удалить параметр"
                        >
                          <Trash2 className="size-4" />
                        </Button>
                      </div>
                    )}
                  </div>
                )
              })}

              {!readOnly && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={handleAddRow}
                  className="h-7 text-xs gap-1.5 mt-1 cursor-pointer"
                >
                  <Plus className="size-3.5" />
                  <span>Добавить параметр</span>
                </Button>
              )}
            </div>
          )}
        </div>
      )}

      {/* Режим 2: Прямой JSON редактор */}
      {mode === "json" && (
        <div className="space-y-2">
          <Textarea
            value={jsonText}
            readOnly={readOnly}
            onChange={(e) => handleJsonChange(e.target.value)}
            rows={7}
            className="font-mono text-xs bg-muted/20 resize-y"
            placeholder='{"key": "value"}'
          />
          {jsonError ? (
            <p className="text-xs text-destructive font-medium">{jsonError}</p>
          ) : (
            <p className="text-[11px] text-muted-foreground">
              Формат: JSON-объект ключ-значение. Изменения автоматически отражаются в визуальном режиме.
            </p>
          )}
        </div>
      )}
    </div>
  )
}
