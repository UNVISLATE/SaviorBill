import { createContext, useContext, useEffect, useMemo, useState } from "react"
import type { ReactNode } from "react"

interface BreadcrumbState {
  extra: string | null
  setExtra: (title: string | null) => void
}

const BreadcrumbContext = createContext<BreadcrumbState | null>(null)

export function BreadcrumbProvider({ children }: { children: ReactNode }) {
  const [extra, setExtra] = useState<string | null>(null)
  const value = useMemo(() => ({ extra, setExtra }), [extra])
  return (
    <BreadcrumbContext.Provider value={value}>
      {children}
    </BreadcrumbContext.Provider>
  )
}

export function useBreadcrumbState() {
  const ctx = useContext(BreadcrumbContext)
  if (!ctx) throw new Error("useBreadcrumbState must be used within BreadcrumbProvider")
  return ctx
}

/** Страницы вызывают это, чтобы добавить доп. сегмент в хлебные крошки
 * (например, имя открытого пользователя) — сбрасывается при размонтировании. */
export function useBreadcrumbExtra(title: string | null | undefined) {
  const { setExtra } = useBreadcrumbState()
  useEffect(() => {
    setExtra(title ?? null)
    return () => setExtra(null)
  }, [title, setExtra])
}
