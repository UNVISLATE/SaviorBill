import type { ReactNode } from "react"
import { NavLink } from "react-router-dom"
import { Info } from "lucide-react"

import { cn } from "@/lib/utils"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/shadsnui/tooltip"

export interface SectionTabItem {
  title: string
  to: string
  icon?: ReactNode
  group?: string
  hint?: string
}

/** Под-навигация для составных страниц (`/system`, `/settings`) — общий
 * компонент вместо отдельного велосипеда на каждую секцию.
 *
 * Десктоп — вертикальная колонка w-56 с поддержкой группировки, разделителей
 * и подсказок [i]. Мобильный — плавающий остров.
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
        {items.map((item, idx) => {
          const prevItem = idx > 0 ? items[idx - 1] : null
          const isNewGroup = item.group && (!prevItem || prevItem.group !== item.group)

          return (
            <div key={item.to}>
              {isNewGroup && (
                <div
                  className={cn(
                    "px-2.5 pb-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/70",
                    idx > 0 && "pt-3.5 border-t border-border/50 mt-2.5"
                  )}
                >
                  {item.group}
                </div>
              )}
              <NavLink
                to={item.to}
                title={item.title}
                end
                className={({ isActive }) =>
                  cn(
                    "flex items-center justify-between rounded-md px-3 py-2 text-sm transition-colors",
                    isActive
                      ? "bg-sidebar-accent text-sidebar-accent-foreground font-medium"
                      : "text-muted-foreground hover:bg-sidebar-accent/50 hover:text-foreground"
                  )
                }
              >
                <div className="flex min-w-0 items-center gap-2">
                  <span className="shrink-0">{item.icon}</span>
                  <span className="truncate whitespace-nowrap">{item.title}</span>
                </div>
                {item.hint && (
                  <span
                    onClick={(e) => {
                      e.preventDefault()
                      e.stopPropagation()
                    }}
                    className="inline-flex shrink-0 items-center text-muted-foreground/60 transition-colors hover:text-foreground ml-1"
                  >
                    <Tooltip>
                      <TooltipTrigger
                        render={
                          <span className="p-0.5 cursor-help">
                            <Info className="size-3.5" />
                          </span>
                        }
                      />
                      <TooltipContent className="max-w-xs text-xs font-normal leading-relaxed">
                        {item.hint}
                      </TooltipContent>
                    </Tooltip>
                  </span>
                )}
              </NavLink>
            </div>
          )
        })}
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
