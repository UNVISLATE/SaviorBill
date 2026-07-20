import { ChevronRight } from "lucide-react"
import { Outlet, useLocation, useNavigate } from "react-router-dom"

import { useAuth } from "@/hooks/use-auth"
import { footerNavItems, navGroups } from "@/components/layout/nav-config"
import { NavUser } from "@/components/layout/NavUser"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/shadsnui/collapsible"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarSeparator,
  SidebarTrigger,
} from "@/components/shadsnui/sidebar"
import { Separator } from "@/components/shadsnui/separator"

export function DashboardLayout() {
  const { me, can } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()

  const visibleFooterItems = footerNavItems.filter((i) => !i.perm || can(i.perm))

  return (
    <SidebarProvider>
      {/* collapsible="icon" — сворачивается до колонки с иконками, а не
          исчезает целиком (offcanvas), как просили. */}
      <Sidebar variant="inset" collapsible="icon">
        <SidebarHeader>
          <div className="flex items-center gap-2 px-2 py-1.5">
            <img src="/unvi/logo_1x1_128.webp" alt="" className="size-8 shrink-0" />
            <span className="truncate text-lg font-semibold group-data-[collapsible=icon]:hidden">
              SaviorBill Admin
            </span>
          </div>
        </SidebarHeader>
        <SidebarContent>
          {navGroups.map((group) => {
            const items = group.items.filter((i) => !i.perm || can(i.perm))
            if (items.length === 0) return null
            return (
              <Collapsible key={group.title} defaultOpen>
                <SidebarGroup>
                  <CollapsibleTrigger
                    nativeButton={false}
                    render={
                      <SidebarGroupLabel className="group flex w-full cursor-pointer items-center justify-between">
                        <span>{group.title}</span>
                        <ChevronRight className="size-3.5 transition-transform group-data-[panel-open]:rotate-90" />
                      </SidebarGroupLabel>
                    }
                  />
                  <CollapsibleContent>
                    <SidebarGroupContent>
                      <SidebarMenu>
                        {items.map((item) => (
                          <SidebarMenuItem key={item.url}>
                            <SidebarMenuButton
                              tooltip={item.title}
                              isActive={location.pathname === item.url}
                              onClick={() => navigate(item.url)}
                            >
                              <item.icon />
                              <span>{item.title}</span>
                            </SidebarMenuButton>
                          </SidebarMenuItem>
                        ))}
                      </SidebarMenu>
                    </SidebarGroupContent>
                  </CollapsibleContent>
                </SidebarGroup>
              </Collapsible>
            )
          })}
        </SidebarContent>
        <SidebarFooter>
          {visibleFooterItems.length > 0 && (
            <>
              <SidebarMenu>
                {visibleFooterItems.map((item) => (
                  <SidebarMenuItem key={item.url}>
                    <SidebarMenuButton
                      tooltip={item.title}
                      isActive={location.pathname === item.url}
                      onClick={() => navigate(item.url)}
                    >
                      <item.icon />
                      <span>{item.title}</span>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
              <SidebarSeparator className="mx-0" />
            </>
          )}
          <NavUser />
        </SidebarFooter>
      </Sidebar>
      <SidebarInset>
        <header className="flex h-12 items-center gap-2 border-b px-4">
          <SidebarTrigger />
          <Separator orientation="vertical" className="h-4" />
          <span className="text-sm text-muted-foreground">{me?.role}</span>
        </header>
        <main className="flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}
