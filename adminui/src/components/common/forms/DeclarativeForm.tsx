import { useState, useEffect } from "react"
import { Code2, SlidersHorizontal, Plus, Trash2 } from "lucide-react"
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

export type FieldType =
  | "text"
  | "password"
  | "number"
  | "boolean"
  | "select"
  | "date"
  | "color"
  | "textarea"

export interface FormFieldDef {
  key: string
  label: string
  type: FieldType
  description?: string
  placeholder?: string
  required?: boolean
  options?: { value: string; label: string }[] // для select
  default?: unknown
}

export interface FormSchema {
  title?: string
  description?: string
  fields: FormFieldDef[]
}

interface DeclarativeFormProps {
  schema?: FormSchema | null
  value: Record<string, unknown> | string
  onChange: (value: Record<string, unknown>, jsonText: string) => void
  readOnly?: boolean
  className?: string
}

export function DeclarativeForm({
  schema,
  value,
  onChange,
  readOnly = false,
  className = "",
}: DeclarativeFormProps) {
  const [mode, setMode] = useState<"visual" | "json">("visual")
  const [jsonText, setJsonText] = useState("{}")
  const [jsonError, setJsonError] = useState<string | null>(null)
  const [formData, setFormData] = useState<Record<string, unknown>>({})
  // Для случая, когда схемы нет: динамические пары ключ-значение
  const [genericPairs, setGenericPairs] = useState<{ id: string; key: string; value: string }[]>([])

  // Синхронизация извне
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

    setFormData(parsed)
    setJsonText(text)

    if (!schema || !schema.fields || schema.fields.length === 0) {
      const pairs = Object.entries(parsed).map(([k, v], idx) => ({
        id: `pair-${idx}-${k}`,
        key: k,
        value: typeof v === "object" ? JSON.stringify(v) : String(v ?? ""),
      }))
      setGenericPairs(pairs)
    }
  }, [value, schema])

  const notifyChange = (newData: Record<string, unknown>) => {
    setFormData(newData)
    const text = JSON.stringify(newData, null, 2)
    setJsonText(text)
    setJsonError(null)
    onChange(newData, text)
  }

  const handleFieldChange = (key: string, val: unknown) => {
    const next = { ...formData, [key]: val }
    notifyChange(next)
  }

  const handleGenericPairChange = (id: string, field: "key" | "value", val: string) => {
    const nextPairs = genericPairs.map((p) => (p.id === id ? { ...p, [field]: val } : p))
    setGenericPairs(nextPairs)

    const nextData: Record<string, unknown> = {}
    for (const p of nextPairs) {
      if (!p.key.trim()) continue
      let v: unknown = p.value
      if (v === "true") v = true
      else if (v === "false") v = false
      else if (!isNaN(Number(v)) && v !== "") v = Number(v)
      nextData[p.key.trim()] = v
    }
    notifyChange(nextData)
  }

  const handleAddGenericPair = () => {
    const nextPairs = [
      ...genericPairs,
      { id: `pair-${Date.now()}-${Math.random()}`, key: "", value: "" },
    ]
    setGenericPairs(nextPairs)
  }

  const handleRemoveGenericPair = (id: string) => {
    const nextPairs = genericPairs.filter((p) => p.id !== id)
    setGenericPairs(nextPairs)
    const nextData: Record<string, unknown> = {}
    for (const p of nextPairs) {
      if (!p.key.trim()) continue
      nextData[p.key.trim()] = p.value
    }
    notifyChange(nextData)
  }

  const handleJsonChange = (text: string) => {
    setJsonText(text)
    if (!text.trim()) {
      setJsonError(null)
      setFormData({})
      setGenericPairs([])
      onChange({}, "{}")
      return
    }
    try {
      const parsed = JSON.parse(text)
      if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
        setJsonError("JSON должен быть объектом { ... }")
        return
      }
      setJsonError(null)
      setFormData(parsed)
      if (!schema || !schema.fields || schema.fields.length === 0) {
        const pairs = Object.entries(parsed).map(([k, v], idx) => ({
          id: `pair-${idx}-${k}`,
          key: k,
          value: typeof v === "object" ? JSON.stringify(v) : String(v ?? ""),
        }))
        setGenericPairs(pairs)
      }
      onChange(parsed, text)
    } catch (e) {
      setJsonError(e instanceof Error ? e.message : "Некорректный JSON")
    }
  }

  const hasSchema = Boolean(schema && schema.fields && schema.fields.length > 0)

  return (
    <div className={`space-y-3 rounded-xl border border-border/70 bg-card/60 p-4 shadow-2xs ${className}`}>
      {/* Шапка */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 pb-3">
        <div>
          <h4 className="text-sm font-semibold tracking-tight">
            {schema?.title || "Конфигурация параметров"}
          </h4>
          {schema?.description && (
            <p className="text-xs text-muted-foreground">{schema.description}</p>
          )}
        </div>

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
            <span>Форма</span>
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

      {/* Режим 1: Визуальный */}
      {mode === "visual" && (
        <div className="space-y-3">
          {hasSchema ? (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {schema!.fields.map((field) => {
                const curVal = formData[field.key] ?? field.default ?? ""
                const isFullWidth = field.type === "textarea"

                return (
                  <div
                    key={field.key}
                    className={`space-y-1.5 ${isFullWidth ? "sm:col-span-2" : ""}`}
                  >
                    <div className="flex items-center justify-between">
                      <Label className="text-xs font-medium">
                        {field.label}
                        {field.required && <span className="text-destructive ml-1">*</span>}
                      </Label>
                    </div>

                    {/* Поле: text / password */}
                    {(field.type === "text" || field.type === "password") && (
                      <Input
                        type={field.type}
                        value={String(curVal)}
                        disabled={readOnly}
                        placeholder={field.placeholder}
                        onChange={(e) => handleFieldChange(field.key, e.target.value)}
                        className="h-8 text-xs font-mono"
                      />
                    )}

                    {/* Поле: number */}
                    {field.type === "number" && (
                      <Input
                        type="number"
                        value={String(curVal)}
                        disabled={readOnly}
                        placeholder={field.placeholder}
                        onChange={(e) =>
                          handleFieldChange(
                            field.key,
                            e.target.value === "" ? "" : Number(e.target.value),
                          )
                        }
                        className="h-8 text-xs font-mono"
                      />
                    )}

                    {/* Поле: boolean (Switch) */}
                    {field.type === "boolean" && (
                      <div className="flex items-center justify-between rounded-lg border border-border/60 bg-muted/20 px-3 py-1.5">
                        <span className="text-xs text-muted-foreground">
                          {curVal ? "Включено" : "Выключено"}
                        </span>
                        <Switch
                          checked={Boolean(curVal)}
                          disabled={readOnly}
                          onCheckedChange={(c) => handleFieldChange(field.key, c)}
                        />
                      </div>
                    )}

                    {/* Поле: select */}
                    {field.type === "select" && (
                      <Select
                        value={String(curVal)}
                        disabled={readOnly}
                        onValueChange={(val) => handleFieldChange(field.key, val)}
                      >
                        <SelectTrigger className="h-8 text-xs">
                          <SelectValue placeholder={field.placeholder || "Выберите значение"} />
                        </SelectTrigger>
                        <SelectContent>
                          {field.options?.map((opt) => (
                            <SelectItem key={opt.value} value={opt.value}>
                              {opt.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )}

                    {/* Поле: date */}
                    {field.type === "date" && (
                      <Input
                        type="date"
                        value={String(curVal)}
                        disabled={readOnly}
                        onChange={(e) => handleFieldChange(field.key, e.target.value)}
                        className="h-8 text-xs"
                      />
                    )}

                    {/* Поле: color */}
                    {field.type === "color" && (
                      <div className="flex items-center gap-2">
                        <input
                          type="color"
                          value={String(curVal || "#000000")}
                          disabled={readOnly}
                          onChange={(e) => handleFieldChange(field.key, e.target.value)}
                          className="h-8 w-12 cursor-pointer rounded border border-border/80 bg-background p-1"
                        />
                        <Input
                          value={String(curVal)}
                          disabled={readOnly}
                          onChange={(e) => handleFieldChange(field.key, e.target.value)}
                          placeholder="#ffffff"
                          className="h-8 font-mono text-xs flex-1"
                        />
                      </div>
                    )}

                    {/* Поле: textarea */}
                    {field.type === "textarea" && (
                      <Textarea
                        value={String(curVal)}
                        disabled={readOnly}
                        rows={3}
                        placeholder={field.placeholder}
                        onChange={(e) => handleFieldChange(field.key, e.target.value)}
                        className="font-mono text-xs"
                      />
                    )}

                    {field.description && (
                      <p className="text-[10px] text-muted-foreground">{field.description}</p>
                    )}
                  </div>
                )
              })}
            </div>
          ) : (
            /* Нет схемы: универсальный редактор пар ключ-значение */
            <div className="space-y-2">
              {genericPairs.length === 0 ? (
                <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border/80 py-6 text-center">
                  <p className="text-xs text-muted-foreground mb-2">
                    Параметры не заданы (пустой объект)
                  </p>
                  {!readOnly && (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={handleAddGenericPair}
                      className="h-7 text-xs gap-1.5 cursor-pointer"
                    >
                      <Plus className="size-3.5" />
                      <span>Добавить параметр</span>
                    </Button>
                  )}
                </div>
              ) : (
                <div className="space-y-2">
                  {genericPairs.map((p) => (
                    <div
                      key={p.id}
                      className="group flex flex-col sm:flex-row sm:items-center gap-2 rounded-lg border border-border/60 bg-muted/20 p-2 transition-colors hover:border-border"
                    >
                      <div className="w-full sm:w-1/3">
                        <Input
                          value={p.key}
                          disabled={readOnly}
                          onChange={(e) => handleGenericPairChange(p.id, "key", e.target.value)}
                          placeholder="ключ"
                          className="h-8 font-mono text-xs"
                        />
                      </div>
                      <div className="flex-1">
                        <Input
                          value={p.value}
                          disabled={readOnly}
                          onChange={(e) => handleGenericPairChange(p.id, "value", e.target.value)}
                          placeholder="значение"
                          className="h-8 font-mono text-xs"
                        />
                      </div>
                      {!readOnly && (
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          onClick={() => handleRemoveGenericPair(p.id)}
                          className="h-8 w-8 text-muted-foreground hover:text-destructive cursor-pointer"
                        >
                          <Trash2 className="size-4" />
                        </Button>
                      )}
                    </div>
                  ))}

                  {!readOnly && (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={handleAddGenericPair}
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
        </div>
      )}

      {/* Режим 2: Прямой JSON */}
      {mode === "json" && (
        <div className="space-y-2">
          <Textarea
            value={jsonText}
            readOnly={readOnly}
            onChange={(e) => handleJsonChange(e.target.value)}
            rows={7}
            className="font-mono text-xs bg-muted/20 resize-y"
            placeholder="{}"
          />
          {jsonError ? (
            <p className="text-xs text-destructive font-medium">{jsonError}</p>
          ) : (
            <p className="text-[11px] text-muted-foreground">
              Прямой ввод JSON конфигурации. Корректные поля моментально обновляют форму.
            </p>
          )}
        </div>
      )}
    </div>
  )
}
