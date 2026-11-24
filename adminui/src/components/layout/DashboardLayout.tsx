import { useMemo } from "react"
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"

import { api } from "@/api/api.ts"
import { useAuth } from "@/hooks/use-auth"
import { useBranding } from "@/hooks/use-branding"
import { footerNavItems, isNavItemVisible, navGroups, type NavItem } from "@/components/layout/nav-config"
import { Plug, MessageSquare, Gift, Users as UsersIcon, Shield, Database, Layers, BookOpen, FileText } from "lucide-react"

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
import { ButtonGroup, ButtonGroupSeparator } from "@/components/shadsnui/button-group"
import { Button } from "@/components/shadsnui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/shadsnui/tooltip"
import { ErrorBoundary } from "@/components/common/ErrorBoundary"
import { formatAppVersion } from "@/lib/version"

interface PluginNavItemMeta {
  slug: string
  name: string
  status: string
  admin_ui?: {
    nav?: {
      title?: string
      icon?: string
      required_perm?: string
    }
  }
}

export function DashboardLayout() {
  const { can } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const branding = useBranding()

  const { data: health } = useQuery({
    queryKey: ["app-health"],
    queryFn: async () => (await api.get<{ app_name: string; app_version: string; debug?: boolean; docs_enabled?: boolean }>("/health")).data,
    staleTime: 60_000,
  })
  const versionInfo = useMemo(() => {
    const raw =
      health?.app_version || (typeof __APP_VERSION__ !== "undefined" ? __APP_VERSION__ : "0.0.0-dev")
    return formatAppVersion(raw)
  }, [health?.app_version])
  const isDebug = Boolean(health?.debug)

  const { data: plugins = [] } = useQuery<PluginNavItemMeta[]>({
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
        const IconComp = (PLUGIN_ICONS[nav.icon || ""] || Plug) as typeof Plug
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
        icon: Plug,
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
      <SidebarInset className="min-w-0">
        <header className="flex h-12 items-center justify-between border-b px-4">
          <div className="flex items-center gap-2 min-w-0">
            <SidebarTrigger />
            <Separator orientation="vertical" className="h-4" />
            <Breadcrumbs />
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {isDebug ? (
              <ButtonGroup className="rounded-full border border-border/70 bg-muted/30 shadow-2xs p-0.5 items-center">
                <Tooltip>
                  <TooltipTrigger
                    render={
                      <Button
                        variant="ghost"
                        size="xs"
                        nativeButton={false}
                        className="rounded-full h-6 px-2.5 text-xs font-mono font-medium text-muted-foreground hover:text-foreground hover:bg-muted/80 gap-1.5 transition-colors"
                        render={<a href="/api/docs" target="_blank" rel="noreferrer" />}
                      >
                        <BookOpen className="size-3 text-emerald-500" />
                        <span>Swagger</span>
                      </Button>
                    }
                  />
                  <TooltipContent>Swagger API документация (/api/docs)</TooltipContent>
                </Tooltip>

                <ButtonGroupSeparator className="h-3 my-auto bg-border/60" />

                <Tooltip>
                  <TooltipTrigger
                    render={
                      <Button
                        variant="ghost"
                        size="xs"
                        nativeButton={false}
                        className="rounded-full h-6 px-2.5 text-xs font-mono font-medium text-muted-foreground hover:text-foreground hover:bg-muted/80 gap-1.5 transition-colors"
                        render={<a href="/api/redoc" target="_blank" rel="noreferrer" />}
                      >
                        <FileText className="size-3 text-teal-400" />
                        <span>ReDoc</span>
                      </Button>
                    }
                  />
                  <TooltipContent>ReDoc API спецификация (/api/redoc)</TooltipContent>
                </Tooltip>

                <ButtonGroupSeparator className="h-3 my-auto bg-border/60" />

                <Tooltip>
                  <TooltipTrigger
                    render={
                      <Button
                        variant="ghost"
                        size="xs"
                        nativeButton={false}
                        className="rounded-full h-6 px-2.5 text-xs font-mono font-medium text-muted-foreground hover:text-foreground hover:bg-muted/80 gap-1.5 transition-colors max-w-[170px]"
                        render={<Link to="/about" />}
                      >
                        <span className="size-1.5 rounded-full bg-emerald-500 animate-pulse shrink-0" />
                        <span className="truncate">{versionInfo.short}</span>
                      </Button>
                    }
                  />
                  <TooltipContent>О системе SaviorBill ({versionInfo.full})</TooltipContent>
                </Tooltip>
              </ButtonGroup>
            ) : (
              <Tooltip>
                <TooltipTrigger
                  render={
                    <Link
                      to="/about"
                      className="flex items-center gap-1.5 rounded-full border border-border/70 bg-muted/30 hover:bg-muted px-2.5 py-1 text-xs font-mono font-medium text-muted-foreground hover:text-foreground transition-all hover:border-primary/40 shadow-2xs max-w-[170px]"
                    >
                      <span className="size-1.5 rounded-full bg-emerald-500 animate-pulse shrink-0" />
                      <span className="truncate">{versionInfo.short}</span>
                    </Link>
                  }
                />
                <TooltipContent>О системе SaviorBill ({versionInfo.full})</TooltipContent>
              </Tooltip>
            )}
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
