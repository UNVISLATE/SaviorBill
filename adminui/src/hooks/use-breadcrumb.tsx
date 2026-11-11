import { createContext, useContext, useEffect, useMemo, useState } from "react"
import type { ReactNode } from "react"

export interface BreadcrumbExtraSegment {
  title: string
  path?: string
}

export type BreadcrumbExtraValue =
  | string
  | BreadcrumbExtraSegment
  | BreadcrumbExtraSegment[]
  | null

interface BreadcrumbState {
  extra: BreadcrumbExtraValue
  setExtra: (value: BreadcrumbExtraValue) => void
}

const BreadcrumbContext = createContext<BreadcrumbState | null>(null)

export function BreadcrumbProvider({ children }: { children: ReactNode }) {
  const [extra, setExtra] = useState<BreadcrumbExtraValue>(null)
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

/** Страницы вызывают это, чтобы добавить доп. сегмент(ы) в хлебные крошки
 * (например, имя открытого скрипта и подстраницу) — сбрасывается при размонтировании. */
export function useBreadcrumbExtra(value: BreadcrumbExtraValue | undefined) {
  const { setExtra } = useBreadcrumbState()
  useEffect(() => {
    setExtra(value ?? null)
    return () => setExtra(null)
  }, [value, setExtra])
}
