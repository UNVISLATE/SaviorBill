import { createContext, useContext, useEffect, useMemo, type ReactNode } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"

import { api, AUTH_LOGOUT_EVENT } from "@/api/api.ts"
import { hasPerm, type PermNode } from "@/api/rbac.ts"
import { getErrorDetail, getErrorStatus } from "@/lib/api-error.ts"

export interface AdminMe {
  id: number
  login: string
  email: string | null
  role: string | null
  perms: PermNode
}

interface AuthContextValue {
  me: AdminMe | undefined
  isLoading: boolean
  isAuthenticated: boolean
  isBackendUnavailable: boolean
  error: unknown
  refetchMe: () => void
  login: (login: string, password: string, totp?: string) => Promise<void>
  logout: () => Promise<void>
  can: (perm: string) => boolean
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient()
  // Токены — httpOnly cookies (JS их не видит вовсе, см. api/api.ts), поэтому
  // единственный способ узнать "залогинен ли клиент" — спросить сервер;
  // `enabled: true` всегда, состояние сессии полностью определяется этим
  // запросом (`isAuthenticated = !!me`), а не отдельным локальным флагом.
  const meQuery = useQuery({
    queryKey: ["admin-me"],
    queryFn: async () => (await api.get<AdminMe>("/v1/admin/me")).data,
    retry: false,
    staleTime: 60_000,
  })

  const isBackendUnavailable = useMemo(() => {
    if (!meQuery.isError) return false
    const err = meQuery.error as { response?: { status?: number }; code?: string } | undefined
    const status = err?.response?.status
    if (status && status < 500) return false
    return err?.code === "ERR_NETWORK" || (status !== undefined && status >= 500)
  }, [meQuery.isError, meQuery.error])

  useEffect(() => {
    // Сработавший refresh-фейл где-то в дереве запросов -> сбросить сессию и перенаправить на логин
    const onLogout = () => {
      qc.setQueryData(["admin-me"], null)
      if (!window.location.pathname.startsWith("/login")) {
        const fromPath = encodeURIComponent(window.location.pathname + window.location.search)
        window.location.href = `/login?from=${fromPath}`
      }
    }
    window.addEventListener(AUTH_LOGOUT_EVENT, onLogout)
    return () => window.removeEventListener(AUTH_LOGOUT_EVENT, onLogout)
  }, [qc])

  const value = useMemo<AuthContextValue>(
    () => ({
      me: meQuery.data,
      isLoading: meQuery.isLoading,
      isAuthenticated: Boolean(meQuery.data),
      isBackendUnavailable,
      error: meQuery.error,
      refetchMe: () => void meQuery.refetch(),
      async login(login: string, password: string, totp?: string) {
        try {
          await api.post("/v1/auth/login", { login, password, totp })
        } catch (err) {
          const detail = getErrorDetail(err)
          if (detail === "totp required") throw new Error("TOTP_REQUIRED", { cause: err })
          if (detail === "invalid totp") throw new Error("TOTP_INVALID", { cause: err })
          throw new Error("LOGIN_FAILED", { cause: err })
        }
        try {
          // Гейт на вход в админку — на бэкенде (role.admin_login_allowed),
          // запрашиваем актуальный профиль администратора
          const res = await api.get<AdminMe>("/v1/admin/me")
          qc.setQueryData(["admin-me"], res.data)
        } catch (err) {
          await api.post("/v1/auth/logout").catch(() => undefined)
          qc.setQueryData(["admin-me"], null)
          const status = getErrorStatus(err)
          throw new Error(
            status === 403 ? "ACCESS_DENIED" : "LOGIN_FAILED",
            { cause: err },
          )
        }
      },
      async logout() {
        try {
          await api.post("/v1/auth/logout")
        } catch {
          // Игнорируем сетевые сбои при логауте
        }
        qc.clear()
        window.location.href = "/login"
      },
      can(perm: string) {
        return hasPerm(meQuery.data?.perms, perm)
      },
    }),
    [meQuery, isBackendUnavailable, qc],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used within AuthProvider")
  return ctx
}
