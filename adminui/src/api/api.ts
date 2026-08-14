import axios, { type AxiosError, type InternalAxiosRequestConfig } from "axios"

/** Событие: сессия истекла (refresh не удался) — слушает AuthProvider. */
export const AUTH_LOGOUT_EVENT = "sb-admin:logout"
/** Событие: 2FA обязательна настройкой инстанса, но не включена у аккаунта —
 * backend отвечает 403 `totp_setup_required` на ЛЮБОЕ админ-действие (кроме
 * /admin/me и самих роутов настройки 2FA), см. dependencies/twofa.py.
 * Слушает ProfileDialogHost, чтобы сразу открыть профиль вместо немого 403. */
export const TOTP_SETUP_REQUIRED_EVENT = "sb-admin:totp-setup-required"

export const api = axios.create({
  // Каждый роутер (admin/auth/user/...) уже несёт полный "/api/v1/..." префикс
  // сам (см. src/api/v1/admin/__init__.py) — здесь достаточно "/api".
  baseURL: "/api",
  // Access/refresh — httpOnly cookies (см. security/sec/cookies.py на
  // стороне billing), не localStorage: браузер прикладывает их сам, JS их
  // не видит и не может ни прочитать, ни вписать в заголовок Authorization.
  withCredentials: true,
})

// Однополётный refresh — параллельные 401 не должны насоздать N параллельных
// /auth/refresh (backend ротирует refresh_token, второй вызов инвалидировал бы
// токен, который первый вызов ещё не успел сохранить).
let refreshPromise: Promise<boolean> | null = null

async function refreshAccessToken(): Promise<boolean> {
  if (!refreshPromise) {
    refreshPromise = axios
      .post("/api/v1/auth/refresh", null, { withCredentials: true })
      .then(() => true)
      .catch(() => false)
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
      const refreshed = await refreshAccessToken()
      if (refreshed) {
        return api(cfg)
      }
      window.dispatchEvent(new Event(AUTH_LOGOUT_EVENT))
    }
    if (
      error.response?.status === 403 &&
      (error.response.data as { detail?: string } | undefined)?.detail === "totp_setup_required"
    ) {
      window.dispatchEvent(new Event(TOTP_SETUP_REQUIRED_EVENT))
    }
    return Promise.reject(error)
  },
)
