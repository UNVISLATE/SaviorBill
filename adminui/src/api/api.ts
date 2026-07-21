import axios, { type AxiosError, type InternalAxiosRequestConfig } from "axios"

import { clearTokens, getAccessToken, getRefreshToken, setTokens } from "@/api/tokens.ts"

/** Событие: сессия истекла (refresh не удался) — слушает AuthProvider. */
export const AUTH_LOGOUT_EVENT = "sb-admin:logout"

export const api = axios.create({
  // Каждый роутер (admin/auth/user/...) уже несёт полный "/api/v1/..." префикс
  // сам (см. src/api/v1/admin/__init__.py) — здесь достаточно "/api".
  baseURL: "/api",
})

api.interceptors.request.use((config) => {
  const token = getAccessToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Однополётный refresh — параллельные 401 не должны насоздать N параллельных
// /auth/refresh (backend ротирует refresh_token, второй вызов инвалидировал бы
// токен, который первый вызов ещё не успел сохранить).
let refreshPromise: Promise<string | null> | null = null

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = getRefreshToken()
  if (!refreshToken) return null
  if (!refreshPromise) {
    refreshPromise = axios
      .post("/api/v1/auth/refresh", { refresh_token: refreshToken })
      .then((res) => {
        setTokens(res.data)
        return res.data.access_token as string
      })
      .catch(() => {
        clearTokens()
        return null
      })
      .finally(() => {
        refreshPromise = null
      })
  }
  return refreshPromise
}

api.interceptors.response.use(
  (res) => res,
  async (error: AxiosError) => {
    const cfg = error.config as (InternalAxiosRequestConfig & { _retried?: boolean }) | undefined
    if (error.response?.status === 401 && cfg && !cfg._retried) {
      cfg._retried = true
      const newToken = await refreshAccessToken()
      if (newToken) {
        cfg.headers.Authorization = `Bearer ${newToken}`
        return api(cfg)
      }
      window.dispatchEvent(new Event(AUTH_LOGOUT_EVENT))
    }
    return Promise.reject(error)
  },
)
