import { useState, useRef, useMemo, useEffect, type KeyboardEvent } from "react"
import { Check, Plus, X } from "lucide-react"
import { Badge } from "@/components/shadsnui/badge"

export const KNOWN_CURRENCIES: Array<{ code: string; name: string }> = [
  { code: "RUB", name: "Российский рубль" },
  { code: "USD", name: "Доллар США" },
  { code: "EUR", name: "Евро" },
  { code: "USDT", name: "Tether USD" },
  { code: "TON", name: "Toncoin" },
  { code: "BTC", name: "Bitcoin" },
  { code: "ETH", name: "Ethereum" },
  { code: "CNY", name: "Китайский юань" },
  { code: "KZT", name: "Казахстанский тенге" },
  { code: "BYN", name: "Белорусский рубль" },
  { code: "GBP", name: "Британский фунт" },
  { code: "TRY", name: "Турецкая лира" },
  { code: "AED", name: "Дирхам ОАЭ" },
  { code: "GEL", name: "Грузинский лари" },
  { code: "AMD", name: "Армянский драм" },
  { code: "UZS", name: "Узбекский сум" },
  { code: "UAH", name: "Украинская гривна" },
  { code: "JPY", name: "Японская иена" },
  { code: "CHF", name: "Швейцарский франк" },
  { code: "PLN", name: "Польский злотый" },
  { code: "INR", name: "Индийская рупия" },
  { code: "BRL", name: "Бразильский реал" },
]

export interface CurrencyTagSelectProps {
  value: string[]
  onChange: (next: string[]) => void
  placeholder?: string
  disabled?: boolean
  className?: string
}

export function CurrencyTagSelect({
  value,
  onChange,
  placeholder = "Выберите или введите валюту...",
  disabled = false,
  className = "",
}: CurrencyTagSelectProps) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState("")
  const containerRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const selectedSet = useMemo(
    () => new Set(value.map((v) => v.trim().toUpperCase())),
    [value]
  )

  const filteredItems = useMemo(() => {
    const q = query.trim().toUpperCase()
    if (!q) return KNOWN_CURRENCIES
    return KNOWN_CURRENCIES.filter(
      (c) => c.code.includes(q) || c.name.toUpperCase().includes(q)
    )
  }, [query])

  const canAddCustom = useMemo(() => {
    const q = query.trim().toUpperCase()
    if (!q || q.length < 2 || q.length > 10) return false
    return !selectedSet.has(q)
  }, [query, selectedSet])

  // Закрытие при клике вне контейнера
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent | TouchEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [])

  const toggleCurrency = (code: string) => {
    const upper = code.trim().toUpperCase()
    if (selectedSet.has(upper)) {
      onChange(value.filter((v) => v.trim().toUpperCase() !== upper))
    } else {
      onChange([...value, upper])
    }
    setQuery("")
    inputRef.current?.focus()
  }

  const removeCurrency = (code: string) => {
    const upper = code.trim().toUpperCase()
    onChange(value.filter((v) => v.trim().toUpperCase() !== upper))
    inputRef.current?.focus()
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault()
      const q = query.trim().toUpperCase()
      if (q) {
        toggleCurrency(q)
      }
    } else if (e.key === "Backspace" && !query && value.length > 0) {
      removeCurrency(value[value.length - 1])
    } else if (e.key === "Escape") {
      setOpen(false)
    }
  }

  return (
    <div ref={containerRef} className="relative w-full">
      <div
        onClick={() => {
          if (!disabled) {
            setOpen(true)
            inputRef.current?.focus()
          }
        }}
        className={`flex min-h-[38px] w-full flex-wrap items-center gap-1.5 rounded-md border border-input bg-background px-3 py-1.5 text-xs shadow-2xs transition-colors focus-within:ring-1 focus-within:ring-ring ${
          disabled ? "opacity-50 cursor-not-allowed" : "cursor-text"
        } ${className}`}
      >
        {value.map((code) => (
          <Badge
            key={code}
            variant="secondary"
            className="gap-1 font-mono text-[11px] py-0.5 px-2 select-none"
          >
            <span>{code}</span>
            {!disabled && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation()
                  removeCurrency(code)
                }}
                className="rounded-full hover:bg-muted p-0.5 text-muted-foreground hover:text-foreground cursor-pointer"
              >
                <X className="size-2.5" />
              </button>
            )}
          </Badge>
        ))}

        <input
          ref={inputRef}
          type="text"
          value={query}
          disabled={disabled}
          onFocus={() => {
            if (!disabled) setOpen(true)
          }}
          onChange={(e) => {
            setQuery(e.target.value)
            setOpen(true)
          }}
          onKeyDown={handleKeyDown}
          placeholder={value.length === 0 ? placeholder : ""}
          className="flex-1 min-w-[120px] bg-transparent outline-none placeholder:text-muted-foreground text-xs"
        />
      </div>

      {open && !disabled && (
        <div className="absolute left-0 right-0 top-full mt-1.5 z-50 rounded-lg border border-border bg-popover p-1.5 text-popover-foreground shadow-md max-h-60 overflow-y-auto animate-in fade-in-0 zoom-in-95 duration-100">
          <div className="space-y-0.5">
            {canAddCustom && (
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => toggleCurrency(query)}
                className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left font-medium text-primary hover:bg-accent hover:text-accent-foreground cursor-pointer"
              >
                <Plus className="size-3.5 shrink-0" />
                <span>
                  Добавить &laquo;<strong>{query.trim().toUpperCase()}</strong>&raquo;
                </span>
              </button>
            )}

            {filteredItems.map((item) => {
              const isChecked = selectedSet.has(item.code)
              return (
                <button
                  key={item.code}
                  type="button"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => toggleCurrency(item.code)}
                  className="flex w-full items-center justify-between rounded-sm px-2 py-1.5 text-left hover:bg-accent hover:text-accent-foreground transition-colors cursor-pointer"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="font-mono font-semibold">{item.code}</span>
                    <span className="text-[11px] text-muted-foreground truncate">
                      {item.name}
                    </span>
                  </div>
                  {isChecked && <Check className="size-3.5 text-primary shrink-0" />}
                </button>
              )
            })}

            {filteredItems.length === 0 && !canAddCustom && (
              <p className="px-2 py-3 text-center text-[11px] text-muted-foreground">
                Ничего не найдено
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
