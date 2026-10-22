import { useState, useEffect } from "react"
import { Eye, EyeOff, Plus, Trash2, Copy, Check, Code2, SlidersHorizontal, Sparkles } from "lucide-react"
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

export interface PresetItem {
  name: string
  description?: string
  keys: { key: string; label?: string; placeholder?: string; default?: string }[]
}

export const COMMON_PAYMENT_PRESETS: PresetItem[] = [
  {
    name: "ЮKassa (YooKassa)",
    description: "shop_id и secret_key",
    keys: [
      { key: "shop_id", label: "Идентификатор магазина (Shop ID)", placeholder: "123456" },
      { key: "secret_key", label: "Секретный ключ (Secret Key)", placeholder: "live_..." },
    ],
  },
  {
    name: "Robokassa",
    description: "merchant_login и пароли",
    keys: [
      { key: "merchant_login", label: "Логин мерчанта", placeholder: "my_shop" },
      { key: "password_1", label: "Пароль #1 (оплата)", placeholder: "••••••••" },
      { key: "password_2", label: "Пароль #2 (уведомления)", placeholder: "••••••••" },
    ],
  },
  {
    name: "Stripe",
    description: "API keys & Webhook secret",
    keys: [
      { key: "publishable_key", label: "Публичный ключ (pk_live_...)", placeholder: "pk_live_..." },
      { key: "secret_key", label: "Секретный ключ (sk_live_...)", placeholder: "sk_live_..." },
      { key: "webhook_secret", label: "Секрет вебхука (whsec_...)", placeholder: "whsec_..." },
    ],
  },
  {
    name: "CryptoPay / @CryptoBot",
    description: "API Token бота",
    keys: [
      { key: "api_token", label: "API Token", placeholder: "1234:AA..." },
    ],
  },
]

export const COMMON_OAUTH_PRESETS: PresetItem[] = [
  {
    name: "Google OAuth 2.0",
    description: "Client ID и Secret",
    keys: [
      { key: "client_id", label: "Client ID", placeholder: "...apps.googleusercontent.com" },
      { key: "client_secret", label: "Client Secret", placeholder: "GOCSPX-..." },
      { key: "auth_endpoint", label: "Auth URL", default: "https://accounts.google.com/o/oauth2/v2/auth" },
      { key: "token_endpoint", label: "Token URL", default: "https://oauth2.googleapis.com/token" },
      { key: "userinfo_endpoint", label: "Userinfo URL", default: "https://openidconnect.googleapis.com/v1/userinfo" },
    ],
  },
  {
    name: "GitHub OAuth",
    description: "OAuth App",
    keys: [
      { key: "client_id", label: "Client ID", placeholder: "Iv1..." },
      { key: "client_secret", label: "Client Secret", placeholder: "••••••••" },
      { key: "auth_endpoint", label: "Auth URL", default: "https://github.com/login/oauth/authorize" },
      { key: "token_endpoint", label: "Token URL", default: "https://github.com/login/oauth/access_token" },
      { key: "userinfo_endpoint", label: "Userinfo URL", default: "https://api.github.com/user" },
    ],
  },
  {
    name: "Telegram Login Widget",
    description: "Bot Token",
    keys: [
      { key: "bot_token", label: "Токен Telegram бота", placeholder: "123456789:ABC..." },
    ],
  },
]

interface KeyRow {
  id: string
  key: string
  value: string
  isSecret: boolean
  label?: string
  placeholder?: string
}

interface KeySecretEditorProps {
  value: Record<string, unknown> | string
  onChange: (parsed: Record<string, unknown>, jsonText: string) => void
  presets?: PresetItem[]
  title?: string
  description?: string
  readOnly?: boolean
}

export function KeySecretEditor({
  value,
  onChange,
  presets = [],
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

  // Инициализация при смене внешнего value
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

    const newRows: KeyRow[] = Object.entries(parsed).map(([k, v], idx) => {
      const isSec = /secret|password|token|key|hash|pass|cert/i.test(k)
      return {
        id: `row-${idx}-${k}`,
        key: k,
        value: typeof v === "object" ? JSON.stringify(v) : String(v ?? ""),
        isSecret: isSec,
      }
    })
    setRows(newRows)
  }, [value])

  const notifyChange = (updatedRows: KeyRow[]) => {
    const obj: Record<string, unknown> = {}
    for (const r of updatedRows) {
      if (!r.key.trim()) continue
      let val: unknown = r.value
      if (val === "true") val = true
      else if (val === "false") val = false
      else if (!isNaN(Number(val)) && val !== "") val = Number(val)
      obj[r.key.trim()] = val
    }
    const text = JSON.stringify(obj, null, 2)
    setJsonText(text)
    setJsonError(null)
    onChange(obj, text)
  }

  const handleRowChange = (id: string, field: "key" | "value", val: string) => {
    const updated = rows.map((r) => {
      if (r.id !== id) return r
      const next = { ...r, [field]: val }
      if (field === "key") {
        next.isSecret = /secret|password|token|key|hash|pass|cert/i.test(val)
      }
      return next
    })
    setRows(updated)
    notifyChange(updated)
  }

  const handleAddRow = () => {
    const newRow: KeyRow = {
      id: `row-${Date.now()}-${Math.random()}`,
      key: "",
      value: "",
      isSecret: false,
    }
    const updated = [...rows, newRow]
    setRows(updated)
    notifyChange(updated)
  }

  const handleRemoveRow = (id: string) => {
    const updated = rows.filter((r) => r.id !== id)
    setRows(updated)
    notifyChange(updated)
  }

  const handleApplyPreset = (preset: PresetItem) => {
    const existingMap = new Map(rows.map((r) => [r.key, r.value]))
    const newRows: KeyRow[] = preset.keys.map((k, idx) => ({
      id: `row-${Date.now()}-${idx}`,
      key: k.key,
      value: existingMap.get(k.key) || k.default || "",
      isSecret: /secret|password|token|key|hash|pass|cert/i.test(k.key),
      label: k.label,
      placeholder: k.placeholder,
    }))
    setRows(newRows)
    notifyChange(newRows)
  }

  const handleJsonChange = (text: string) => {
    setJsonText(text)
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
      const nextRows: KeyRow[] = Object.entries(parsed).map(([k, v], idx) => ({
        id: `row-${idx}-${k}`,
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
      {/* Шапка с переключателем режима и пресетами */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 pb-3">
        <div>
          <h4 className="text-sm font-semibold tracking-tight">{title}</h4>
          {description && (
            <p className="text-xs text-muted-foreground">{description}</p>
          )}
        </div>

        <div className="flex items-center gap-2">
          {presets.length > 0 && !readOnly && (
            <DropdownMenu>
              <DropdownMenuTrigger
                render={
                  <Button variant="outline" size="sm" className="h-7 text-xs gap-1.5">
                    <Sparkles className="size-3.5 text-amber-500" />
                    <span>Шаблон...</span>
                  </Button>
                }
              />
              <DropdownMenuContent align="end" className="w-56">
                {presets.map((p) => (
                  <DropdownMenuItem
                    key={p.name}
                    onClick={() => handleApplyPreset(p)}
                    className="flex flex-col items-start gap-0.5 text-xs cursor-pointer py-1.5"
                  >
                    <span className="font-medium">{p.name}</span>
                    {p.description && (
                      <span className="text-[10px] text-muted-foreground">{p.description}</span>
                    )}
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
                        placeholder={row.placeholder || "значение..."}
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
                          title="Удалить ключ"
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
