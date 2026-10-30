import { useMemo, useState, useRef, useEffect } from "react"
import { Check, ChevronDown, Coins, Plus, Search, X } from "lucide-react"

import { Badge } from "@/components/shadsnui/badge"
import { Input } from "@/components/shadsnui/input"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/shadsnui/popover"
import { ScrollArea } from "@/components/shadsnui/scroll-area"
import { useInstanceCurrency, getCurrencySymbol } from "@/lib/currency"

export interface CurrencyOption {
  code: string
  name: string
  symbol?: string
}

export const KNOWN_CURRENCIES: CurrencyOption[] = [
  { code: "RUB", name: "Российский рубль", symbol: "₽" },
  { code: "USD", name: "Доллар США", symbol: "$" },
  { code: "EUR", name: "Евро", symbol: "€" },
  { code: "USDT", name: "Tether USD", symbol: "₮" },
  { code: "TON", name: "Toncoin", symbol: "TON" },
  { code: "BTC", name: "Bitcoin", symbol: "₿" },
  { code: "ETH", name: "Ethereum", symbol: "Ξ" },
  { code: "KZT", name: "Казахстанский тенге", symbol: "₸" },
  { code: "BYN", name: "Белорусский рубль", symbol: "Br" },
  { code: "UAH", name: "Украинская гривна", symbol: "₴" },
  { code: "TRY", name: "Турецкая лира", symbol: "₺" },
  { code: "CNY", name: "Китайский юань", symbol: "¥" },
  { code: "GBP", name: "Британский фунт", symbol: "£" },
  { code: "AED", name: "Дирхам ОАЭ", symbol: "AED" },
  { code: "GEL", name: "Грузинский лари", symbol: "₾" },
  { code: "AMD", name: "Армянский драм", symbol: "֏" },
  { code: "UZS", name: "Узбекский сум", symbol: "so'm" },
  { code: "JPY", name: "Японская иена", symbol: "¥" },
  { code: "CHF", name: "Швейцарский франк", symbol: "CHF" },
  { code: "PLN", name: "Польский злотый", symbol: "zł" },
  { code: "INR", name: "Индийская рупия", symbol: "₹" },
  { code: "BRL", name: "Бразильский реал", symbol: "R$" },
]

export interface CurrencySelectProps {
  value: string | null | undefined
  onChange: (code: string) => void
  currencies?: CurrencyOption[]
  allowCustom?: boolean
  placeholder?: string
  disabled?: boolean
  hasError?: boolean
  className?: string
}

export function CurrencySelect({
  value,
  onChange,
  currencies = KNOWN_CURRENCIES,
  allowCustom = true,
  placeholder = "Выберите валюту",
  disabled = false,
  hasError = false,
  className = "",
}: CurrencySelectProps) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState("")
  const searchInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (open) {
      const id = requestAnimationFrame(() => {
        searchInputRef.current?.focus({ preventScroll: true })
      })
      return () => cancelAnimationFrame(id)
    }
  }, [open])

  const { currency: instanceCurrency } = useInstanceCurrency()

  const currentCode = value ? value.trim().toUpperCase() : ""

  const selectedCurrency = useMemo(() => {
    if (!currentCode) return null
    const found = currencies.find((c) => c.code.toUpperCase() === currentCode)
    if (found) return found
    return {
      code: currentCode,
      name: "Пользовательская валюта",
      symbol: getCurrencySymbol(currentCode),
    }
  }, [currentCode, currencies])

  const filtered = useMemo(() => {
    const q = search.trim().toUpperCase()
    if (!q) return currencies
    return currencies.filter(
      (c) => c.code.includes(q) || c.name.toUpperCase().includes(q)
    )
  }, [currencies, search])

  const customMatch = useMemo(() => {
    const q = search.trim().toUpperCase().replace(/[^A-Z0-9_-]/g, "")
    if (!q || q.length < 2 || q.length > 8) return null
    const exists = currencies.some((c) => c.code.toUpperCase() === q)
    if (exists) return null
    return q
  }, [currencies, search])

  const handleSelect = (code: string) => {
    onChange(code.toUpperCase())
    setOpen(false)
    setSearch("")
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        disabled={disabled}
        className={`w-full h-8 flex items-center justify-between gap-2 px-2.5 text-xs rounded-lg border bg-card transition-all text-left outline-none select-none disabled:opacity-50 disabled:cursor-not-allowed ${
          hasError
            ? "border-destructive focus-visible:ring-1 focus-visible:ring-destructive"
            : "border-input hover:border-border focus-visible:border-primary focus-visible:ring-1 focus-visible:ring-primary/40"
        } ${className}`}
      >
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <div
            className={`size-5 rounded flex items-center justify-center font-mono font-bold text-[11px] shrink-0 ${
              selectedCurrency
                ? "bg-primary/10 text-primary border border-primary/20"
                : "bg-muted text-muted-foreground"
            }`}
          >
            {selectedCurrency?.symbol || <Coins className="size-3" />}
          </div>
          {selectedCurrency ? (
            <div className="flex items-center gap-1.5 truncate">
              <span className="font-mono font-bold text-foreground shrink-0">{selectedCurrency.code}</span>
              <span className="text-[11px] text-muted-foreground truncate">{selectedCurrency.name}</span>
              {selectedCurrency.code === instanceCurrency && (
                <Badge variant="outline" className="text-[9px] px-1 py-0 border-primary/30 text-primary shrink-0">
                  базовая
                </Badge>
              )}
            </div>
          ) : (
            <span className="text-muted-foreground truncate">{placeholder}</span>
          )}
        </div>

        <div className="flex items-center gap-1 shrink-0 text-muted-foreground">
          {selectedCurrency && !disabled && (
            <span
              role="button"
              tabIndex={0}
              onClick={(e) => {
                e.stopPropagation()
                onChange("")
              }}
              className="p-0.5 hover:text-foreground rounded cursor-pointer transition-colors"
              title="Очистить выбор"
            >
              <X className="size-3" />
            </span>
          )}
          <ChevronDown className={`size-3.5 transition-transform duration-150 ${open ? "rotate-180" : ""}`} />
        </div>
      </PopoverTrigger>

      <PopoverContent
        side="bottom"
        align="start"
        sideOffset={4}
        className="w-(--anchor-width) min-w-[280px] max-w-[420px] p-0 z-50 bg-popover border border-border shadow-md rounded-lg overflow-hidden"
      >
        {/* Поле поиска */}
        <div className="p-2 border-b border-border/60 bg-muted/20">
          <div className="relative">
            <Search className="size-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input
              ref={searchInputRef}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Поиск валюты (RUB, USD, евро...)"
              className="h-8 pl-8 text-xs bg-background uppercase font-mono placeholder:normal-case placeholder:font-sans"
            />
            {search && (
              <button
                type="button"
                onClick={() => setSearch("")}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground p-0.5"
              >
                <X className="size-3" />
              </button>
            )}
          </div>
        </div>

        {/* Список валют */}
        <ScrollArea className="max-h-60 overflow-y-auto p-1">
          {filtered.length === 0 && !customMatch && (
            <div className="py-6 text-center text-xs text-muted-foreground">
              Валюта не найдена
            </div>
          )}

          {/* Вариант добавления пользовательской валюты */}
          {allowCustom && customMatch && (
            <button
              type="button"
              onClick={() => handleSelect(customMatch)}
              className="w-full flex items-center gap-2 px-2.5 py-2 mb-1 rounded-md text-xs transition-colors cursor-pointer text-left bg-primary/5 hover:bg-primary/10 border border-primary/20 text-primary font-medium"
            >
              <Plus className="size-3.5 shrink-0" />
              <div className="flex items-center gap-1.5 truncate">
                <span>Использовать валюту:</span>
                <span className="font-mono font-bold">{customMatch}</span>
              </div>
            </button>
          )}

          <div className="space-y-0.5">
            {filtered.map((item) => {
              const isSelected = item.code.toUpperCase() === currentCode
              const isDefault = item.code.toUpperCase() === instanceCurrency
              return (
                <button
                  key={item.code}
                  type="button"
                  onClick={() => handleSelect(item.code)}
                  className={`w-full flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-md text-xs transition-colors cursor-pointer text-left ${
                    isSelected
                      ? "bg-primary/10 text-primary font-medium"
                      : "hover:bg-muted/60 text-foreground"
                  }`}
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <span className="font-mono font-bold text-[11px] size-5 rounded flex items-center justify-center bg-muted/60 text-muted-foreground shrink-0">
                      {item.symbol || item.code.slice(0, 2)}
                    </span>
                    <div className="flex flex-col min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className="font-mono font-semibold">{item.code}</span>
                        {isDefault && (
                          <Badge variant="outline" className="text-[9px] px-1 py-0 border-primary/30 text-primary font-normal">
                            базовая
                          </Badge>
                        )}
                      </div>
                      <span className="text-[10px] text-muted-foreground truncate">{item.name}</span>
                    </div>
                  </div>

                  {isSelected && <Check className="size-3.5 text-primary shrink-0" />}
                </button>
              )
            })}
          </div>
        </ScrollArea>
      </PopoverContent>
    </Popover>
  )
}
