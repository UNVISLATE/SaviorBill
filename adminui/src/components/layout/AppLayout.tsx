import { Outlet, useLocation, useNavigate } from "react-router-dom"
import { LogOut } from "lucide-react"

import { useAuth } from "@/hooks/use-auth"
import { navGroups } from "@/components/layout/nav-config"
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
  SidebarTrigger,
} from "@/components/shadsnui/sidebar"
import { Separator } from "@/components/shadsnui/separator"

export function AppLayout() {
  const { me, can, logout } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()

  return (
    <SidebarProvider>
      <Sidebar>
        <SidebarHeader>
          <div className="flex items-center gap-2 px-2 py-1.5">
            <img src="/unvi/logo_1x1_32.webp" alt="" className="size-6 rounded" />
            <span className="text-sm font-semibold">SaviorBill Admin</span>
          </div>
        </SidebarHeader>
        <SidebarContent>
          {navGroups.map((group) => {
            const items = group.items.filter((i) => !i.perm || can(i.perm))
            if (items.length === 0) return null
            return (
              <SidebarGroup key={group.title}>
                <SidebarGroupLabel>{group.title}</SidebarGroupLabel>
                <SidebarGroupContent>
                  <SidebarMenu>
                    {items.map((item) => (
                      <SidebarMenuItem key={item.url}>
                        <SidebarMenuButton
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
              </SidebarGroup>
            )
          })}
        </SidebarContent>
        <SidebarFooter>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton onClick={logout}>
                <LogOut />
                <span>{me?.login ?? "…"} — выйти</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
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
