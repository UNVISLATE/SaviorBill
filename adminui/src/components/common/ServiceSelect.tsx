import { useMemo, useState, useRef, useEffect } from "react"
import { useQuery } from "@tanstack/react-query"
import { Check, ChevronDown, KeyRound, Package, Search, X } from "lucide-react"

import { api } from "@/api/api.ts"
import { Badge } from "@/components/shadsnui/badge"
import { Input } from "@/components/shadsnui/input"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/shadsnui/popover"
import { ScrollArea } from "@/components/shadsnui/scroll-area"

export interface ServiceOption {
  id?: number
  service_id?: number
  name?: string
  service_name?: string
  slug?: string
  price?: string | number
  currency?: string
  delivery?: string
  price_type?: string
  is_active?: boolean
}

interface PageResponse<T> {
  items: T[]
  total: number
}

interface ServiceSelectProps {
  services?: ServiceOption[]
  value: string | number | null
  onChange: (serviceId: string, service?: ServiceOption) => void
  placeholder?: string
  disabled?: boolean
  hasError?: boolean
  filterDelivery?: "key" | "lua"
  className?: string
}

export function ServiceSelect({
  services: externalServices,
  value,
  onChange,
  placeholder = "Выберите товар / услугу",
  disabled = false,
  hasError = false,
  filterDelivery,
  className = "",
}: ServiceSelectProps) {
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

  // Автозагрузка списка товаров, если внешний список не был передан
  const { data: fetchedServices } = useQuery({
    queryKey: ["admin-services-lookup"],
    queryFn: async () => {
      const res = (await api.get<PageResponse<ServiceOption>>("/v1/admin/services", { params: { limit: 200 } })).data
      return Array.isArray(res) ? res : res.items || []
    },
    enabled: externalServices === undefined,
    staleTime: 60_000,
  })

  const rawList = externalServices !== undefined ? externalServices : fetchedServices || []

  // Нормализация и фильтрация по типу доставки (если запрошено)
  const allServices = useMemo(() => {
    let list = Array.isArray(rawList) ? rawList : []
    if (filterDelivery) {
      list = list.filter((s) => s.delivery === filterDelivery)
    }
    return list
  }, [rawList, filterDelivery])

  const selectedId = value !== null && value !== undefined && value !== "" ? String(value) : null

  const selectedService = useMemo(() => {
    if (!selectedId) return null
    return (
      allServices.find(
        (s) => String(s.id ?? s.service_id) === selectedId
      ) || null
    )
  }, [allServices, selectedId])

  // Поиск по названию, slug, ID и валюте
  const filteredServices = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return allServices
    return allServices.filter((s) => {
      const id = String(s.id ?? s.service_id ?? "")
      const name = (s.name || s.service_name || "").toLowerCase()
      const slug = (s.slug || "").toLowerCase()
      return id.includes(q) || name.includes(q) || slug.includes(q)
    })
  }, [allServices, search])

  const displayName = selectedService
    ? (selectedService.name || selectedService.service_name || `Товар #${selectedId}`)
    : null

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
          {selectedService?.delivery === "key" ? (
            <KeyRound className="size-3.5 shrink-0 text-amber-500" />
          ) : (
            <Package className={`size-3.5 shrink-0 ${selectedService ? "text-primary" : "text-muted-foreground"}`} />
          )}
          {displayName ? (
            <div className="flex items-center gap-2 truncate">
              <span className="font-medium text-foreground truncate">{displayName}</span>
              <span className="text-[10px] text-muted-foreground font-mono">
                #{selectedService?.id ?? selectedService?.service_id}
              </span>
              {selectedService?.price !== undefined && selectedService?.currency && (
                <Badge variant="outline" className="text-[10px] font-mono px-1.5 py-0 h-4">
                  {selectedService.price} {selectedService.currency}
                </Badge>
              )}
            </div>
          ) : (
            <span className="text-muted-foreground truncate">{placeholder}</span>
          )}
        </div>

        <div className="flex items-center gap-1 shrink-0 text-muted-foreground">
          {selectedService && !disabled && (
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
        className="w-(--anchor-width) min-w-[320px] max-w-[550px] p-0 z-50 bg-popover border border-border shadow-md rounded-lg overflow-hidden"
      >
        {/* Поисковая строка */}
        <div className="p-2 border-b border-border/60 bg-muted/20">
          <div className="relative">
            <Search className="size-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input
              ref={searchInputRef}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Поиск товара по названию, slug или ID…"
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

        {/* Список товаров */}
        <ScrollArea className="max-h-72 overflow-y-auto p-1">
          {filteredServices.length === 0 ? (
            <div className="py-6 text-center text-xs text-muted-foreground">
              {search ? "Товары не найдены" : "Список товаров пуст"}
            </div>
          ) : (
            <div className="space-y-0.5">
              {filteredServices.map((service) => {
                const id = String(service.id ?? service.service_id)
                const isSelected = id === selectedId
                const name = service.name || service.service_name || `Товар #${id}`

                return (
                  <button
                    key={id}
                    type="button"
                    onClick={() => {
                      onChange(id, service)
                      setOpen(false)
                      setSearch("")
                    }}
                    className={`w-full flex items-center justify-between gap-2 px-2.5 py-2 rounded-md text-xs transition-colors cursor-pointer text-left ${
                      isSelected
                        ? "bg-primary/10 text-primary font-medium"
                        : "hover:bg-muted/60 text-foreground"
                    }`}
                  >
                    <div className="flex items-center gap-2.5 min-w-0 flex-1">
                      <div className="size-7 rounded-md bg-muted flex items-center justify-center shrink-0">
                        {service.delivery === "key" ? (
                          <KeyRound className="size-3.5 text-amber-500" />
                        ) : (
                          <Package className="size-3.5 text-primary" />
                        )}
                      </div>
                      <div className="flex flex-col min-w-0">
                        <span className="truncate font-medium">{name}</span>
                        <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
                          <span className="font-mono">#{id}</span>
                          {service.slug && <span className="font-mono truncate">· /{service.slug}</span>}
                          {service.delivery === "key" && (
                            <span className="text-amber-500 font-medium">· Ключи</span>
                          )}
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      {service.price !== undefined && service.currency && (
                        <span className="text-xs font-mono font-medium text-foreground">
                          {service.price} {service.currency}
                        </span>
                      )}
                      {isSelected && <Check className="size-4 text-primary shrink-0" />}
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
