import type { ReactNode } from "react"
import { NavLink } from "react-router-dom"

import { cn } from "@/lib/utils"

export interface SectionTabItem {
  title: string
  to: string
  icon?: ReactNode
}

/** Вертикальная под-навигация для составных страниц (`/system`, `/settings`)
 * — общий компонент вместо отдельного велосипеда на каждую секцию
 * (см. IMPLEMENTATION_PLAN.md §0.4). */
export function SectionTabs({
  items,
  children,
}: {
  items: SectionTabItem[]
  children: ReactNode
}) {
  return (
    <div className="flex gap-6">
      <nav className="w-48 shrink-0 space-y-1">
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
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  )
}
