import type { ReactNode } from "react"
import { NavLink } from "react-router-dom"

import { cn } from "@/lib/utils"

export interface SectionTabItem {
  title: string
  to: string
  icon?: ReactNode
}

/** Под-навигация для составных страниц (`/system`, `/settings`) — общий
 * компонент вместо отдельного велосипеда на каждую секцию (см.
 * IMPLEMENTATION_PLAN.md §0.4).
 *
 * Десктоп — обычная вертикальная колонка слева. Мобильный — не встроенная
 * колонка (расходует драгоценную ширину экрана и требует скролла страницы
 * до неё), а "плавающий остров": закреплённая внизу панель, по центру, НЕ
 * прижатая к краю экрана (похоже на bottom-nav многих мобильных веб-приложений,
 * но не примагничена вплотную к самому низу — см. PLAN.md Ф5, п.3).
 */
export function SectionTabs({
  items,
  children,
}: {
  items: SectionTabItem[]
  children: ReactNode
}) {
  return (
    <div className="flex gap-6">
      <nav className="hidden w-48 shrink-0 space-y-1 md:block">
        {items.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end
            className={({ isActive }) =>
              cn(
                "flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
                isActive
                  ? "bg-sidebar-accent text-sidebar-accent-foreground font-medium"
                  : "text-muted-foreground hover:bg-sidebar-accent/50 hover:text-foreground"
              )
            }
          >
            {item.icon}
            <span>{item.title}</span>
          </NavLink>
        ))}
      </nav>

      {/* Мобильный "плавающий остров" — fixed, по центру, с отступом от
          края (включая safe-area на iOS), не на всю ширину экрана. */}
      <nav
        className="fixed inset-x-0 z-40 mx-auto flex w-fit max-w-[calc(100vw-2rem)] items-center gap-1 rounded-full border bg-[#0D504B]/90 p-1.5 shadow-lg backdrop-blur-md md:hidden"
        style={{ bottom: "max(1.5rem, env(safe-area-inset-bottom))" }}
      >
        {items.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end
            className={({ isActive }) =>
              cn(
                "flex items-center gap-1.5 rounded-full px-3 py-2 text-xs font-medium whitespace-nowrap transition-colors",
                isActive
                  ? "bg-[#009080] text-white"
                  : "text-white/70 hover:text-white"
              )
            }
          >
            {item.icon}
          </NavLink>
        ))}
      </nav>

      {/* Отступ снизу на мобильном, чтобы плавающий остров не перекрывал
          последний контент страницы. */}
      <div className="min-w-0 flex-1 pb-20 md:pb-0">{children}</div>
    </div>
  )
}

