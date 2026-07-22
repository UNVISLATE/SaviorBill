import { useEffect, useRef, useState } from "react"

const DEFAULT_PAGE_SIZE = 30
export const PAGE_SIZE_OPTIONS = [10, 30, 50, 100] as const

/** Состояние сортировки/поиска/пагинации общего `DataTable` (см.
 * IMPLEMENTATION_PLAN.md §0.1) — держит query-параметры, совместимые с
 * backend'ом (`limit`/`offset`/`q`/`sort`, см. `utils/pagination.py`), и
 * debounce'ит поиск, чтобы не долбить API на каждое нажатие клавиши. */
export function useDataTableQuery(defaultLimit: number = DEFAULT_PAGE_SIZE) {
  const [limit, setLimit] = useState(defaultLimit)
  const [offset, setOffset] = useState(0)
  const [sort, setSort] = useState<string | null>(null)
  const [searchInput, setSearchInput] = useState("")
  const [search, setSearch] = useState("")
  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  useEffect(() => {
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      setSearch(searchInput)
      setOffset(0)
    }, 300)
    return () => clearTimeout(debounceRef.current)
  }, [searchInput])

  const toggleSort = (field: string) => {
    setOffset(0)
    setSort((prev) => {
      if (prev === field) return `-${field}`
      if (prev === `-${field}`) return null
      return field
    })
  }

  const changeLimit = (next: number) => {
    setLimit(next)
    setOffset(0)
  }

  return {
    limit,
    offset,
    sort,
    search,
    searchInput,
    setSearchInput,
    setOffset,
    toggleSort,
    changeLimit,
  }
}
