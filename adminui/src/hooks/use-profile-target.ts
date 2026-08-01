import type { ProfileTarget } from "@/hooks/use-profile-dialog"

/**
 * Разрешить, какой режим профиля открывать по id пользователя.
 *
 * Раньше `openUserProfile(userId)` всегда открывал режим "чужого" профиля
 * (`view`), даже если админ кликал СВОЮ же строку в списке пользователей —
 * визуально и функционально это другой профиль (нет самообслуживания,
 * другие права), хотя пользователь ожидал попасть в свой обычный профиль.
 *
 * :arg userId: id аккаунта, чей профиль открываем.
 * :arg meId: id текущего авторизованного аккаунта (``undefined`` — ещё не
 *     загружен `/admin/me`; в этом случае считаем цель чужой — безопаснее
 *     показать "чужой" вид, чем ошибочно показать "свой").
 */
export function resolveProfileTarget(
  userId: number,
  meId: number | undefined,
): ProfileTarget {
  if (meId !== undefined && userId === meId) return { mode: "own" }
  return { mode: "view", userId }
}
