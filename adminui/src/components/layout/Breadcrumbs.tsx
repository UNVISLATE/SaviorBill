import { useLocation } from "react-router-dom"

import { cn } from "@/lib/utils"
import { matchRouteChain } from "@/lib/route-meta"
import { useBreadcrumbState } from "@/hooks/use-breadcrumb"
import {
  Breadcrumb,
  BreadcrumbEllipsis,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/shadsnui/breadcrumb"

/**
 * Хлебные крошки строятся ВСЕЙ цепочкой сегментов маршрута (см.
 * `lib/route-meta.ts`), а не одной "текущей" меткой — раньше составные
 * разделы (`/system/*`, `/settings/*`) были видны в крошках только как один
 * пункт верхнего уровня, без под-страницы (см. PLAN.md Ф5).
 *
 * `extra` — доп. сегмент поверх цепочки маршрута для динамического контента
 * (например, имя открытого пользователя) — задаётся страницей через
 * `useBreadcrumbExtra()`, не связан со статической структурой маршрутов.
 *
 * На мобильном (`sm:` и меньше) цепочка длиннее 2 сегментов схлопывается:
 * показываем только первый и последний, середина — `…`.
 */
export function Breadcrumbs() {
  const location = useLocation()
  const { extra } = useBreadcrumbState()
  const chain = matchRouteChain(location.pathname)
  const items = chain.length > 0 ? chain : [{ path: "/", title: "Дашборд" }]
  const isLast = (i: number) => i === items.length - 1 && !extra

  return (
    <Breadcrumb>
      <BreadcrumbList className="flex-nowrap">
        {items.map((item, i) => (
          <span key={item.path} className="contents">
            <BreadcrumbItem
              className={cn(
                // Схлопываем середину цепочки на мобильном — оставляем
                // первый и последний сегмент реального маршрута видимыми.
                i !== 0 && i !== items.length - 1 && "hidden sm:inline-flex",
              )}
            >
              {isLast(i) ? (
                <BreadcrumbPage>{item.title}</BreadcrumbPage>
              ) : (
                <BreadcrumbLink href={item.path}>{item.title}</BreadcrumbLink>
              )}
            </BreadcrumbItem>
            {i < items.length - 1 && (
              <>
                <BreadcrumbSeparator className="hidden sm:inline-flex" />
                {i === 0 && items.length > 2 && (
                  <BreadcrumbItem className="sm:hidden">
                    <BreadcrumbEllipsis />
                  </BreadcrumbItem>
                )}
                {i === 0 && items.length > 2 && (
                  <BreadcrumbSeparator className="sm:hidden" />
                )}
              </>
            )}
          </span>
        ))}
        {extra && (
          <>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage className="max-w-[16rem] truncate">
                {extra}
              </BreadcrumbPage>
            </BreadcrumbItem>
          </>
        )}
      </BreadcrumbList>
    </Breadcrumb>
  )
}

