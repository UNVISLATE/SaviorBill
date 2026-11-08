import { useMemo, useState, useRef, useEffect } from "react"
import { useQuery } from "@tanstack/react-query"
import {
  Check,
  ChevronDown,
  Code2,
  CreditCard,
  FileCode2,
  KeyRound,
  Package,
  Search,
  X,
  Zap,
} from "lucide-react"

import { api } from "@/api/api"
import { Badge } from "@/components/shadsnui/badge"
import { Input } from "@/components/shadsnui/input"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/shadsnui/popover"
import { ScrollArea } from "@/components/shadsnui/scroll-area"

export type LuaScriptKind = "service" | "payment" | "auth" | "trigger" | "generic" | string

export interface LuaScriptOption {
  id: number
  name?: string | null
  slug?: string | null
  kind?: LuaScriptKind | null
  is_active?: boolean
  filename?: string | null
  settings?: Record<string, unknown>
}

export interface LuaScriptSelectProps {
  value: string | number | null | undefined
  onChange: (id: string, script?: LuaScriptOption | null) => void
  scripts?: LuaScriptOption[]
  kind?: LuaScriptKind | LuaScriptKind[]
  placeholder?: string
  disabled?: boolean
  hasError?: boolean
  className?: string
  showKindBadge?: boolean
  valueField?: "id" | "slug"
}

export function getScriptKindBadge(kind?: string | null) {
  const k = kind?.toLowerCase() || "generic"
  switch (k) {
    case "payment":
      return {
        label: "Платёж",
        icon: CreditCard,
        className: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20",
      }
    case "service":
      return {
        label: "Услуга",
        icon: Package,
        className: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20",
      }
    case "auth":
      return {
        label: "Авторизация",
        icon: KeyRound,
        className: "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20",
      }
    case "trigger":
      return {
        label: "Триггер",
        icon: Zap,
        className: "bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/20",
      }
    default:
      return {
        label: "Скрипт",
        icon: FileCode2,
        className: "bg-muted text-muted-foreground border-border",
      }
  }
}

export function LuaScriptSelect({
  value,
  onChange,
  scripts: propScripts,
  kind,
  placeholder = "Выберите скрипт автоматизации",
  disabled = false,
  hasError = false,
  className = "",
  showKindBadge = true,
  valueField = "id",
}: LuaScriptSelectProps) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState("")
  const searchInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (open) {
      // Фокусируемся на строке поиска без скролла окна
      const id = requestAnimationFrame(() => {
        searchInputRef.current?.focus({ preventScroll: true })
      })
      return () => cancelAnimationFrame(id)
    }
  }, [open])

  // Автозагрузка скриптов, если prop не передан
  const { data: fetchedScripts, isLoading } = useQuery({
    queryKey: ["admin-lua-scripts"],
    queryFn: async () => {
      const res = await api.get<LuaScriptOption[]>("/v1/admin/lua")
      return Array.isArray(res.data) ? res.data : []
    },
    enabled: propScripts === undefined,
    staleTime: 60_000,
  })

  const availableScripts = propScripts !== undefined ? propScripts : fetchedScripts || []

  // Фильтрация по переданному типу kind (например, только payment или только service)
  const kindFilteredScripts = useMemo(() => {
    if (!kind) return availableScripts
    const allowedKinds = Array.isArray(kind) ? kind.map((k) => k.toLowerCase()) : [kind.toLowerCase()]
    return availableScripts.filter((s) => s.kind && allowedKinds.includes(s.kind.toLowerCase()))
  }, [availableScripts, kind])

  const selectedValue = value !== null && value !== undefined && value !== "" ? String(value) : null

  const selectedScript = useMemo(() => {
    if (!selectedValue) return null
    if (valueField === "slug") {
      return availableScripts.find((s) => s.slug === selectedValue) || null
    }
    return (
      availableScripts.find((s) => String(s.id) === selectedValue || (s.slug && s.slug === selectedValue)) || null
    )
  }, [availableScripts, selectedValue, valueField])

  // Фильтрация по поисковой строке
  const searchFilteredScripts = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return kindFilteredScripts
    return kindFilteredScripts.filter((s) => {
      const nameMatch = s.name?.toLowerCase().includes(q)
      const slugMatch = s.slug?.toLowerCase().includes(q)
      const idMatch = String(s.id).includes(q)
      const kindMatch = s.kind?.toLowerCase().includes(q)
      return Boolean(nameMatch || slugMatch || idMatch || kindMatch)
    })
  }, [kindFilteredScripts, search])

  const displayName = selectedScript
    ? (selectedScript.name?.trim() || selectedScript.slug || `Скрипт #${selectedScript.id}`)
    : null

  const selectedBadge = selectedScript ? getScriptKindBadge(selectedScript.kind) : null
  const SelectedIcon = selectedBadge?.icon || Code2

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
          <SelectedIcon
            className={`size-3.5 shrink-0 ${selectedScript ? "text-primary" : "text-muted-foreground"}`}
          />
          {displayName ? (
            <div className="flex items-center gap-1.5 truncate">
              <span className="font-medium text-foreground truncate">{displayName}</span>
              <span className="text-[10px] text-muted-foreground font-mono">#{selectedScript?.id}</span>
              {showKindBadge && selectedBadge && (
                <Badge
                  variant="outline"
                  className={`text-[9px] px-1 py-0 font-normal shrink-0 ${selectedBadge.className}`}
                >
                  {selectedBadge.label}
                </Badge>
              )}
            </div>
          ) : (
            <span className="text-muted-foreground truncate">{placeholder}</span>
          )}
        </div>

        <div className="flex items-center gap-1 shrink-0 text-muted-foreground">
          {selectedScript && !disabled && (
            <span
              role="button"
              tabIndex={0}
              onClick={(e) => {
                e.stopPropagation()
                onChange("", null)
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
        className="w-(--anchor-width) min-w-[320px] max-w-[500px] p-0 z-50 bg-popover border border-border shadow-md rounded-lg overflow-hidden"
      >
        {/* Поисковая строка */}
        <div className="p-2 border-b border-border/60 bg-muted/20">
          <div className="relative">
            <Search className="size-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input
              ref={searchInputRef}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Поиск скрипта по названию, slug, ID или типу…"
              className="h-8 pl-8 text-xs bg-background"
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

        {/* Список скриптов */}
        <ScrollArea className="max-h-64 overflow-y-auto p-1">
          {isLoading && (
            <div className="py-6 text-center text-xs text-muted-foreground">
              Загрузка скриптов…
            </div>
          )}

          {!isLoading && searchFilteredScripts.length === 0 && (
            <div className="py-6 text-center text-xs text-muted-foreground">
              {search
                ? "Скрипты не найдены"
                : kind
                ? `Нет доступных скриптов с типом «${Array.isArray(kind) ? kind.join(", ") : kind}»`
                : "Список скриптов пуст"}
            </div>
          )}

          {!isLoading && (
            <div className="space-y-0.5">
              {searchFilteredScripts.map((script) => {
                const scriptVal = valueField === "slug" ? (script.slug || "") : String(script.id)
                const isSelected = valueField === "slug"
                  ? script.slug === selectedValue
                  : (String(script.id) === selectedValue || script.slug === selectedValue)
                const title = script.name?.trim() || script.slug || `Скрипт #${script.id}`
                const badge = getScriptKindBadge(script.kind)
                const ItemIcon = badge.icon

                return (
                  <button
                    key={script.id}
                    type="button"
                    onClick={() => {
                      onChange(scriptVal, script)
                      setOpen(false)
                      setSearch("")
                    }}
                    className={`w-full flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-md text-xs transition-colors cursor-pointer text-left ${
                      isSelected
                        ? "bg-primary/10 text-primary font-medium"
                        : "hover:bg-muted/60 text-foreground"
                    }`}
                  >
                    <div className="flex items-center gap-2 min-w-0 flex-1">
                      <ItemIcon
                        className={`size-3.5 shrink-0 ${isSelected ? "text-primary" : "text-muted-foreground"}`}
                      />
                      <div className="flex flex-col min-w-0">
                        <div className="flex items-center gap-1.5 truncate">
                          <span className="truncate">{title}</span>
                          <span className="text-[10px] text-muted-foreground font-mono shrink-0">
                            #{script.id}
                          </span>
                        </div>
                        {script.slug && script.slug !== title && (
                          <span className="text-[10px] text-muted-foreground font-mono truncate">
                            {script.slug}
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-1.5 shrink-0">
                      <Badge
                        variant="outline"
                        className={`text-[9px] px-1 py-0 font-normal shrink-0 ${badge.className}`}
                      >
                        {badge.label}
                      </Badge>
                      {script.is_active === false && (
                        <span className="text-[9px] text-muted-foreground italic">
                          (неактивен)
                        </span>
                      )}
                      {isSelected && <Check className="size-3.5 text-primary shrink-0 ml-1" />}
                    </div>
                  </button>
                )
              })}
            </div>
          )}
        </ScrollArea>
      </PopoverContent>
    </Popover>
  )
}
