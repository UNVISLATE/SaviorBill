import {
  BadgePercent,
  FileClock,
  Gauge,
  KeySquare,
  LayoutTemplate,
  Link2,
  Mail,
  Package,
  ScrollText,
  Settings,
  ShieldCheck,
  ShoppingCart,
  Users,
  Zap,
} from "lucide-react"

/**
 * Разделы навигации админки. `perm` — dot-path право (см. `lib/rbac.ts`),
 * пункт скрывается, если у текущей роли нет права (гейт только для UI —
 * реальная проверка всегда на backend через `require_perm`).
 */
export interface NavItem {
  title: string
  url: string
  icon: typeof Gauge
  perm?: string
}

export interface NavGroup {
  title: string
  items: NavItem[]
}

export const navGroups: NavGroup[] = [
  {
    title: "Обзор",
    items: [{ title: "Дашборд", url: "/", icon: Gauge }],
  },
  {
    title: "Пользователи",
    items: [
      { title: "Пользователи", url: "/users", icon: Users, perm: "users.read" },
      { title: "Роли", url: "/roles", icon: ShieldCheck, perm: "roles.read" },
    ],
  },
  {
    title: "Каталог и продажи",
    items: [
      { title: "Каталог услуг", url: "/catalogs", icon: LayoutTemplate, perm: "catalogs.read" },
      { title: "Товары/услуги", url: "/services", icon: Package, perm: "services.read" },
      { title: "Ключи услуг", url: "/service-keys", icon: KeySquare, perm: "services.read" },
      { title: "Заказы", url: "/orders", icon: ShoppingCart, perm: "orders.read" },
      { title: "Покупки", url: "/purchases", icon: ShoppingCart, perm: "purchases.read" },
      { title: "Промокоды", url: "/promo", icon: BadgePercent, perm: "promo.read" },
    ],
  },
  {
    title: "Автоматизация",
    items: [
      { title: "Lua-скрипты", url: "/lua", icon: ScrollText, perm: "lua.read" },
      { title: "Триггеры", url: "/triggers", icon: Zap, perm: "triggers.read" },
      { title: "OAuth-провайдеры", url: "/oauth", icon: Link2, perm: "oauth.read" },
      { title: "Email-шаблоны", url: "/email", icon: Mail, perm: "email.read" },
    ],
  },
  {
    title: "Система",
    items: [
      { title: "Настройки", url: "/settings", icon: Settings, perm: "settings.read" },
      { title: "Аудит", url: "/audit", icon: FileClock, perm: "audit.read" },
    ],
  },
]
