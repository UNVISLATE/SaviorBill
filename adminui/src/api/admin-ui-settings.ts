import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "./api"
import { BRANDING_UPDATED_EVENT } from "@/hooks/use-branding"

export interface MediaDialogDefaultSettings {
  gif_format: string
  video_format: string
  video_codec: string
  audio_codec: string
  scale: string
  poster_scale: string
  crf: number
  video_preset?: string
  audio_bitrate?: string
}

export interface MediaDialogSettings {
  enabled: boolean
  default: MediaDialogDefaultSettings
}

export interface AdminUiSettings {
  mediadialog: MediaDialogSettings
  [key: string]: unknown
}

interface BrandingAdminResponse {
  name: string | null
  logo_url: string | null
  favicon_url: string | null
  theme: Record<string, unknown>
  version: string
  currency: string
  settings: AdminUiSettings
}

export const ADMIN_UI_SETTINGS_KEY = ["admin-ui-settings"]

export async function fetchAdminUiSettings(): Promise<AdminUiSettings> {
  const res = await api.get<BrandingAdminResponse>("/v1/branding/admin")
  return res.data.settings
}

export async function updateAdminUiSettings(
  settings: Partial<AdminUiSettings>,
): Promise<AdminUiSettings> {
  const res = await api.put<BrandingAdminResponse>("/v1/branding/admin", {
    settings,
  })
  window.dispatchEvent(new Event(BRANDING_UPDATED_EVENT))
  return res.data.settings
}

export function useAdminUiSettings() {
  return useQuery({
    queryKey: ADMIN_UI_SETTINGS_KEY,
    queryFn: fetchAdminUiSettings,
    staleTime: 60_000,
  })
}

export function useUpdateAdminUiSettings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: updateAdminUiSettings,
    onSuccess: (data) => {
      qc.setQueryData(ADMIN_UI_SETTINGS_KEY, data)
      void qc.invalidateQueries({ queryKey: ["branding-admin"] })
    },
  })
}
