/**
 * Хранилище пары токенов (access/refresh) в localStorage.
 *
 * localStorage — не самый безопасный вариант с точки зрения XSS (в отличие от
 * httpOnly-cookie), но соответствует контракту backend `POST /auth/login`,
 * который явно отдаёт токены в теле ответа (не ставит cookie) — см.
 * `src/api/v1/auth/local.py`. Если backend когда-нибудь перейдёт на httpOnly-cookie
 * для админки, это единственное место, которое нужно будет поменять.
 */
const ACCESS_KEY = "sb_admin_access"
const REFRESH_KEY = "sb_admin_refresh"

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
  is_active: boolean
}

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_KEY)
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY)
}

export function setTokens(pair: Pick<TokenPair, "access_token" | "refresh_token">) {
  localStorage.setItem(ACCESS_KEY, pair.access_token)
  localStorage.setItem(REFRESH_KEY, pair.refresh_token)
}

export function clearTokens() {
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
}
