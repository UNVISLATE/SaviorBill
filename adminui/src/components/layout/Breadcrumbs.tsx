import { useLocation } from "react-router-dom"

import { footerNavItems, navGroups } from "@/components/layout/nav-config"
import { useBreadcrumbState } from "@/hooks/use-breadcrumb"
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/shadsnui/breadcrumb"

const ALL_ITEMS = [...navGroups.flatMap((g) => g.items), ...footerNavItems]

export function Breadcrumbs() {
  const location = useLocation()
  const { extra } = useBreadcrumbState()
  const current =
    ALL_ITEMS.find((i) => i.url === location.pathname) ??
    ALL_ITEMS.filter((i) => i.url !== "/" && location.pathname.startsWith(i.url))
      .sort((a, b) => b.url.length - a.url.length)[0]
  const title = current?.title ?? "Дашборд"

  return (
    <Breadcrumb>
      <BreadcrumbList className="flex-nowrap">
        <BreadcrumbItem>
          {extra ? (
            <BreadcrumbLink href={location.pathname}>{title}</BreadcrumbLink>
          ) : (
            <BreadcrumbPage>{title}</BreadcrumbPage>
          )}
        </BreadcrumbItem>
        {extra && (
          <>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage className="truncate max-w-[16rem]">
                {extra}
              </BreadcrumbPage>
            </BreadcrumbItem>
          </>
        )}
      </BreadcrumbList>
    </Breadcrumb>
  )
}

