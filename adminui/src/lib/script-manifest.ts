/**
 * Проверка наличия реального манифеста формы или предустановок в скрипте.
 * Пустой объект `{}` или `{ "manifest": {} }` манифестом НЕ считается.
 */
export function hasScriptManifest(settings: Record<string, unknown> | null | undefined): boolean {
  if (!settings || typeof settings !== "object") return false
  const m = ((settings as any).manifest || settings) as Record<string, any>
  if (!m || typeof m !== "object") return false

  const hasClientFields = Array.isArray(m.client_order_form) && m.client_order_form.length > 0
  const hasSettingsFields = Array.isArray(m.settings_form) && m.settings_form.length > 0
  const hasPrefill = Boolean(m.prefill?.name || m.prefill?.slug)

  return Boolean(hasClientFields || hasSettingsFields || hasPrefill)
}
