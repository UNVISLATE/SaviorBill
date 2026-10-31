import { useMemo, useState, type ReactNode } from "react"
import { useQuery } from "@tanstack/react-query"
import { ChevronRight, Minus, Search, X } from "lucide-react"

import { api } from "@/api/api.ts"
import { Button } from "@/components/shadsnui/button"
import { Checkbox } from "@/components/shadsnui/checkbox"
import { Input } from "@/components/shadsnui/input"

export interface PermTree {
  [key: string]: PermTree | boolean
}

export interface PermsCatalog {
  flat: string[]
  tree: PermTree
}

export function treePaths(tree: PermTree, prefix = ""): string[] {
  return Object.entries(tree).flatMap(([key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key
    if (value === true) return [path]
    if (typeof value === "object" && value !== null) {
      const keys = Object.keys(value)
      return keys.length === 0 ? [path] : treePaths(value as PermTree, path)
    }
    return [path]
  })
}

export function buildPermsTree(paths: string[]): Record<string, unknown> {
  const tree: Record<string, unknown> = {}
  for (const path of paths) {
    const segs = path.split(".")
    let node = tree
    for (let i = 0; i < segs.length - 1; i++) {
      const seg = segs[i]
      if (typeof node[seg] !== "object" || node[seg] === null) node[seg] = {}
      node = node[seg] as Record<string, unknown>
    }
    node[segs[segs.length - 1]] = true
  }
  return tree
}

interface PermsPickerProps {
  selected: Set<string>
  onChange: (next: Set<string>) => void
  maxHeight?: string
  catalog?: PermsCatalog
}

export function PermsPicker({
  selected,
  onChange,
  maxHeight = "max-h-[350px]",
  catalog: propCatalog,
}: PermsPickerProps) {
  const [filter, setFilter] = useState("")
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set())

  const { data: fetchedCatalog } = useQuery({
    queryKey: ["admin-perms"],
    queryFn: async () => (await api.get<PermsCatalog>("/v1/admin/perms")).data,
    enabled: !propCatalog,
  })

  const catalog = propCatalog || fetchedCatalog
  const flatPerms = catalog?.flat ?? []
  const permissionTree = (catalog?.tree ?? {}) as PermTree

  const filteredFlat = useMemo(() => {
    if (!filter.trim()) return flatPerms
    const q = filter.trim().toLowerCase()
    return flatPerms.filter((p) => p.toLowerCase().includes(q))
  }, [flatPerms, filter])

  function togglePermission(path: string, enabled: boolean) {
    const descendants = flatPerms.filter(
      (permission) => permission === path || permission.startsWith(`${path}.`),
    )
    const next = new Set(selected)
    descendants.forEach((permission) => {
      if (enabled) next.add(permission)
      else next.delete(permission)
    })
    onChange(next)
  }

  function togglePermissionGroup(path: string) {
    setCollapsedGroups((prev) => {
      const next = new Set(prev)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      return next
    })
  }

  function selectAll() {
    onChange(new Set(flatPerms))
  }

  function clearAll() {
    onChange(new Set())
  }

  function renderTree(tree: PermTree, prefix = "", depth = 0): ReactNode[] {
    return Object.entries(tree).flatMap(([key, value]) => {
      const path = prefix ? `${prefix}.${key}` : key
      const descendants = treePaths({ [key]: value }, prefix)
      const selectedDescendants = descendants.filter((item) => selected.has(item))
      const isLeaf =
        value === true ||
        (typeof value === "object" && value !== null && Object.keys(value).length === 0)
      const isExpanded =
        depth === 0 ? !collapsedGroups.has(path) : collapsedGroups.has(path)
      const isCollapsed = !isExpanded
      const isPartiallySelected =
        selectedDescendants.length > 0 && selectedDescendants.length < descendants.length

      const row = (
        <div
          key={path}
          className={`flex min-h-8 items-center gap-1.5 rounded-md px-1.5 py-0.5 text-sm transition-colors hover:bg-muted/60 ${
            !isLeaf ? "bg-muted/20 font-medium" : ""
          }`}
        >
          {!isLeaf ? (
            <button
              type="button"
              className="flex size-6 shrink-0 items-center justify-center rounded hover:bg-muted"
              aria-label={isCollapsed ? `Развернуть ${key}` : `Свернуть ${key}`}
              onClick={() => togglePermissionGroup(path)}
            >
              <ChevronRight
                className={`size-4 transition-transform ${isCollapsed ? "" : "rotate-90"}`}
              />
            </button>
          ) : (
            <span className="size-6 shrink-0" />
          )}
          <Checkbox
            checked={
              selectedDescendants.length === descendants.length && descendants.length > 0
            }
            onCheckedChange={(v) => togglePermission(path, !!v)}
            aria-label={`Выбрать ${path}`}
          />
          <span
            className={`cursor-pointer select-none ${
              isLeaf ? "font-mono text-xs text-foreground/90" : "font-semibold text-xs"
            }`}
            onClick={() => togglePermission(path, selectedDescendants.length !== descendants.length)}
          >
            {key}
          </span>
          {!isLeaf && (
            <span className="text-[10px] text-muted-foreground ml-1">
              ({selectedDescendants.length}/{descendants.length})
            </span>
          )}
          {!isLeaf && isPartiallySelected && (
            <Minus className="ml-auto mr-1 size-3.5 text-primary" aria-label="Выбрано частично" />
          )}
        </div>
      )

      if (isLeaf || isCollapsed) return [row]
      return [
        row,
        <div key={`${path}-children`} className="ml-3 border-l border-border/70 pl-2">
          {renderTree(value as PermTree, path, depth + 1)}
        </div>,
      ]
    })
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground" />
          <Input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Быстрый поиск права (например: apptokens, orders, services)..."
            className="h-8 pl-8 pr-8 text-xs"
          />
          {filter && (
            <button
              type="button"
              onClick={() => setFilter("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              <X className="size-3.5" />
            </button>
          )}
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-8 text-xs px-2.5"
            onClick={selectAll}
          >
            Выбрать все ({flatPerms.length})
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="h-8 text-xs px-2.5 text-muted-foreground hover:text-destructive"
            onClick={clearAll}
            disabled={selected.size === 0}
          >
            Снять все
          </Button>
        </div>
      </div>

      <div
        className={`${maxHeight} overflow-y-auto rounded-lg border border-border/60 p-2 space-y-0.5 bg-background/50 shadow-inner`}
      >
        {filter.trim() ? (
          filteredFlat.length > 0 ? (
            filteredFlat.map((p) => (
              <label
                key={p}
                className="flex items-center gap-2 rounded px-2 py-1 text-sm hover:bg-muted/50 cursor-pointer"
              >
                <Checkbox
                  checked={selected.has(p)}
                  onCheckedChange={(v) => togglePermission(p, !!v)}
                />
                <span className="font-mono text-xs">{p}</span>
              </label>
            ))
          ) : (
            <p className="p-4 text-center text-xs text-muted-foreground">
              Ничего не найдено по запросу «{filter}»
            </p>
          )
        ) : (
          renderTree(permissionTree)
        )}
      </div>
    </div>
  )
}
