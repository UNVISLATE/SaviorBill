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
  login: (login: string, password: string, totp?: string) => Promise<void>
  logout: () => void
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

  useEffect(() => {
    // Сработавший refresh-фейл где-то в дереве запросов -> сбросить сессию везде.
    const onLogout = () => {
      qc.setQueryData(["admin-me"], undefined)
      qc.removeQueries({ queryKey: ["admin-me"] })
    }
    window.addEventListener(AUTH_LOGOUT_EVENT, onLogout)
    return () => window.removeEventListener(AUTH_LOGOUT_EVENT, onLogout)
  }, [qc])

  const value = useMemo<AuthContextValue>(
    () => ({
      me: meQuery.data,
      isLoading: meQuery.isLoading,
      isAuthenticated: !!meQuery.data,
      async login(login: string, password: string, totp?: string) {
        try {
          await api.post("/v1/auth/login", { login, password, totp })
        } catch (err) {
          const detail = getErrorDetail(err)
          if (detail === "totp required") throw new Error("TOTP_REQUIRED")
          if (detail === "invalid totp") throw new Error("TOTP_INVALID")
          throw new Error("LOGIN_FAILED")
        }
        try {
          // Гейт на вход в админку — на бэкенде (role.admin_login_allowed),
          // здесь только сразу подхватываем результат; если роль не
          // допущена — снимаем cookie через /auth/logout, чтобы не оставлять
          // "полу-залогиненную" сессию.
          const me = await qc.fetchQuery({
            queryKey: ["admin-me"],
            queryFn: async () => (await api.get<AdminMe>("/v1/admin/me")).data,
          })
          qc.setQueryData(["admin-me"], me)
        } catch (err) {
          await api.post("/v1/auth/logout").catch(() => undefined)
          qc.removeQueries({ queryKey: ["admin-me"] })
          const status = getErrorStatus(err)
          throw new Error(
            status === 403 ? "ACCESS_DENIED" : "LOGIN_FAILED",
          )
        }
      },
      logout() {
        api.post("/v1/auth/logout").catch(() => undefined)
        qc.setQueryData(["admin-me"], undefined)
        qc.removeQueries({ queryKey: ["admin-me"] })
      },
      can(perm: string) {
        return hasPerm(meQuery.data?.perms, perm)
      },
    }),
    [meQuery.data, meQuery.isLoading, qc],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used within AuthProvider")
  return ctx
}
