import { useState, useEffect } from "react"
import { Plus, Trash2, Code2, SlidersHorizontal, Sparkles } from "lucide-react"
import { Button } from "@/components/shadsnui/button"
import { Input } from "@/components/shadsnui/input"
import { Label } from "@/components/shadsnui/label"
import { Textarea } from "@/components/shadsnui/textarea"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/shadsnui/dropdown-menu"

export interface RuleRow {
  id: string
  path: string
  value: string
  type: "string" | "number" | "boolean"
}

interface ConditionRuleBuilderProps {
  event?: string
  value: Record<string, unknown> | string
  onChange: (parsed: Record<string, unknown>, jsonText: string) => void
  readOnly?: boolean
}

// Популярные поля в контексте различных событий
const SUGGESTED_FIELDS_BY_EVENT: Record<string, { path: string; label: string; example: string }[]> = {
  "payment.paid": [
    { path: "payment.target", label: "Цель платежа (service / topup)", example: "service" },
    { path: "payment.currency", label: "Валюта платежа", example: "RUB" },
    { path: "payment.provider_slug", label: "Платёжная система", example: "yookassa" },
    { path: "payment.amount", label: "Сумма платежа", example: "1000" },
  ],
  "payment.refunded": [
    { path: "payment.target", label: "Цель платежа", example: "service" },
    { path: "payment.currency", label: "Валюта", example: "RUB" },
  ],
  "order.created": [
    { path: "order.service_id", label: "ID услуги", example: "1" },
    { path: "order.currency", label: "Валюта заказа", example: "RUB" },
    { path: "order.status", label: "Статус заказа", example: "pending" },
  ],
  "service.delivered": [
    { path: "service.id", label: "ID услуги", example: "1" },
    { path: "delivery_type", label: "Тип доставки", example: "key" },
  ],
  "service.keys.low": [
    { path: "service_id", label: "ID услуги", example: "1" },
  ],
  "service.keys.empty": [
    { path: "service_id", label: "ID услуги", example: "1" },
  ],
  "user.registered": [
    { path: "user.is_verified", label: "Email подтверждён", example: "false" },
  ],
}

export function ConditionRuleBuilder({
  event,
  value,
  onChange,
  readOnly = false,
}: ConditionRuleBuilderProps) {
  const [mode, setMode] = useState<"visual" | "json">("visual")
  const [jsonText, setJsonText] = useState("")
  const [jsonError, setJsonError] = useState<string | null>(null)
  const [rules, setRules] = useState<RuleRow[]>([])

  // Инициализация из внешнего значения
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

    setJsonText(text)

    const newRules: RuleRow[] = Object.entries(parsed).map(([k, v], idx) => {
      let t: "string" | "number" | "boolean" = "string"
      if (typeof v === "boolean") t = "boolean"
      else if (typeof v === "number") t = "number"
      return {
        id: `rule-${idx}-${k}`,
        path: k,
        value: String(v ?? ""),
        type: t,
      }
    })
    setRules(newRules)
  }, [value])

  const notifyChange = (updatedRules: RuleRow[]) => {
    const obj: Record<string, unknown> = {}
    for (const r of updatedRules) {
      if (!r.path.trim()) continue
      let val: unknown = r.value
      if (r.type === "boolean") {
        val = r.value === "true"
      } else if (r.type === "number") {
        const num = Number(r.value)
        val = isNaN(num) ? r.value : num
      }
      obj[r.path.trim()] = val
    }
    const text = JSON.stringify(obj, null, 2)
    setJsonText(text)
    setJsonError(null)
    onChange(obj, text)
  }

  const handleRuleChange = (
    id: string,
    field: "path" | "value" | "type",
    val: string,
  ) => {
    const updated = rules.map((r) => {
      if (r.id !== id) return r
      const next = { ...r, [field]: val }
      if (field === "type" && val === "boolean" && next.value !== "true" && next.value !== "false") {
        next.value = "true"
      }
      return next
    })
    setRules(updated)
    notifyChange(updated)
  }

  const handleAddRule = (suggestedPath?: string, defaultValue?: string) => {
    const newRule: RuleRow = {
      id: `rule-${Date.now()}-${Math.random()}`,
      path: suggestedPath || "",
      value: defaultValue || "",
      type: defaultValue === "true" || defaultValue === "false" ? "boolean" : "string",
    }
    const updated = [...rules, newRule]
    setRules(updated)
    notifyChange(updated)
  }

  const handleRemoveRule = (id: string) => {
    const updated = rules.filter((r) => r.id !== id)
    setRules(updated)
    notifyChange(updated)
  }

  const handleJsonChange = (text: string) => {
    setJsonText(text)
    if (!text.trim()) {
      setJsonError(null)
      setRules([])
      onChange({}, "{}")
      return
    }
    try {
      const parsed = JSON.parse(text)
      if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
        setJsonError("Условия должны быть объектом { \"путь.поля\": \"значение\" }")
        return
      }
      setJsonError(null)
      const nextRules: RuleRow[] = Object.entries(parsed).map(([k, v], idx) => {
        let t: "string" | "number" | "boolean" = "string"
        if (typeof v === "boolean") t = "boolean"
        else if (typeof v === "number") t = "number"
        return {
          id: `rule-${idx}-${k}`,
          path: k,
          value: String(v ?? ""),
          type: t,
        }
      })
      setRules(nextRules)
      onChange(parsed, text)
    } catch (e) {
      setJsonError(e instanceof Error ? e.message : "Некорректный JSON")
    }
  }

  const currentSuggestions = (event && SUGGESTED_FIELDS_BY_EVENT[event]) || [
    { path: "payment.target", label: "Цель платежа", example: "service" },
    { path: "payment.currency", label: "Валюта", example: "RUB" },
    { path: "order.service_id", label: "ID услуги", example: "1" },
  ]

  return (
    <div className="space-y-3 rounded-xl border border-border/70 bg-card/60 p-4 shadow-2xs">
      {/* Шапка */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 pb-3">
        <div>
          <h4 className="text-sm font-semibold tracking-tight">Условия срабатывания (Контекст)</h4>
          <p className="text-xs text-muted-foreground">
            Триггер выполнится только если все указанные условия совпадут с данными события
          </p>
        </div>

        <div className="flex items-center gap-2">
          {currentSuggestions.length > 0 && !readOnly && (
            <DropdownMenu>
              <DropdownMenuTrigger
                render={
                  <Button variant="outline" size="sm" className="h-7 text-xs gap-1.5 cursor-pointer">
                    <Sparkles className="size-3.5 text-amber-500" />
                    <span>Добавить поле...</span>
                  </Button>
                }
              />
              <DropdownMenuContent align="end" className="w-64">
                {currentSuggestions.map((s) => (
                  <DropdownMenuItem
                    key={s.path}
                    onClick={() => handleAddRule(s.path, s.example)}
                    className="flex flex-col items-start gap-0.5 text-xs cursor-pointer py-1.5"
                  >
                    <span className="font-mono font-medium text-primary">{s.path}</span>
                    <span className="text-[10px] text-muted-foreground">{s.label}</span>
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          )}

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
              <span>Правила</span>
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

      {/* Режим 1: Визуальный конструктор правил */}
      {mode === "visual" && (
        <div className="space-y-2.5">
          {rules.length === 0 ? (
            <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border/80 py-6 text-center">
              <p className="text-xs text-muted-foreground mb-1">
                Условия не заданы — триггер будет срабатывать на все события этого типа.
              </p>
              {!readOnly && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => handleAddRule()}
                  className="h-7 text-xs gap-1.5 mt-2 cursor-pointer"
                >
                  <Plus className="size-3.5" />
                  <span>Добавить условие фильтрации</span>
                </Button>
              )}
            </div>
          ) : (
            <div className="space-y-2">
              {rules.map((rule) => (
                <div
                  key={rule.id}
                  className="group flex flex-col sm:flex-row sm:items-center gap-2 rounded-lg border border-border/60 bg-muted/20 p-2 transition-colors hover:border-border"
                >
                  <div className="w-full sm:w-5/12">
                    <Label className="text-[10px] text-muted-foreground block mb-0.5 sm:hidden">
                      Точечный путь к полю
                    </Label>
                    <Input
                      value={rule.path}
                      disabled={readOnly}
                      onChange={(e) => handleRuleChange(rule.id, "path", e.target.value)}
                      placeholder="payment.currency"
                      className="h-8 font-mono text-xs"
                    />
                  </div>

                  <div className="flex items-center text-xs font-semibold text-muted-foreground shrink-0 px-1">
                    =
                  </div>

                  <div className="flex-1 flex items-center gap-1.5">
                    {rule.type === "boolean" ? (
                      <div className="flex items-center gap-1">
                        <Button
                          type="button"
                          size="sm"
                          variant={rule.value === "true" ? "default" : "outline"}
                          className="h-8 text-xs px-3"
                          onClick={() => handleRuleChange(rule.id, "value", "true")}
                        >
                          true (Да)
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant={rule.value === "false" ? "default" : "outline"}
                          className="h-8 text-xs px-3"
                          onClick={() => handleRuleChange(rule.id, "value", "false")}
                        >
                          false (Нет)
                        </Button>
                      </div>
                    ) : (
                      <Input
                        type={rule.type === "number" ? "number" : "text"}
                        value={rule.value}
                        disabled={readOnly}
                        onChange={(e) => handleRuleChange(rule.id, "value", e.target.value)}
                        placeholder="значение"
                        className="h-8 text-xs font-mono"
                      />
                    )}

                    {!readOnly && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        onClick={() => handleRemoveRule(rule.id)}
                        className="h-8 w-8 text-muted-foreground hover:text-destructive shrink-0 cursor-pointer"
                        title="Удалить правило"
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    )}
                  </div>
                </div>
              ))}

              {!readOnly && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => handleAddRule()}
                  className="h-7 text-xs gap-1.5 mt-1 cursor-pointer"
                >
                  <Plus className="size-3.5" />
                  <span>Добавить условие</span>
                </Button>
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
            rows={6}
            className="font-mono text-xs bg-muted/20 resize-y"
            placeholder='{"payment.target": "service"}'
          />
          {jsonError ? (
            <p className="text-xs text-destructive font-medium">{jsonError}</p>
          ) : (
            <p className="text-[11px] text-muted-foreground">
              Формат: JSON-объект совпадений вида <code>{"{\"path.to.field\": \"expected_value\"}"}</code>.
            </p>
          )}
        </div>
      )}
    </div>
  )
}
