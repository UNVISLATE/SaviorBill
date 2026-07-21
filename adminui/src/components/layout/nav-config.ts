import {
  FileClock,
  Gauge,
  Settings,
  ShieldCheck,
  Users,
  MonitorCog,
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
  { title: "Настройки", url: "/settings", icon: Settings, perm: "settings.read" }
]
