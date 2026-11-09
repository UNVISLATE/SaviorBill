import { useMemo } from "react"
import { Navigate, Route, Routes } from "react-router-dom"
import {
  Ban,
  Coins,
  Film,
  KeyRound,
  Lock,
  Mail,
  Palette,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
} from "lucide-react"

import { useAuth } from "@/hooks/use-auth"
import { SectionTabs } from "@/components/layout/SectionTabs"
import { SettingsGeneral } from "./SettingsGeneral"
import { SettingsBranding } from "./SettingsBranding"
import { CurrencySettings } from "./CurrencySettings"
import { SmtpSettings } from "./SmtpSettings"
import { SecuritySettings } from "./SecuritySettings"
import { RawSettingsEditor } from "./RawSettingsEditor"
import { BannedDomainsSettings } from "./BannedDomainsSettings"
import { AppTokensSettings } from "./AppTokensSettings"
import { MediaSettingsPage } from "./MediaSettingsPage"
import { RolesPage } from "@/pages/roles/RolesPage"
import { PluginsSettingsPage } from "./PluginsSettingsPage"
import { Plug } from "lucide-react"

interface SettingsTabDef {
  path: string
  title: string
  to: string
  icon: React.ReactNode
  element: React.ReactNode
  group?: string
  hint?: string
  anyPerm?: string[]
}

const SETTINGS_TABS: SettingsTabDef[] = [
  // Группа 1: Общее
  {
    path: "general",
    title: "Основное",
    to: "/settings/general",
    icon: <Settings2 className="size-4" />,
    element: <SettingsGeneral />,
    group: "Общее",
    anyPerm: ["settings.raw.read", "settings.read", "settings.edit", "settings.raw.edit"],
  },
  {
    path: "branding",
    title: "Бренд",
    to: "/settings/branding",
    icon: <Palette className="size-4" />,
    element: <SettingsBranding />,
    group: "Общее",
    anyPerm: ["settings.raw.edit", "settings.raw.read", "branding"],
  },
  {
    path: "currency",
    title: "Валюта",
    to: "/settings/currency",
    icon: <Coins className="size-4" />,
    element: <CurrencySettings />,
    group: "Общее",
    anyPerm: ["settings.raw.read", "settings.raw.edit"],
  },
  {
    path: "media",
    title: "Медиа",
    to: "/settings/media",
    icon: <Film className="size-4" />,
    element: <MediaSettingsPage />,
    group: "Общее",
    anyPerm: ["settings.raw.read", "settings.raw.edit", "media.read", "media"],
  },
  {
    path: "smtp",
    title: "Почта",
    to: "/settings/smtp",
    icon: <Mail className="size-4" />,
    element: <SmtpSettings />,
    group: "Общее",
    anyPerm: ["settings.read", "settings.edit", "settings.raw.read"],
  },

  // Группа 2: Доступ
  {
    path: "roles",
    title: "Роли",
    to: "/settings/roles",
    icon: <ShieldCheck className="size-4" />,
    element: <RolesPage />,
    group: "Доступ",
    anyPerm: ["roles.read", "roles"],
  },
  {
    path: "app-tokens",
    title: "API Токены",
    to: "/settings/app-tokens",
    icon: <KeyRound className="size-4" />,
    element: <AppTokensSettings />,
    group: "Доступ",
    anyPerm: [
      "apptokens",
      "apptokens.read",
      "apptokens.create",
      "apptokens.revoke",
      "apptokens.delete",
      "apptokens.manage_any",
    ],
  },

  // Группа 3: Безопасность
  {
    path: "security",
    title: "Безопасность",
    to: "/settings/security",
    icon: <Lock className="size-4" />,
    element: <SecuritySettings />,
    group: "Безопасность",
    anyPerm: [
      "settings.security.read",
      "settings.security.edit",
      "settings.ratelimits.read",
      "settings.ratelimits.edit",
      "settings.ratelimits",
      "settings.raw.read",
    ],
  },
  {
    path: "domains",
    title: "Заблок. почта",
    to: "/settings/domains",
    icon: <Ban className="size-4" />,
    element: <BannedDomainsSettings />,
    group: "Безопасность",
    anyPerm: [
      "settings.email_domains.read",
      "settings.email_domains.edit",
      "settings.email_domains",
      "settings.raw.read",
    ],
  },

  // Группа 4: Другое
  {
    path: "plugins",
    title: "Плагины",
    to: "/settings/plugins",
    icon: <Plug className="size-4" />,
    element: <PluginsSettingsPage />,
    group: "Другое",
    anyPerm: ["plugins.manage", "settings.read", "settings.edit", "settings.raw.read"],
  },
  {
    path: "raw",
    title: "RAW Settings",
    to: "/settings/raw",
    icon: <SlidersHorizontal className="size-4" />,
    element: <RawSettingsEditor />,
    group: "Другое",
    anyPerm: ["settings.raw.read", "settings.raw.edit"],
  },
]

/** /settings — раздел настроек с группированной структурой. */
export function SettingsPage() {
  const { can } = useAuth()

  const visibleTabs = useMemo(() => {
    return SETTINGS_TABS.filter((tab) => {
      if (!tab.anyPerm || tab.anyPerm.length === 0) return true
      return tab.anyPerm.some((p) => can(p))
    })
  }, [can])

  const tabItems = useMemo(() => {
    return visibleTabs.map((tab) => ({
      title: tab.title,
      to: tab.to,
      icon: tab.icon,
      group: tab.group,
      hint: tab.hint,
    }))
  }, [visibleTabs])

  if (visibleTabs.length === 0) {
    return (
      <div className="space-y-4">
        <h1 className="text-xl font-semibold">Настройки</h1>
        <div className="rounded-lg border border-dashed p-8 text-center text-muted-foreground">
          Недостаточно прав для просмотра раздела настроек.
        </div>
      </div>
    )
  }

  const defaultTo = visibleTabs[0].to

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Настройки</h1>
      <SectionTabs items={tabItems}>
        <Routes>
          <Route index element={<Navigate to={defaultTo} replace />} />
          {visibleTabs.map((tab) => (
            <Route key={tab.path} path={tab.path} element={tab.element} />
          ))}
          {/* Устаревшие алиасы и редиректы */}
          <Route path="about" element={<Navigate to="/about" replace />} />
          <Route path="ratelimits" element={<Navigate to="/settings/security" replace />} />
          <Route path="adminui" element={<Navigate to="/settings/media" replace />} />
          <Route path="payment-providers" element={<Navigate to="/providers/payment" replace />} />
          <Route path="*" element={<Navigate to={defaultTo} replace />} />
        </Routes>
      </SectionTabs>
    </div>
  )
}
