import { useEffect } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/api/api.ts"

export const BRANDING_UPDATED_EVENT = "sb-admin:branding-updated"

interface BrandingResponse {
  name: string | null
  logo_url: string | null
  favicon_url: string | null
  theme: Record<string, unknown>
  version?: string
  currency?: string
}

const FALLBACK_NAME = "SaviorBill Admin"

export function useBranding() {
  const qc = useQueryClient()
  const { data } = useQuery({
    queryKey: ["branding-admin"],
    queryFn: async () => (await api.get<BrandingResponse>("/v1/branding/admin")).data,
    staleTime: 0,
    retry: false,
  })

  useEffect(() => {
    const onBrandingUpdated = () => {
      void qc.invalidateQueries({ queryKey: ["branding-admin"] })
      void qc.refetchQueries({ queryKey: ["branding-admin"] })
    }
    window.addEventListener(BRANDING_UPDATED_EVENT, onBrandingUpdated)
    return () => window.removeEventListener(BRANDING_UPDATED_EVENT, onBrandingUpdated)
  }, [qc])

  return {
    name: data?.name || FALLBACK_NAME,
    logoUrl: data?.logo_url ?? null,
    faviconUrl: data?.favicon_url ?? null,
    version: data?.version ?? "",
    currency: data?.currency ?? "RUB",
  }
}
