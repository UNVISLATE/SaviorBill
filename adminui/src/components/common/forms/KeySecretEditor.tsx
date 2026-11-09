import { useState, useEffect, useRef, useMemo } from "react"
import { Eye, EyeOff, Plus, Trash2, Copy, Check, Code2, SlidersHorizontal } from "lucide-react"
import { Button } from "@/components/shadsnui/button"
import { Input } from "@/components/shadsnui/input"
import { Label } from "@/components/shadsnui/label"
import { Switch } from "@/components/shadsnui/switch"
import { Textarea } from "@/components/shadsnui/textarea"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/shadsnui/select"

export interface FormFieldSchema {
  id: string
  type?: "text" | "password" | "number" | "toggle" | "checkbox" | "select" | string
  label?: string
  placeholder?: string
  description?: string
  required?: boolean
  default?: unknown
  options?: Array<{ value: string | number; label: string }>
}

interface KeyRow {
  id: string
  key: string
  value: string
  isSecret: boolean
}

export interface KeySecretEditorProps {
  value: Record<string, unknown> | string
  onChange: (parsed: Record<string, unknown>, jsonText: string) => void
  schema?: FormFieldSchema[]
  title?: string
  description?: string
  readOnly?: boolean
  variant?: "card" | "flat"
}

let rowCounter = 0
function generateRowId(): string {
  rowCounter += 1
  return `key-row-${Date.now()}-${rowCounter}`
}

export function KeySecretEditor({
  value,
  onChange,
  schema,
  title = "Параметры и секреты",
  description = "Значения шифруются и защищены от несанкционированного доступа",
  readOnly = false,
  variant = "flat",
}: KeySecretEditorProps) {
  const [mode, setMode] = useState<"visual" | "json">("visual")
  const [jsonText, setJsonText] = useState("")
  const [jsonError, setJsonError] = useState<string | null>(null)
  const [parsedData, setParsedData] = useState<Record<string, unknown>>({})
  const [rows, setRows] = useState<KeyRow[]>([])
  const [visibleSecrets, setVisibleSecrets] = useState<Record<string, boolean>>({})
  const [copiedKey, setCopiedKey] = useState<string | null>(null)

  const lastSerializedTextRef = useRef<string>("")

  // Parse external value
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

    if (text === lastSerializedTextRef.current) {
      return
    }

    lastSerializedTextRef.current = text
    setJsonText(text)
    setJsonError(null)
    setParsedData(parsed)

    const newRows: KeyRow[] = Object.entries(parsed).map(([k, v]) => ({
      id: generateRowId(),
      key: k,
      value: typeof v === "object" ? JSON.stringify(v) : String(v ?? ""),
      isSecret: /secret|password|token|key|hash|pass|cert/i.test(k),
    }))
    setRows(newRows)
  }, [value])

  const notifyChange = (updatedObj: Record<string, unknown>) => {
    const text = JSON.stringify(updatedObj, null, 2)
    lastSerializedTextRef.current = text
    setJsonText(text)
    setJsonError(null)
    setParsedData(updatedObj)

    const nextRows: KeyRow[] = Object.entries(updatedObj).map(([k, v]) => ({
      id: generateRowId(),
      key: k,
      value: typeof v === "object" ? JSON.stringify(v) : String(v ?? ""),
      isSecret: /secret|password|token|key|hash|pass|cert/i.test(k),
    }))
    setRows(nextRows)
    onChange(updatedObj, text)
  }

  // Handle changes when in schema-driven form mode
  const handleSchemaFieldChange = (fieldId: string, val: unknown) => {
    const next = { ...parsedData, [fieldId]: val }
    notifyChange(next)
  }

  // Dynamic row changes (when no schema or extra keys)
  const handleRowChange = (id: string, field: "key" | "value", val: string) => {
    setRows((prev) => {
      const next = prev.map((r) => {
        if (r.id !== id) return r
        const isSecret =
          field === "key" ? /secret|password|token|key|hash|pass|cert/i.test(val) : r.isSecret
        return { ...r, [field]: val, isSecret }
      })

      const obj: Record<string, unknown> = {}
      for (const r of next) {
        if (!r.key.trim()) continue
        let v: unknown = r.value
        if (v === "true") v = true
        else if (v === "false") v = false
        else if (!isNaN(Number(v)) && v !== "") v = Number(v)
        obj[r.key.trim()] = v
      }
      notifyChange(obj)
      return next
    })
  }

  const handleAddRow = () => {
    setRows((prev) => [
      ...prev,
      {
        id: generateRowId(),
        key: "",
        value: "",
        isSecret: false,
      },
    ])
  }

  const handleRemoveRow = (id: string, keyName?: string) => {
    setRows((prev) => prev.filter((r) => r.id !== id))
    if (keyName && keyName in parsedData) {
      const next = { ...parsedData }
      delete next[keyName]
      notifyChange(next)
    }
  }

  const handleJsonChange = (text: string) => {
    setJsonText(text)
    lastSerializedTextRef.current = text

    if (!text.trim()) {
      setJsonError(null)
      setRows([])
      setParsedData({})
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
      setParsedData(parsed)

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

  // Schema-based extra keys detection
  const schemaKeySet = useMemo(() => new Set((schema || []).map((f) => f.id)), [schema])
  const extraRows = useMemo(() => {
    if (!schema || schema.length === 0) return rows
    return rows.filter((r) => !schemaKeySet.has(r.key))
  }, [rows, schema, schemaKeySet])

  const containerClasses =
    variant === "card"
      ? "space-y-4 rounded-xl border border-border/70 bg-card/60 p-4 shadow-2xs"
      : "space-y-4"

  return (
    <div className={containerClasses}>
      {/* Шапка с переключателем режима */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 pb-3">
        <div>
          <h4 className="text-sm font-semibold tracking-tight text-foreground">{title}</h4>
          {description && <p className="text-xs text-muted-foreground">{description}</p>}
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

      {/* Режим 1: Визуальный редактор (нативная форма или строки) */}
      {mode === "visual" && (
        <div className="space-y-4">
          {schema && schema.length > 0 ? (
            /* Нативные элементы админки по схеме манифеста (без card) */
            <div className="space-y-4">
              {schema.map((f) => {
                const val = parsedData[f.id] ?? f.default
                const isSecret = f.type === "password" || /secret|password|token|key/i.test(f.id)
                const isVisible = visibleSecrets[f.id] ?? false

                if (f.type === "toggle" || f.type === "checkbox") {
                  return (
                    <div
                      key={f.id}
                      className="flex items-center justify-between rounded-lg border border-border/60 bg-muted/20 p-3 transition-colors hover:border-border"
                    >
                      <div className="space-y-0.5 pr-4">
                        <Label className="text-xs font-medium text-foreground cursor-pointer">
                          {f.label || f.id}
                          {f.required && <span className="text-destructive"> *</span>}
                        </Label>
                        {f.description && (
                          <p className="text-[11px] text-muted-foreground">{f.description}</p>
                        )}
                      </div>
                      <Switch
                        disabled={readOnly}
                        checked={Boolean(val)}
                        onCheckedChange={(checked) => handleSchemaFieldChange(f.id, checked)}
                      />
                    </div>
                  )
                }

                if (f.type === "select" && f.options && f.options.length > 0) {
                  return (
                    <div key={f.id} className="space-y-1.5">
                      <Label className="text-xs font-medium text-foreground">
                        {f.label || f.id}
                        {f.required && <span className="text-destructive"> *</span>}
                      </Label>
                      <Select
                        disabled={readOnly}
                        value={String(val ?? "")}
                        onValueChange={(nextVal) => handleSchemaFieldChange(f.id, nextVal)}
                      >
                        <SelectTrigger className="h-9 text-xs">
                          <SelectValue placeholder={f.placeholder || "Выберите вариант..."} />
                        </SelectTrigger>
                        <SelectContent>
                          {f.options.map((opt) => (
                            <SelectItem key={String(opt.value)} value={String(opt.value)}>
                              {opt.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      {f.description && (
                        <p className="text-[11px] text-muted-foreground">{f.description}</p>
                      )}
                    </div>
                  )
                }

                if (f.type === "number") {
                  return (
                    <div key={f.id} className="space-y-1.5">
                      <Label className="text-xs font-medium text-foreground">
                        {f.label || f.id}
                        {f.required && <span className="text-destructive"> *</span>}
                      </Label>
                      <Input
                        type="number"
                        disabled={readOnly}
                        value={val !== undefined && val !== null ? String(val) : ""}
                        placeholder={f.placeholder}
                        onChange={(e) =>
                          handleSchemaFieldChange(
                            f.id,
                            e.target.value === "" ? "" : Number(e.target.value)
                          )
                        }
                        className="h-9 text-xs font-mono"
                      />
                      {f.description && (
                        <p className="text-[11px] text-muted-foreground">{f.description}</p>
                      )}
                    </div>
                  )
                }

                return (
                  <div key={f.id} className="space-y-1.5">
                    <Label className="text-xs font-medium text-foreground">
                      {f.label || f.id}
                      {f.required && <span className="text-destructive"> *</span>}
                    </Label>
                    <div className="relative">
                      <Input
                        type={isSecret && !isVisible ? "password" : "text"}
                        disabled={readOnly}
                        value={String(val ?? "")}
                        placeholder={f.placeholder || (isSecret ? "••••••••" : "")}
                        onChange={(e) => handleSchemaFieldChange(f.id, e.target.value)}
                        className={`h-9 text-xs font-mono ${isSecret ? "pr-16" : ""}`}
                      />
                      {isSecret && (
                        <div className="absolute right-1 top-1/2 -translate-y-1/2 flex items-center gap-0.5">
                          <button
                            type="button"
                            onClick={() => toggleSecretVisibility(f.id)}
                            className="p-1 text-muted-foreground hover:text-foreground rounded cursor-pointer"
                            title={isVisible ? "Скрыть" : "Показать"}
                          >
                            {isVisible ? (
                              <EyeOff className="size-3.5" />
                            ) : (
                              <Eye className="size-3.5" />
                            )}
                          </button>
                          <button
                            type="button"
                            onClick={() => copyToClipboard(String(val ?? ""), f.id)}
                            className="p-1 text-muted-foreground hover:text-foreground rounded cursor-pointer"
                            title="Скопировать"
                          >
                            {copiedKey === f.id ? (
                              <Check className="size-3.5 text-emerald-500" />
                            ) : (
                              <Copy className="size-3.5" />
                            )}
                          </button>
                        </div>
                      )}
                    </div>
                    {f.description && (
                      <p className="text-[11px] text-muted-foreground">{f.description}</p>
                    )}
                  </div>
                )
              })}

              {/* Нестандартные параметры, если они есть в объекте */}
              {extraRows.length > 0 && (
                <div className="pt-3 border-t border-border/40 space-y-2">
                  <div className="text-xs font-medium text-muted-foreground">
                    Дополнительные параметры ({extraRows.length})
                  </div>
                  {extraRows.map((row) => (
                    <div
                      key={row.id}
                      className="group flex flex-col sm:flex-row sm:items-center gap-2 rounded-lg border border-border/60 bg-muted/20 p-2"
                    >
                      <div className="w-full sm:w-1/3">
                        <Input
                          value={row.key}
                          disabled={readOnly}
                          onChange={(e) => handleRowChange(row.id, "key", e.target.value)}
                          placeholder="ключ"
                          className="h-8 font-mono text-xs"
                        />
                      </div>
                      <div className="flex-1">
                        <Input
                          value={row.value}
                          disabled={readOnly}
                          onChange={(e) => handleRowChange(row.id, "value", e.target.value)}
                          placeholder="значение"
                          className="h-8 font-mono text-xs"
                        />
                      </div>
                      {!readOnly && (
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          onClick={() => handleRemoveRow(row.id, row.key)}
                          className="size-8 text-muted-foreground hover:text-destructive cursor-pointer"
                        >
                          <Trash2 className="size-3.5" />
                        </Button>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : rows.length === 0 ? (
            /* Без схемы и без строк — пустое состояние */
            <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border/80 py-8 text-center">
              <p className="text-xs text-muted-foreground mb-2">Параметры и ключи не заданы</p>
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
            /* Стандартные строки key-value */
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
                            {isVisible ? (
                              <EyeOff className="size-3.5" />
                            ) : (
                              <Eye className="size-3.5" />
                            )}
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
                          onClick={() => handleRemoveRow(row.id, row.key)}
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
            rows={8}
            className="font-mono text-xs bg-muted/20 resize-y"
            placeholder='{"key": "value"}'
          />
          {jsonError ? (
            <p className="text-xs text-destructive font-medium">{jsonError}</p>
          ) : (
            <p className="text-[11px] text-muted-foreground">
              Формат: JSON-объект ключ-значение. Изменения автоматически отражаются в режиме полей.
            </p>
          )}
        </div>
      )}
    </div>
  )
}
