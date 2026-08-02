/**
 * Реестр меток маршрутов для хлебных крошек — включает не только
 * верхнеуровневые разделы сайдбара, но и под-страницы составных секций
 * (`/system/*`, `/settings/*`), которых раньше не было видно в крошках
 * вообще (см. PLAN.md Ф5 — "хлебные крошки не видят подстраницы").
 *
 * `Breadcrumbs.tsx` строит цепочку из ВСЕХ записей, чей `path` — префикс
 * текущего `pathname` (по целым сегментам), от самой короткой к самой
 * длинной — не просто одну "текущую" метку.
 */
export interface RouteMeta {
  path: string
  title: string
}

export const routeMeta: RouteMeta[] = [
  { path: "/", title: "Дашборд" },
  { path: "/users", title: "Пользователи" },
  { path: "/audit", title: "Аудит" },
  { path: "/lua", title: "Скрипты" },
  { path: "/triggers", title: "Триггеры" },
  { path: "/email-templates", title: "Email-шаблоны" },
  { path: "/oauth", title: "OAuth-вход" },
  { path: "/catalog", title: "Каталоги" },
  { path: "/services", title: "Услуги" },
  { path: "/orders", title: "Заказы" },
  { path: "/purchases", title: "Платежи" },
  { path: "/promo", title: "Промокоды" },

  { path: "/system", title: "Система" },
  { path: "/system/overview", title: "Обзор" },
  { path: "/system/instances", title: "Инстансы" },
  { path: "/system/tasks", title: "Задачи" },
  { path: "/system/dlq", title: "DLQ" },

  { path: "/settings", title: "Настройки" },
  { path: "/settings/general", title: "Основное" },
  { path: "/settings/currency", title: "Валюта и курсы" },
  { path: "/settings/branding", title: "Брендирование" },
  { path: "/settings/ratelimits", title: "Rate limiting" },
  { path: "/settings/raw", title: "Raw settings" },
  { path: "/settings/roles", title: "Роли" },
]

/**
 * Построить цепочку крошек для `pathname`: все записи реестра, чей `path`
 * совпадает целым сегментом с началом `pathname`, отсортированные от
 * короткого к длинному (корень → раздел → подраздел).
 *
 * Сравнение по целым сегментам (не просто `startsWith`) — иначе `/settings`
 * ошибочно совпал бы с `/settingsx`.
 */
export function matchRouteChain(pathname: string): RouteMeta[] {
  const segments = pathname.split("/").filter(Boolean)
  const chain: RouteMeta[] = []
  for (const meta of routeMeta) {
    if (meta.path === "/") {
      if (pathname === "/") chain.push(meta)
      continue
    }
    const metaSegments = meta.path.split("/").filter(Boolean)
    const matches = metaSegments.every((seg, i) => segments[i] === seg)
    if (matches) chain.push(meta)
  }
  return chain.sort((a, b) => a.path.length - b.path.length)
}
