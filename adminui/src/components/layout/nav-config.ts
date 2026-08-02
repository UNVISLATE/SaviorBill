import {
  FileClock,
  FolderTree,
  Gauge,
  KeyRound,
  Mail,
  Package,
  Receipt,
  ShoppingCart,
  Settings,
  Ticket,
  Users,
  MonitorCog,
  ScrollText,
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
    items: [
        { title: "Дашборд", url: "/", icon: Gauge }
    ],
  },
  {
    title: "Пользователи",
    items: [
        { title: "Пользователи", url: "/users", icon: Users, perm: "users.read" }
    ],
  },
  {
    title: "Каталог",
    items: [
        { title: "Каталоги", url: "/catalog", icon: FolderTree, perm: "catalogs.read" },
        { title: "Услуги", url: "/services", icon: Package, perm: "services.read" },
    ],
  },
  {
    title: "Продажи",
    items: [
        { title: "Заказы", url: "/orders", icon: ShoppingCart, perm: "orders.read" },
        { title: "Платежи", url: "/purchases", icon: Receipt, perm: "purchases.read" },
        { title: "Промокоды", url: "/promo", icon: Ticket, perm: "promo.catalogs.read" },
    ],
  },
  {
    title: "Автоматизация",
    items: [
        { title: "Скрипты", url: "/lua", icon: ScrollText, perm: "lua.read" },
        { title: "Триггеры", url: "/triggers", icon: Zap, perm: "triggers.read" },
        { title: "Email-шаблоны", url: "/email-templates", icon: Mail, perm: "email.read" },
        { title: "OAuth-вход", url: "/oauth", icon: KeyRound, perm: "oauth.read" },
    ]
  }
]

/**
 * Нижний блок сайдбара (над карточкой пользователя) — системные разделы,
 * не относящиеся к повседневной работе с каталогом/пользователями, вынесены
 * из общих групп навигации, как "Settings/Get Help/Search" в референсе.
 */
export const footerNavItems: NavItem[] = [
  { title: "Аудит", url: "/audit", icon: FileClock, perm: "audit.read" },
  { title: "Система", url: "/system", icon: MonitorCog, perm: "system.stats.read" },
  { title: "Настройки", url: "/settings", icon: Settings, perm: "settings.raw.read" }
]
