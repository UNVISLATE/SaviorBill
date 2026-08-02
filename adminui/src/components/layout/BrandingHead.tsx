import { useEffect } from "react"

import { useBranding } from "@/hooks/use-branding"

/**
 * Применяет брендинг к `document.title` и favicon — раньше отдельного
 * компонента для этого не было вообще, поэтому смена `ui.admin.name`/
 * `ui.admin.favicon` через настройки никак не отражалась во вкладке
 * браузера (см. PLAN.md). Рендерит `null`, монтируется один раз в App.tsx.
 */
export function BrandingHead() {
  const { name, faviconUrl } = useBranding()

  useEffect(() => {
    document.title = name
  }, [name])

  useEffect(() => {
    if (!faviconUrl) return
    let link = document.querySelector<HTMLLinkElement>("link[rel~='icon']")
    if (!link) {
      link = document.createElement("link")
      link.rel = "icon"
      document.head.appendChild(link)
    }
    link.href = faviconUrl
  }, [faviconUrl])

  return null
}
