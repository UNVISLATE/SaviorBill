import { useQuery } from "@tanstack/react-query"

import { api } from "@/api/api.ts"

interface BrandingResponse {
  name: string | null
  logo_url: string | null
  favicon_url: string | null
  theme: Record<string, unknown>
}

const FALLBACK_NAME = "SaviorBill Admin"

/**
 * Брендинг admin-панели (`ui.admin.*`) — публичный, не требует авторизации
 * (см. `api/v1/branding.py`), поэтому доступен и на странице логина.
 *
 * Раньше `ui.admin.name`/`ui.admin.logo` можно было поменять через API, но
 * сама панель их нигде не читала — заголовок и логотип оставались
 * захардкоженными вне зависимости от настроек (см. PLAN.md).
 */
export function useBranding() {
  const { data } = useQuery({
    queryKey: ["branding-admin"],
    queryFn: async () => (await api.get<BrandingResponse>("/v1/branding/admin")).data,
    staleTime: 5 * 60_000,
    retry: false,
  })

  return {
    name: data?.name || FALLBACK_NAME,
    logoUrl: data?.logo_url ?? null,
    faviconUrl: data?.favicon_url ?? null,
  }
}
