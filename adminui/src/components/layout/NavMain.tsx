import { ChevronRight } from "lucide-react"
import { useLocation, useNavigate } from "react-router-dom"

import { cn } from "@/lib/utils"
import { useAuth } from "@/hooks/use-auth"
import type { NavGroup } from "@/components/layout/nav-config"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/shadsnui/collapsible"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/shadsnui/popover"
import {
  SidebarGroup,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  useSidebar,
} from "@/components/shadsnui/sidebar"

/**
 * Основная навигация сайдбара (см. ppp/nav-main.tsx как референс).
 * Категория с одним пунктом — обычная ссылка. Категория с несколькими
 * пунктами: в развёрнутом сайдбаре — Collapsible с под-списком, в
 * свёрнутом (icon-rail) — сама некликабельна, по наведению открывает
 * всплывающий Popover с выбором пункта (категории — не страницы).
 */
export function NavMain({ groups }: { groups: NavGroup[] }) {
  const { can } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const { state, isMobile } = useSidebar()
  const collapsedRail = state === "collapsed" && !isMobile

  return (
    <SidebarGroup>
      <SidebarMenu>
        {groups.map((group) => {
          const items = group.items.filter((i) => !i.perm || can(i.perm))
          if (items.length === 0) return null

          if (items.length === 1) {
            const item = items[0]
            return (
              <SidebarMenuItem key={group.title}>
                <SidebarMenuButton
                  tooltip={item.title}
                  isActive={location.pathname === item.url}
                  onClick={() => navigate(item.url)}
                >
                  <item.icon />
                  <span>{item.title}</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            )
          }

          const GroupIcon = group.icon
          const isActiveGroup = items.some((i) => i.url === location.pathname)

          if (collapsedRail) {
            return (
              <SidebarMenuItem key={group.title}>
                <Popover>
                  <PopoverTrigger
                    openOnHover
                    closeDelay={100}
                    nativeButton={false}
                    render={
                      <SidebarMenuButton isActive={isActiveGroup}>
                        <GroupIcon />
                        <span>{group.title}</span>
                      </SidebarMenuButton>
                    }
                  />
                  <PopoverContent
                    side="right"
                    align="start"
                    className="w-52 p-1.5"
                  >
                    <div className="px-2 py-1 text-xs font-medium text-muted-foreground">
                      {group.title}
                    </div>
                    <div className="flex flex-col gap-0.5">
                      {items.map((item) => (
                        <button
                          key={item.url}
                          type="button"
                          onClick={() => navigate(item.url)}
                          className={cn(
                            "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm text-popover-foreground hover:bg-accent hover:text-accent-foreground",
                            location.pathname === item.url &&
                              "bg-accent font-medium text-accent-foreground"
                          )}
                        >
                          <item.icon className="size-4" />
                          {item.title}
                        </button>
                      ))}
                    </div>
                  </PopoverContent>
                </Popover>
              </SidebarMenuItem>
            )
          }

          return (
            <Collapsible key={group.title} defaultOpen>
              <SidebarMenuItem>
                <CollapsibleTrigger
                  nativeButton={false}
                  render={
                    <SidebarMenuButton
                      isActive={isActiveGroup}
                      className="group"
                    >
                      <GroupIcon />
                      <span>{group.title}</span>
                      <ChevronRight className="ml-auto size-3.5 shrink-0 transition-transform group-data-[panel-open]:rotate-90" />
                    </SidebarMenuButton>
                  }
                />
                <CollapsibleContent>
                  <SidebarMenuSub>
                    {items.map((item) => (
                      <SidebarMenuSubItem key={item.url}>
                        <SidebarMenuSubButton
                          render={<button type="button" />}
                          isActive={location.pathname === item.url}
                          onClick={() => navigate(item.url)}
                        >
                          <item.icon />
                          <span>{item.title}</span>
                        </SidebarMenuSubButton>
                      </SidebarMenuSubItem>
                    ))}
                  </SidebarMenuSub>
                </CollapsibleContent>
              </SidebarMenuItem>
            </Collapsible>
          )
        })}
      </SidebarMenu>
    </SidebarGroup>
  )
}
