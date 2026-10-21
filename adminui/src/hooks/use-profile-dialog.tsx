import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react"

import { useAuth } from "@/hooks/use-auth"
import { resolveProfileTarget } from "@/hooks/use-profile-target"

/** Свой профиль (auth-контекст), чужой (по id, admin-просмотр) или создание нового.
 * Общий Dialog/Drawer и единый визуальный шелл. */
export type ProfileTarget =
  | { mode: "own" }
  | { mode: "view"; userId: number }
  | { mode: "create" }

interface ProfileDialogContextValue {
  isOpen: boolean
  target: ProfileTarget
  openProfile: () => void
  openUserProfile: (userId: number) => void
  openCreateUser: () => void
  closeProfile: () => void
  /** Пока true — диалог/шторку нельзя закрыть кликом снаружи/Esc/свайпом
   * (только явной кнопкой "Закрыть"), чтобы не потерять загрузку аватарки. */
  isBusy: boolean
  setBusy: (busy: boolean) => void
}

const ProfileDialogContext = createContext<ProfileDialogContextValue | null>(null)

export function ProfileDialogProvider({ children }: { children: ReactNode }) {
  const { me } = useAuth()
  const [isOpen, setIsOpen] = useState(false)
  const [isBusy, setIsBusy] = useState(false)
  const [target, setTarget] = useState<ProfileTarget>({ mode: "own" })

  const openProfile = useCallback(() => {
    setTarget({ mode: "own" })
    setIsOpen(true)
  }, [])

  const openUserProfile = useCallback(
    (userId: number) => {
      // Свой же id из списка пользователей -> открыть как "свой" профиль,
      // а не как "чужой" (см. use-profile-target.ts).
      setTarget(resolveProfileTarget(userId, me?.id))
      setIsOpen(true)
    },
    [me?.id],
  )

  const openCreateUser = useCallback(() => {
    setTarget({ mode: "create" })
    setIsOpen(true)
  }, [])

  const closeProfile = useCallback(() => setIsOpen(false), [])

  const value = useMemo<ProfileDialogContextValue>(
    () => ({
      isOpen,
      target,
      openProfile,
      openUserProfile,
      openCreateUser,
      closeProfile,
      isBusy,
      setBusy: setIsBusy,
    }),
    [isOpen, target, openProfile, openUserProfile, openCreateUser, closeProfile, isBusy],
  )

  return (
    <ProfileDialogContext.Provider value={value}>{children}</ProfileDialogContext.Provider>
  )
}

export function useProfileDialog(): ProfileDialogContextValue {
  const ctx = useContext(ProfileDialogContext)
  if (!ctx) throw new Error("useProfileDialog must be used within ProfileDialogProvider")
  return ctx
}
