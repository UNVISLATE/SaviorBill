import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"

import { api, AUTH_LOGOUT_EVENT } from "@/api/api.ts"
import { hasPerm, type PermNode } from "@/api/rbac.ts"
import { clearTokens, getAccessToken, setTokens } from "@/api/tokens.ts"

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
  login: (login: string, password: string) => Promise<void>
  logout: () => void
  can: (perm: string) => boolean
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient()
  // React Query читает `enabled` только на своих собственных ре-рендерах.
  // Просто читать getAccessToken() внутри `enabled` не работает: после
  // login()/logout() ничего не заставляет AuthProvider перерендериться,
  // поэтому query оставался залипшим в старом enabled=false и /admin/me
  // никогда не запрашивался -> isAuthenticated не менялся -> не было редиректа.
  const [hasToken, setHasToken] = useState(() => !!getAccessToken())

  const meQuery = useQuery({
    queryKey: ["admin-me"],
    queryFn: async () => (await api.get<AdminMe>("/v1/admin/me")).data,
    enabled: hasToken,
    retry: false,
    staleTime: 60_000,
  })

  useEffect(() => {
    // Сработавший refresh-фейл где-то в дереве запросов -> сбросить сессию везде.
    const onLogout = () => {
      clearTokens()
      setHasToken(false)
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
      isAuthenticated: hasToken && !meQuery.isError,
      async login(login: string, password: string) {
        const res = await api.post("/v1/auth/login", { login, password })
        setTokens(res.data)
        setHasToken(true)
        await qc.invalidateQueries({ queryKey: ["admin-me"] })
      },
      logout() {
        clearTokens()
        setHasToken(false)
        qc.setQueryData(["admin-me"], undefined)
        qc.removeQueries({ queryKey: ["admin-me"] })
      },
      can(perm: string) {
        return hasPerm(meQuery.data?.perms, perm)
      },
    }),
    [meQuery.data, meQuery.isLoading, meQuery.isError, hasToken, qc],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used within AuthProvider")
  return ctx
}
