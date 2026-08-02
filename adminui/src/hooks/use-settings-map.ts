import { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"

import { api } from "@/api/api.ts"

interface SettingRow {
  key: string
  value: string | null
}

interface Page<T> {
  items: T[]
  has_more: boolean
}

/** Потолок `limit` на бэкенде (`utils/pagination.py`) — запрос сверх него
 * отвергается с 422, поэтому большие выборки берём страницами. */
const PAGE = 200

/** Все строки таблицы `settings` — секции настроек берут из этого общего
 * кэша свои ключи, вместо отдельного запроса на каждый ключ. */
export function useSettingsMap() {
  const query = useQuery({
    queryKey: ["admin-settings-all"],
    queryFn: async () => {
      const all: SettingRow[] = []
      for (let offset = 0; ; offset += PAGE) {
        const { data } = await api.get<Page<SettingRow>>("/v1/admin/settings/raw", {
          params: { limit: PAGE, offset },
        })
        all.push(...data.items)
        if (!data.has_more) break
      }
      return all
    },
    staleTime: 30_000,
  })

  const map = useMemo(() => {
    const m = new Map<string, string>()
    for (const row of query.data ?? []) m.set(row.key, row.value ?? "")
    return m
  }, [query.data])

  return { map, isLoading: query.isLoading }
}
