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
 * Десктоп — вертикальная колонка фиксированной ширины w-56, где все пункты
 * строго умещаются в одну строку. Мобильный — плавающий остров.
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
      <nav className="hidden w-56 shrink-0 space-y-1 md:block">
        {items.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            title={item.title}
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
            <span className="shrink-0">{item.icon}</span>
            <span className="truncate whitespace-nowrap">{item.title}</span>
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
            aria-label={item.title}
            title={item.title}
            className={({ isActive }) =>
              cn(
                "flex size-10 items-center justify-center rounded-full text-sm transition-colors",
                isActive
                  ? "bg-white/20 text-white font-medium shadow-inner"
                  : "text-white/70 hover:bg-white/10 hover:text-white"
              )
            }
          >
            {item.icon}
          </NavLink>
        ))}
      </nav>

      <div className="min-w-0 flex-1">{children}</div>
    </div>
  )
}
