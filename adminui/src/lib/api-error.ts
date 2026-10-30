import { isAxiosError } from "axios"

/** Достаёт `detail` из тела ответа бэкенда (FastAPI `{"detail": "..."}`),
 * если `err` — ошибка axios. Поддерживает как строковые ошибки, так и
 * структурированные ошибки валидации Pydantic/FastAPI (HTTP 422). */
export function getErrorDetail(err: unknown): string | undefined {
  if (!isAxiosError(err)) return undefined
  const detail = (err.response?.data as { detail?: unknown } | undefined)?.detail
  if (typeof detail === "string") return detail
  if (Array.isArray(detail)) {
    return detail
      .map((item: unknown) => {
        if (typeof item === "string") return item
        if (item && typeof item === "object") {
          const rec = item as { loc?: unknown[]; msg?: string }
          const field = Array.isArray(rec.loc)
            ? rec.loc.filter((part) => part !== "body").join(".")
            : ""
          const msg = rec.msg || "Ошибка валидации"
          return field ? `${field}: ${msg}` : msg
        }
        return String(item)
      })
      .filter(Boolean)
      .join("; ")
  }
  return undefined
}

/** HTTP статус ответа, если `err` — ошибка axios. */
export function getErrorStatus(err: unknown): number | undefined {
  if (!isAxiosError(err)) return undefined
  return err.response?.status
}
