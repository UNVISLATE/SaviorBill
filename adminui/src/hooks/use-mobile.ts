import * as React from "react"

const MOBILE_BREAKPOINT = 768

function computeIsMobile(): boolean {
  // SSR/тестовое окружение без window — считаем desktop (безопасный дефолт,
  // не мигает моб. раскладкой там, где window вообще недоступен).
  if (typeof window === "undefined") return false
  return window.innerWidth < MOBILE_BREAKPOINT
}

export function useIsMobile() {
  // Синхронная инициализация по фактической ширине окна при монтировании —
  // раньше первый рендер всегда начинался с `undefined` -> `false`, что на
  // самом мобильном устройстве на долю секунды показывало десктопную
  // раскладку (лишний layout-flash до первого useEffect).
  const [isMobile, setIsMobile] = React.useState<boolean>(computeIsMobile)

  React.useEffect(() => {
    const mql = window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT - 1}px)`)
    const onChange = () => {
      setIsMobile(window.innerWidth < MOBILE_BREAKPOINT)
    }
    mql.addEventListener("change", onChange)
    return () => mql.removeEventListener("change", onChange)
  }, [])

  return isMobile
}
