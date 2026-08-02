import { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"

import { api } from "@/api/api.ts"

interface SettingRow {
  key: string
  value: string | null
}

interface Page<T> {
  items: T[]
}

/** Все строки таблицы `settings` одним запросом — секции настроек берут из
 * этого общего кэша свои ключи, вместо N отдельных запросов по одному ключу. */
export function useSettingsMap() {
  const query = useQuery({
    queryKey: ["admin-settings-all"],
    queryFn: async () =>
      (await api.get<Page<SettingRow>>("/v1/admin/settings/raw", { params: { limit: 500 } }))
        .data.items,
  })
  const map = useMemo(() => {
    const m = new Map<string, string>()
    for (const row of query.data ?? []) m.set(row.key, row.value ?? "")
    return m
  }, [query.data])
  return { map, isLoading: query.isLoading }
}
