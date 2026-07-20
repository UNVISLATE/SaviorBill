import { useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"

/** Полный профиль текущего аккаунта (`/v1/user/me`) — богаче, чем AdminMe
 * (id/login/role/perms) из `useAuth()`: баланс, аватар, реферальный код,
 * кто пригласил, привязанные OAuth. Отдельный запрос, отдельный ключ. */
export interface UserProfile {
  id: number
  login: string
  email: string | null
  is_active: boolean
  is_verified: boolean
  role: string | null
  ref_code: string | null
  created_at: string
  last_login: string | null
  balance: string
  bonus_balance: string
  avatar_media_id: number | null
  avatar_url: string | null
  referred_by_login: string | null
  oauth_providers: string[]
}

export function useUserProfile() {
  return useQuery({
    queryKey: ["user-profile"],
    queryFn: async () => (await api.get<UserProfile>("/v1/user/me")).data,
    staleTime: 15_000,
  })
}

export function useInvalidateUserProfile() {
  const qc = useQueryClient()
  return () => qc.invalidateQueries({ queryKey: ["user-profile"] })
}
