import { createContext, useContext, useState, type ReactNode } from "react"

interface ProfileDialogContextValue {
  isOpen: boolean
  openProfile: () => void
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

  const value: ProfileDialogContextValue = {
    isOpen,
    openProfile: () => setIsOpen(true),
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
