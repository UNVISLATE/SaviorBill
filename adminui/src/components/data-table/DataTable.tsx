import type { ReactNode } from "react"
import { ArrowDown, ArrowUp, ArrowUpDown, Search } from "lucide-react"

import { cn } from "@/lib/utils"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/shadsnui/table"
import { Input } from "@/components/shadsnui/input"
import { Checkbox } from "@/components/shadsnui/checkbox"
import { Button } from "@/components/shadsnui/button"
import { Spinner } from "@/components/shadsnui/spinner"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/shadsnui/select"
import { PAGE_SIZE_OPTIONS } from "@/hooks/use-data-table"

export interface DataTableColumn<T> {
  /** Имя поля для сортировки (см. allowlist на backend); опустить, если
   * колонку нельзя сортировать. */
  key?: string
  header: ReactNode
  render: (row: T) => ReactNode
  className?: string
}

export interface DataTableProps<T> {
  columns: DataTableColumn<T>[]
  data: T[]
  total: number
  isLoading?: boolean
  isError?: boolean
  getRowId: (row: T) => string | number
  onRowClick?: (row: T) => void

  sort: string | null
  onToggleSort: (field: string) => void

  searchValue: string
  onSearchChange: (q: string) => void
  searchPlaceholder?: string

  limit: number
  offset: number
  hasMore: boolean
  onLimitChange: (n: number) => void
  onOffsetChange: (n: number) => void

  selectable?: boolean
  selected?: Set<string | number>
  onSelectedChange?: (next: Set<string | number>) => void

  toolbarExtra?: ReactNode
  emptyMessage?: string
}

/** Общая таблица со серверной сортировкой/поиском/пагинацией + выбором строк
 * (см. IMPLEMENTATION_PLAN.md §0.1). Сама не хранит query-состояние — это
 * делает `useDataTableQuery`, компонент только рендерит и дёргает колбэки. */
export function DataTable<T>({
  columns,
  data,
  total,
  isLoading,
  isError,
  getRowId,
  onRowClick,
  sort,
  onToggleSort,
  searchValue,
  onSearchChange,
  searchPlaceholder = "Поиск…",
  limit,
  offset,
  hasMore,
  onLimitChange,
  onOffsetChange,
  selectable,
  selected,
  onSelectedChange,
  toolbarExtra,
  emptyMessage = "Ничего не найдено.",
}: DataTableProps<T>) {
  const allIds = data.map(getRowId)
  const allSelected = selectable && data.length > 0 && allIds.every((id) => selected?.has(id))
  const someSelected = selectable && allIds.some((id) => selected?.has(id))

  const toggleAll = () => {
    if (!onSelectedChange) return
    const next = new Set(selected)
    if (allSelected) {
      allIds.forEach((id) => next.delete(id))
    } else {
      allIds.forEach((id) => next.add(id))
    }
    onSelectedChange(next)
  }

  const toggleOne = (id: string | number) => {
    if (!onSelectedChange || !selected) return
    const next = new Set(selected)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    onSelectedChange(next)
  }

  const from = total === 0 ? 0 : offset + 1
  const to = Math.min(offset + limit, total)

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <div className="relative w-full max-w-xs">
          <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={searchValue}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder={searchPlaceholder}
            className="pl-8"
          />
        </div>
        {toolbarExtra}
      </div>

      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              {selectable && (
                <TableHead className="w-10">
                  <Checkbox
                    checked={allSelected ?? false}
                    indeterminate={!allSelected && someSelected}
                    onCheckedChange={toggleAll}
                  />
                </TableHead>
              )}
              {columns.map((col, i) => {
                const active =
                  col.key && (sort === col.key || sort === `-${col.key}`)
                const desc = sort === `-${col.key}`
                return (
                  <TableHead key={i} className={col.className}>
                    {col.key ? (
                      <button
                        type="button"
                        onClick={() => onToggleSort(col.key!)}
                        className={cn(
                          "flex items-center gap-1 hover:text-foreground",
                          active ? "text-foreground" : "text-muted-foreground"
                        )}
                      >
                        {col.header}
                        {active ? (
                          desc ? <ArrowDown className="size-3.5" /> : <ArrowUp className="size-3.5" />
                        ) : (
                          <ArrowUpDown className="size-3.5 opacity-40" />
                        )}
                      </button>
                    ) : (
                      col.header
                    )}
                  </TableHead>
                )
              })}
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={columns.length + (selectable ? 1 : 0)} className="py-8 text-center">
                  <Spinner className="mx-auto" />
                </TableCell>
              </TableRow>
            )}
            {isError && !isLoading && (
              <TableRow>
                <TableCell
                  colSpan={columns.length + (selectable ? 1 : 0)}
                  className="py-8 text-center text-sm text-destructive"
                >
                  Не удалось загрузить список.
                </TableCell>
              </TableRow>
            )}
            {!isLoading && !isError && data.length === 0 && (
              <TableRow>
                <TableCell
                  colSpan={columns.length + (selectable ? 1 : 0)}
                  className="py-8 text-center text-sm text-muted-foreground"
                >
                  {emptyMessage}
                </TableCell>
              </TableRow>
            )}
            {!isLoading &&
              !isError &&
              data.map((row) => {
                const id = getRowId(row)
                return (
                  <TableRow
                    key={id}
                    role={onRowClick ? "button" : undefined}
                    tabIndex={onRowClick ? 0 : undefined}
                    onClick={() => onRowClick?.(row)}
                    onKeyDown={(e) => {
                      if (onRowClick && (e.key === "Enter" || e.key === " ")) onRowClick(row)
                    }}
                    className={onRowClick ? "cursor-pointer" : undefined}
                    data-state={selected?.has(id) ? "selected" : undefined}
                  >
                    {selectable && (
                      <TableCell onClick={(e) => e.stopPropagation()}>
                        <Checkbox
                          checked={selected?.has(id) ?? false}
                          onCheckedChange={() => toggleOne(id)}
                        />
                      </TableCell>
                    )}
                    {columns.map((col, i) => (
                      <TableCell key={i} className={col.className}>
                        {col.render(row)}
                      </TableCell>
                    ))}
                  </TableRow>
                )
              })}
          </TableBody>
        </Table>
      </div>

      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <span>На странице:</span>
          <Select value={String(limit)} onValueChange={(v) => onLimitChange(Number(v))}>
            <SelectTrigger size="sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PAGE_SIZE_OPTIONS.map((n) => (
                <SelectItem key={n} value={String(n)}>
                  {n}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <span>
            {from}–{to} из {total}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={offset === 0}
            onClick={() => onOffsetChange(Math.max(0, offset - limit))}
          >
            Назад
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={!hasMore}
            onClick={() => onOffsetChange(offset + limit)}
          >
            Далее
          </Button>
        </div>
      </div>
    </div>
  )
}
