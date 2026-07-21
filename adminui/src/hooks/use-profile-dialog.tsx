import { createContext, useContext, useState, type ReactNode } from "react"

/** Свой профиль (auth-контекст) или чужой (по id, admin-просмотр). Общий
 * Dialog/Drawer, меняется только источник данных секций — см.
 * IMPLEMENTATION_PLAN.md §4. */
export type ProfileTarget = { mode: "own" } | { mode: "view"; userId: number }

interface ProfileDialogContextValue {
  isOpen: boolean
  target: ProfileTarget
  openProfile: () => void
  openUserProfile: (userId: number) => void
  closeProfile: () => void
  /** Пока true — диалог/шторку нельзя закрыть кликом снаружи/Esc/свайпом
   * (только явной кнопкой "Закрыть"), чтобы не потерять загрузку аватарки. */
  isBusy: boolean
  setBusy: (busy: boolean) => void
}

const ProfileDialogContext = createContext<ProfileDialogContextValue | null>(null)

export function ProfileDialogProvider({ children }: { children: ReactNode }) {
  const [isOpen, setIsOpen] = useState(false)
  const [isBusy, setIsBusy] = useState(false)
  const [target, setTarget] = useState<ProfileTarget>({ mode: "own" })

  const value: ProfileDialogContextValue = {
    isOpen,
    target,
    openProfile: () => {
      setTarget({ mode: "own" })
      setIsOpen(true)
    },
    openUserProfile: (userId: number) => {
      setTarget({ mode: "view", userId })
      setIsOpen(true)
    },
    closeProfile: () => setIsOpen(false),
    isBusy,
    setBusy: setIsBusy,
  }

  return (
    <ProfileDialogContext.Provider value={value}>{children}</ProfileDialogContext.Provider>
  )
}

export function useProfileDialog(): ProfileDialogContextValue {
  const ctx = useContext(ProfileDialogContext)
  if (!ctx) throw new Error("useProfileDialog must be used within ProfileDialogProvider")
  return ctx
}
