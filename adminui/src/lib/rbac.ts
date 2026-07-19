/**
 * Клиентское зеркало `security/rbac.py::has_perm` (биллинг, Python).
 *
 * Держать в точном соответствии с backend-реализацией — это только для UI-гейтинга
 * (скрыть пункт меню/кнопку), окончательную проверку всегда делает backend.
 */
export type PermNode = true | { [key: string]: PermNode } | Record<string, never>

export function hasPerm(perms: PermNode | null | undefined, path: string): boolean {
  if (!perms) return false
  let node: PermNode = perms
  for (const seg of path.split(".")) {
    if (node === true) return true
    if (typeof node !== "object") return false
    if (node["*"] === true) return true
    if (!(seg in node)) return false
    node = node[seg]
  }
  return node === true || typeof node === "object"
}
