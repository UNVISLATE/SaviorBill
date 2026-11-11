/**
 * Проверка наличия реального манифеста формы или предустановок в скрипте.
 * Пустой объект `{}` или `{ "manifest": {} }` манифестом НЕ считается.
 */
export function hasScriptManifest(settings: Record<string, unknown> | null | undefined): boolean {
  const manifest = extractScriptManifest(settings)
  if (!manifest) return false

  const hasClientFields = Array.isArray(manifest.client_order_form) && manifest.client_order_form.length > 0
  const hasSettingsFields = Array.isArray(manifest.settings_form) && manifest.settings_form.length > 0
  const hasViewFields = Array.isArray(manifest.client_view_form) && manifest.client_view_form.length > 0
  const hasLayout = Boolean(manifest.layout && typeof manifest.layout === "object")
  const hasPrefill = Boolean(
    manifest.prefill &&
    typeof manifest.prefill === "object" &&
    ((manifest.prefill as Record<string, unknown>).name || (manifest.prefill as Record<string, unknown>).slug)
  )

  return Boolean(hasClientFields || hasSettingsFields || hasViewFields || hasLayout || hasPrefill)
}

const MANIFEST_KEYS = new Set([
  "client_order_form",
  "settings_form",
  "client_view_form",
  "layout",
  "prefill",
  "media_download",
  "version",
  "name",
  "slug",
  "description",
  "author",
])

/**
 * Извлечь объект манифеста из поля ``settings`` Lua-скрипта.
 * Поддерживает как канонический ``settings.manifest``, так и плоские поля манифеста в ``settings``.
 */
export function extractScriptManifest(
  settings: Record<string, unknown> | string | null | undefined,
): Record<string, unknown> | null {
  let raw: unknown = settings
  if (typeof raw === "string") {
    try {
      raw = JSON.parse(raw)
    } catch {
      return null
    }
  }
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null
  const obj = raw as Record<string, unknown>

  let nested = obj.manifest
  if (typeof nested === "string") {
    try {
      nested = JSON.parse(nested)
    } catch {
      nested = null
    }
  }
  if (nested && typeof nested === "object" && !Array.isArray(nested) && Object.keys(nested).length > 0) {
    return nested as Record<string, unknown>
  }

  const hasFlatManifest = Object.keys(obj).some((k) => MANIFEST_KEYS.has(k) && obj[k] !== undefined && obj[k] !== null)
  if (hasFlatManifest) {
    return obj
  }

  return null
}
