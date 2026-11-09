import { useMemo } from "react"
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"

import { api } from "@/api/api.ts"
import { useAuth } from "@/hooks/use-auth"
import { useBranding } from "@/hooks/use-branding"
import { footerNavItems, isNavItemVisible, navGroups, type NavItem } from "@/components/layout/nav-config"
import { Plug, MessageSquare, Gift, Users as UsersIcon, Shield, Database, Layers } from "lucide-react"

const PLUGIN_ICONS: Record<string, React.ElementType> = {
  Plug,
  MessageSquare,
  Gift,
  Users: UsersIcon,
  Shield,
  Database,
  Layers,
}
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
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/shadsnui/tooltip"
import { ErrorBoundary } from "@/components/common/ErrorBoundary"

export function DashboardLayout() {
  const { can } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const branding = useBranding()

  const { data: health } = useQuery({
    queryKey: ["app-health"],
    queryFn: async () => (await api.get<{ app_name: string; app_version: string }>("/health")).data,
    staleTime: 60_000,
  })
  const rawVersion =
    health?.app_version || (typeof __APP_VERSION__ !== "undefined" ? __APP_VERSION__ : "0.0.0-dev")
  const displayVersion = rawVersion.startsWith("v") ? rawVersion : `v${rawVersion}`

  const { data: plugins = [] } = useQuery<any[]>({
    queryKey: ["admin", "plugins"],
    queryFn: async () => (await api.get("/v1/admin/plugins")).data,
    staleTime: 60_000,
  })

  const dynamicNavGroups = useMemo(() => {
    if (!plugins || plugins.length === 0) return navGroups

    const pluginNavItems: NavItem[] = []
    for (const p of plugins) {
      if (p.status === "active" && p.admin_ui?.nav) {
        const nav = p.admin_ui.nav
        const IconComp = (PLUGIN_ICONS[nav.icon] || Plug) as any
        pluginNavItems.push({
          title: nav.title || p.name,
          url: `/plugins/${p.slug}`,
          icon: IconComp,
          perm: nav.required_perm,
        })
      }
    }

    if (pluginNavItems.length === 0) return navGroups

    return [
      ...navGroups,
      {
        title: "Расширения",
        icon: Plug as any,
        items: pluginNavItems,
      },
    ]
  }, [plugins])

  const visibleFooterItems = footerNavItems.filter((i) => isNavItemVisible(can, i))

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
          <NavMain groups={dynamicNavGroups} />
        </SidebarContent>
        <SidebarFooter>
          {visibleFooterItems.length > 0 && (
            <>
              <SidebarMenu>
                {visibleFooterItems.map((item) => (
                  <SidebarMenuItem key={item.url}>
                    <SidebarMenuButton
                      tooltip={item.title}
                      isActive={
                        location.pathname === item.url ||
                        (item.url !== "/" && location.pathname.startsWith(item.url + "/"))
                      }
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
        <header className="flex h-12 items-center justify-between border-b px-4">
          <div className="flex items-center gap-2 min-w-0">
            <SidebarTrigger />
            <Separator orientation="vertical" className="h-4" />
            <Breadcrumbs />
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <Tooltip>
              <TooltipTrigger
                render={
                  <Link
                    to="/about"
                    className="flex items-center gap-1.5 rounded-full border border-border/70 bg-muted/30 hover:bg-muted px-2.5 py-1 text-xs font-mono font-medium text-muted-foreground hover:text-foreground transition-all hover:border-primary/40 shadow-2xs"
                  >
                    <span className="size-1.5 rounded-full bg-emerald-500 animate-pulse" />
                    <span>{displayVersion}</span>
                  </Link>
                }
              />
              <TooltipContent>О системе SaviorBill</TooltipContent>
            </Tooltip>
          </div>
        </header>
        <main className="flex-1 overflow-auto p-6">
          <ErrorBoundary key={location.pathname}>
            <Outlet />
          </ErrorBoundary>
        </main>
      </SidebarInset>
      </BreadcrumbProvider>
    </SidebarProvider>
  )
}
