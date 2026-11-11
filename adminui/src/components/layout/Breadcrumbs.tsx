import { Link, useLocation } from "react-router-dom"

import { cn } from "@/lib/utils"
import { matchRouteChain } from "@/lib/route-meta"
import { useBreadcrumbState, type BreadcrumbExtraSegment, type BreadcrumbExtraValue } from "@/hooks/use-breadcrumb"
import {
  Breadcrumb,
  BreadcrumbEllipsis,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/shadsnui/breadcrumb"

function normalizeExtraSegments(extra: BreadcrumbExtraValue): BreadcrumbExtraSegment[] {
  if (!extra) return []
  if (typeof extra === "string") return [{ title: extra }]
  return Array.isArray(extra) ? extra : [extra]
}

/**
 * Хлебные крошки строятся ВСЕЙ цепочкой сегментов маршрута (см.
 * `lib/route-meta.ts`), а не одной "текущей" меткой — раньше составные
 * разделы (`/system/*`, `/settings/*`) были видны в крошках только как один
 * пункт верхнего уровня, без под-страницы (см. PLAN.md Ф5).
 *
 * `extra` — доп. сегмент(ы) поверх цепочки маршрута для динамического контента
 * (например, имя открытого пользователя или `Скрипт > Манифест`) — задаётся
 * страницей через `useBreadcrumbExtra()`, не связан со статической структурой маршрутов.
 *
 * На мобильном (`sm:` и меньше) цепочка длиннее 2 сегментов схлопывается:
 * показываем только первый и последний, середина — `…`.
 */
export function Breadcrumbs() {
  const location = useLocation()
  const { extra } = useBreadcrumbState()
  const chain = matchRouteChain(location.pathname)
  const routeItems: BreadcrumbExtraSegment[] =
    chain.length > 0 ? chain : [{ path: "/", title: "Дашборд" }]
  const items: BreadcrumbExtraSegment[] = [...routeItems, ...normalizeExtraSegments(extra)]

  return (
    <Breadcrumb>
      <BreadcrumbList className="flex-nowrap">
        {items.map((item, i) => {
          const isLast = i === items.length - 1
          return (
            <span key={`${item.path ?? "extra"}-${i}-${item.title}`} className="contents">
              <BreadcrumbItem
                className={cn(
                  // Схлопываем середину цепочки на мобильном — оставляем
                  // первый и последний сегмент видимыми.
                  i !== 0 && !isLast && "hidden sm:inline-flex",
                )}
              >
                {isLast || !item.path ? (
                  <BreadcrumbPage className={cn(i >= routeItems.length && "max-w-[16rem] truncate")}>
                    {item.title}
                  </BreadcrumbPage>
                ) : (
                  <BreadcrumbLink
                    render={<Link to={item.path} />}
                    className={cn(i >= routeItems.length && "max-w-[16rem] truncate")}
                  >
                    {item.title}
                  </BreadcrumbLink>
                )}
              </BreadcrumbItem>
              {!isLast && (
                <>
                  <BreadcrumbSeparator className="hidden sm:inline-flex" />
                  {i === 0 && items.length > 2 && (
                    <>
                      <BreadcrumbItem className="sm:hidden">
                        <BreadcrumbEllipsis />
                      </BreadcrumbItem>
                      <BreadcrumbSeparator className="sm:hidden" />
                    </>
                  )}
                </>
              )}
            </span>
          )
        })}
      </BreadcrumbList>
    </Breadcrumb>
  )
}

