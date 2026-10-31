import {
  CreditCard,
  FileClock,
  FolderTree,
  Gauge,
  Images,
  KeyRound,
  Mail,
  Package,
  Plug,
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
 * `anyPerm` — набор прав, хотя бы одно из которых открывает доступ.
 * Пункт скрывается, если у текущей роли нет ни одного требуемого права.
 */
export interface NavItem {
  title: string
  url: string
  icon: typeof Gauge
  perm?: string
  anyPerm?: string[]
}

export function isNavItemVisible(can: (p: string) => boolean, item: NavItem): boolean {
  if (item.anyPerm && item.anyPerm.length > 0) {
    return item.anyPerm.some((p) => can(p))
  }
  if (item.perm) {
    return can(item.perm)
  }
  return true
}

export interface NavGroup {
  title: string
  /** Иконка категории — показывается на сайдбаре в свёрнутом (icon-rail) виде. */
  icon: typeof Gauge
  items: NavItem[]
}

export const navGroups: NavGroup[] = [
  {
    title: "Обзор",
    icon: Gauge,
    items: [
      { title: "Дашборд", url: "/", icon: Gauge },
    ],
  },
  {
    title: "Пользователи",
    icon: Users,
    items: [
      {
        title: "Пользователи",
        url: "/users",
        icon: Users,
        anyPerm: ["users.read", "users", "admin.user.create", "admin.user.edit", "admin.user.delete"],
      },
      { title: "Заказы", url: "/orders", icon: ShoppingCart, anyPerm: ["orders.read", "orders"] },
      { title: "Платежи", url: "/purchases", icon: Receipt, anyPerm: ["purchases.read", "purchases"] },
      { title: "Промокоды", url: "/promo", icon: Ticket, anyPerm: ["promo.catalogs.read", "promo.codes.read", "promo"] },
    ],
  },
  {
    title: "Каталог",
    icon: FolderTree,
    items: [
      { title: "Каталоги", url: "/catalog", icon: FolderTree, anyPerm: ["catalogs.read", "catalogs"] },
      { title: "Услуги", url: "/services", icon: Package, anyPerm: ["services.read", "services"] },
      { title: "Ключи", url: "/service-keys", icon: KeyRound, anyPerm: ["services.keys.read", "ownersec.servicekeys.read", "services.keys"] },
      { title: "Медиатека", url: "/media", icon: Images, anyPerm: ["media.read", "media"] },
    ],
  },
  {
    title: "Автоматизация",
    icon: Zap,
    items: [
      { title: "Скрипты", url: "/lua", icon: ScrollText, anyPerm: ["lua.read", "lua"] },
      { title: "Триггеры", url: "/triggers", icon: Zap, anyPerm: ["triggers.read", "triggers"] },
      { title: "Email-шаблоны", url: "/emailtemplate", icon: Mail, anyPerm: ["email.read", "email"] },
    ],
  },
  {
    title: "Провайдеры",
    icon: Plug,
    items: [
      { title: "Платежи", url: "/providers/payment", icon: CreditCard, anyPerm: ["purchases.providers.read", "purchases.providers"] },
      { title: "OAuth", url: "/providers/oauth", icon: KeyRound, anyPerm: ["oauth.read", "oauth"] },
    ],
  },
]

/**
 * Нижний блок сайдбара (над карточкой пользователя) — системные разделы,
 * не относящиеся к повседневной работе с каталогом/пользователями, вынесены
 * из общих групп навигации, как "Settings/Get Help/Search" в референсе.
 */
export const footerNavItems: NavItem[] = [
  { title: "Аудит", url: "/audit", icon: FileClock, anyPerm: ["audit.read", "audit"] },
  {
    title: "Система",
    url: "/system",
    icon: MonitorCog,
    anyPerm: [
      "system.stats.read",
      "system.tasks.summary.read",
      "system.tasks.tail.read",
      "system.tasks.dlq.read",
      "system",
    ],
  },
  {
    title: "Настройки",
    url: "/settings",
    icon: Settings,
    anyPerm: [
      "settings",
      "apptokens",
      "branding",
      "roles",
      "settings.raw.read",
      "settings.read",
      "settings.edit",
      "settings.raw.edit",
      "settings.ratelimits.read",
      "settings.email_domains.read",
      "apptokens.read",
      "roles.read",
    ],
  },
]
