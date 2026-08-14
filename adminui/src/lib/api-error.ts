import { isAxiosError } from "axios"

/** Достаёт `detail` из тела ответа бэкенда (FastAPI `{"detail": "..."}`),
 * если `err` — ошибка axios и `detail` — строка. Заменяет разбросанные по
 * компонентам `// @ts-expect-error — axios error shape`. */
export function getErrorDetail(err: unknown): string | undefined {
  if (!isAxiosError(err)) return undefined
  const detail = (err.response?.data as { detail?: unknown } | undefined)?.detail
  return typeof detail === "string" ? detail : undefined
}

/** HTTP статус ответа, если `err` — ошибка axios. */
export function getErrorStatus(err: unknown): number | undefined {
  if (!isAxiosError(err)) return undefined
  return err.response?.status
}
