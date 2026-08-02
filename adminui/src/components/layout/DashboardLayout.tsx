import { Outlet, useLocation, useNavigate } from "react-router-dom"

import { useAuth } from "@/hooks/use-auth"
import { useBranding } from "@/hooks/use-branding"
import { footerNavItems, navGroups } from "@/components/layout/nav-config"
import { Logo } from "@/components/layout/Logo"
import { NavMain } from "@/components/layout/NavMain"
import { NavUser } from "@/components/layout/NavUser"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarRail,
  SidebarSeparator,
  SidebarTrigger,
} from "@/components/shadsnui/sidebar"
import { Separator } from "@/components/shadsnui/separator"
import { Breadcrumbs } from "@/components/layout/Breadcrumbs"
import { BreadcrumbProvider } from "@/hooks/use-breadcrumb"

export function DashboardLayout() {
  const { can } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const branding = useBranding()

  const visibleFooterItems = footerNavItems.filter((i) => !i.perm || can(i.perm))

  return (
    <SidebarProvider>
      <BreadcrumbProvider>
      <Sidebar variant="inset" collapsible="icon">
        <SidebarHeader>
          <div className="flex items-center gap-2 px-2 py-1.5">
            <Logo className="size-8" src={branding.logoUrl} />
            <span className="truncate text-lg font-semibold group-data-[collapsible=icon]:hidden">
              {branding.name}
            </span>
          </div>
        </SidebarHeader>
        <SidebarContent>
          <NavMain groups={navGroups} />
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
        <SidebarRail />
      </Sidebar>
      <SidebarInset>
        <header className="flex h-12 items-center gap-2 border-b px-4">
          <SidebarTrigger />
          <Separator orientation="vertical" className="h-4" />
          <Breadcrumbs />
        </header>
        <main className="flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </SidebarInset>
      </BreadcrumbProvider>
    </SidebarProvider>
  )
}
