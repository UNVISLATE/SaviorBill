import { useMemo, useState, useRef, useEffect } from "react"
import { useQuery } from "@tanstack/react-query"
import { Check, ChevronDown, Folder, FolderOpen, Search, X } from "lucide-react"

import { api } from "@/api/api"
import { Input } from "@/components/shadsnui/input"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/shadsnui/popover"
import { ScrollArea } from "@/components/shadsnui/scroll-area"

export interface CatalogItem {
  id: number
  name: string
  slug?: string
  parent_id: number | null
}

export interface CatalogTreeSelectProps {
  value: number | string | null | undefined
  onChange: (catalogId: number | null, catalog?: CatalogItem | null) => void
  catalogs?: CatalogItem[]
  excludeId?: number | null
  allowRoot?: boolean
  rootLabel?: string
  placeholder?: string
  disabled?: boolean
  hasError?: boolean
  className?: string
}

interface FlattenedCatalogNode {
  id: number
  name: string
  slug?: string
  parent_id: number | null
  depth: number
  path: string
}

export function CatalogTreeSelect({
  value,
  onChange,
  catalogs: propCatalogs,
  excludeId,
  allowRoot = true,
  rootLabel = "— Без каталога (корневой уровень) —",
  placeholder = "Без каталога (корневой уровень)",
  disabled = false,
  hasError = false,
  className = "",
}: CatalogTreeSelectProps) {
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

  // Автозагрузка каталогов, если не переданы извне
  const { data: fetchedCatalogs, isLoading } = useQuery({
    queryKey: ["admin-catalogs"],
    queryFn: async () => {
      const res = await api.get<CatalogItem[]>("/v1/admin/catalogs")
      return Array.isArray(res.data) ? res.data : []
    },
    enabled: propCatalogs === undefined,
    staleTime: 60_000,
  })

  const rawCatalogs = propCatalogs !== undefined ? propCatalogs : fetchedCatalogs || []

  // Вычисляем список ID, которые нужно исключить (сам excludeId и все его потомки, чтобы избежать циклов)
  const excludedIds = useMemo(() => {
    if (!excludeId) return new Set<number>()
    const set = new Set<number>([excludeId])
    let added = true
    while (added) {
      added = false
      for (const c of rawCatalogs) {
        if (c.parent_id !== null && set.has(c.parent_id) && !set.has(c.id)) {
          set.add(c.id)
          added = true
        }
      }
    }
    return set
  }, [rawCatalogs, excludeId])

  const catalogs = useMemo(() => {
    if (excludedIds.size === 0) return rawCatalogs
    return rawCatalogs.filter((c) => !excludedIds.has(c.id))
  }, [rawCatalogs, excludedIds])

  // Построение плоского дерева с расчетом глубины и путей
  const { flattenedTree, idToPathMap, byIdMap } = useMemo(() => {
    const byParent: Record<string, CatalogItem[]> = {}
    const byId: Record<number, CatalogItem> = {}

    for (const c of catalogs) {
      byId[c.id] = c
      const pKey = c.parent_id === null ? "root" : String(c.parent_id)
      if (!byParent[pKey]) byParent[pKey] = []
      byParent[pKey].push(c)
    }

    const flat: FlattenedCatalogNode[] = []
    const paths: Record<number, string> = {}

    function traverse(parentId: number | null, depth: number, prefix: string) {
      const pKey = parentId === null ? "root" : String(parentId)
      const children = byParent[pKey] || []
      children.sort((a, b) => a.name.localeCompare(b.name, "ru"))

      for (const child of children) {
        const fullPath = prefix ? `${prefix} / ${child.name}` : child.name
        paths[child.id] = fullPath
        flat.push({
          id: child.id,
          name: child.name,
          slug: child.slug,
          parent_id: child.parent_id,
          depth,
          path: fullPath,
        })
        traverse(child.id, depth + 1, fullPath)
      }
    }

    traverse(null, 0, "")
    return { flattenedTree: flat, idToPathMap: paths, byIdMap: byId }
  }, [catalogs])

  // Фильтрация по поиску
  const filteredNodes = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return flattenedTree
    return flattenedTree.filter(
      (node) =>
        node.name.toLowerCase().includes(q) ||
        node.path.toLowerCase().includes(q) ||
        (node.slug && node.slug.toLowerCase().includes(q)) ||
        String(node.id) === q
    )
  }, [flattenedTree, search])

  const numericValue =
    value !== null && value !== undefined && value !== "" ? Number(value) : null

  const selectedPath = numericValue !== null ? idToPathMap[numericValue] || null : null

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
          {numericValue !== null ? (
            <FolderOpen className="size-3.5 text-primary shrink-0" />
          ) : (
            <Folder className="size-3.5 text-muted-foreground shrink-0" />
          )}
          <span
            className={
              numericValue !== null
                ? "text-foreground font-medium truncate"
                : "text-muted-foreground truncate"
            }
          >
            {selectedPath || placeholder}
          </span>
        </div>

        <div className="flex items-center gap-1 shrink-0 text-muted-foreground">
          {numericValue !== null && !disabled && allowRoot && (
            <span
              role="button"
              tabIndex={0}
              onClick={(e) => {
                e.stopPropagation()
                onChange(null, null)
              }}
              className="p-0.5 hover:text-foreground rounded cursor-pointer transition-colors"
              title="Очистить каталог"
            >
              <X className="size-3" />
            </span>
          )}
          <ChevronDown
            className={`size-3.5 transition-transform duration-150 ${open ? "rotate-180" : ""}`}
          />
        </div>
      </PopoverTrigger>

      <PopoverContent
        side="bottom"
        align="start"
        sideOffset={4}
        className="w-(--anchor-width) min-w-[320px] max-w-[480px] p-0 z-50 bg-popover border border-border shadow-md rounded-lg overflow-hidden"
      >
        {/* Поисковая строка */}
        <div className="p-2 border-b border-border/60 bg-muted/20">
          <div className="relative">
            <Search className="size-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input
              ref={searchInputRef}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Поиск по названию каталога или ID…"
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

        {/* Древовидный список */}
        <ScrollArea className="max-h-64 overflow-y-auto p-1">
          {isLoading && (
            <div className="py-6 text-center text-xs text-muted-foreground">
              Загрузка каталогов…
            </div>
          )}

          {/* Пункт: Без каталога (корневой уровень) */}
          {allowRoot && !search.trim() && (
            <button
              type="button"
              onClick={() => {
                onChange(null, null)
                setOpen(false)
              }}
              className={`w-full flex items-center justify-between px-2.5 py-1.5 mb-1 rounded-md text-xs cursor-pointer transition-colors text-left ${
                numericValue === null
                  ? "bg-primary/10 text-primary font-medium"
                  : "hover:bg-muted/60 text-muted-foreground"
              }`}
            >
              <div className="flex items-center gap-2">
                <Folder className="size-3.5 shrink-0" />
                <span>{rootLabel}</span>
              </div>
              {numericValue === null && <Check className="size-3.5 text-primary shrink-0" />}
            </button>
          )}

          {!isLoading && filteredNodes.length === 0 ? (
            <div className="py-6 text-center text-xs text-muted-foreground">
              Каталоги не найдены
            </div>
          ) : (
            <div className="space-y-0.5">
              {filteredNodes.map((node) => {
                const isSelected = numericValue === node.id
                const indent = search.trim() ? 0 : node.depth * 14

                return (
                  <button
                    key={node.id}
                    type="button"
                    onClick={() => {
                      onChange(node.id, byIdMap[node.id] || null)
                      setOpen(false)
                      setSearch("")
                    }}
                    style={{ paddingLeft: `${indent + 10}px` }}
                    className={`w-full flex items-center justify-between pr-2.5 py-1.5 rounded-md text-xs cursor-pointer transition-colors text-left ${
                      isSelected
                        ? "bg-primary/10 text-primary font-medium"
                        : "hover:bg-muted/60 text-foreground"
                    }`}
                  >
                    <div className="flex items-center gap-2 min-w-0 flex-1">
                      {node.depth > 0 && !search.trim() && (
                        <span className="text-muted-foreground/40 font-mono text-[10px]">└</span>
                      )}
                      <Folder
                        className={`size-3.5 shrink-0 ${
                          isSelected ? "text-primary" : "text-muted-foreground/70"
                        }`}
                      />
                      <span className="truncate">
                        {search.trim() ? node.path : node.name}
                      </span>
                    </div>

                    <div className="flex items-center gap-1.5 shrink-0 ml-2">
                      <span className="text-[10px] font-mono text-muted-foreground">
                        #{node.id}
                      </span>
                      {isSelected && <Check className="size-3.5 text-primary shrink-0" />}
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
