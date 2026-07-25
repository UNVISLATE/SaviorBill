/**
 * Локальное (клиентское) версионирование тела Lua-скрипта.
 *
 * Бэкенд (`lua_scripts`) хранит только текущий код + sha256, без истории
 * версий/commit-сообщений — добавление полноценной версионной таблицы на
 * сервере это отдельная задача (миграция + роуты). До тех пор версии
 * пишутся в localStorage: при каждом успешном сохранении текущая версия
 * (код + commit message + автор + время) пушится в список, привязанный к
 * id скрипта. Действие полностью рабочее (история, просмотр, восстановление,
 * diff), только источник истории — браузер администратора, а не БД.
 */

export interface LuaScriptVersion {
  /** Порядковый номер версии (1, 2, 3…), возрастает монотонно для скрипта. */
  version: number
  code: string
  /** Commit message — краткое описание изменений. */
  message: string
  createdAt: string
  authorLogin: string | null
}

const STORAGE_PREFIX = "lua-script-versions:"
/** Не даём истории разрастаться бесконечно в localStorage. */
const MAX_VERSIONS_PER_SCRIPT = 100

function storageKey(scriptId: number): string {
  return `${STORAGE_PREFIX}${scriptId}`
}

export function listVersions(scriptId: number): LuaScriptVersion[] {
  try {
    const raw = localStorage.getItem(storageKey(scriptId))
    if (!raw) return []
    const parsed = JSON.parse(raw) as LuaScriptVersion[]
    if (!Array.isArray(parsed)) return []
    // Новые сверху.
    return parsed.slice().sort((a, b) => b.version - a.version)
  } catch {
    return []
  }
}

export function pushVersion(
  scriptId: number,
  code: string,
  message: string,
  authorLogin: string | null,
): LuaScriptVersion {
  const existing = listVersions(scriptId)
  const nextVersion = existing.length > 0 ? existing[0].version + 1 : 1
  const entry: LuaScriptVersion = {
    version: nextVersion,
    code,
    message: message.trim() || "(без описания)",
    createdAt: new Date().toISOString(),
    authorLogin,
  }
  const next = [entry, ...existing].slice(0, MAX_VERSIONS_PER_SCRIPT)
  localStorage.setItem(storageKey(scriptId), JSON.stringify(next))
  return entry
}

export function clearVersions(scriptId: number): void {
  localStorage.removeItem(storageKey(scriptId))
}
