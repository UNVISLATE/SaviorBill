import { useMemo } from "react"
import { Navigate, Route, Routes } from "react-router-dom"
import {
  Ban,
  Coins,
  Film,
  Info,
  KeyRound,
  Mail,
  Palette,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
} from "lucide-react"

import { useAuth } from "@/hooks/use-auth"
import { SectionTabs } from "@/components/layout/SectionTabs"
import { SettingsGeneral } from "./SettingsGeneral"
import { CurrencySettings } from "./CurrencySettings"
import { SettingsBranding } from "./SettingsBranding"
import { SecuritySettings } from "./SecuritySettings"
import { RawSettingsEditor } from "./RawSettingsEditor"
import { BannedDomainsSettings } from "./BannedDomainsSettings"
import { RolesPage } from "@/pages/roles/RolesPage"
import { AboutPage } from "./AboutPage"
import { SmtpSettings } from "./SmtpSettings"
import { MediaSettingsPage } from "./MediaSettingsPage"
import { AppTokensSettings } from "./AppTokensSettings"

interface SettingsTabDef {
  path: string
  title: string
  to: string
  icon: React.ReactNode
  element: React.ReactNode
  anyPerm?: string[]
}

const SETTINGS_TABS: SettingsTabDef[] = [
  {
    path: "general",
    title: "Основное",
    to: "/settings/general",
    icon: <Settings2 className="size-4" />,
    element: <SettingsGeneral />,
    anyPerm: ["settings.raw.read", "settings.read", "settings.edit", "settings.raw.edit"],
  },
  {
    path: "app-tokens",
    title: "Токены API",
    to: "/settings/app-tokens",
    icon: <KeyRound className="size-4" />,
    element: <AppTokensSettings />,
    anyPerm: [
      "apptokens",
      "apptokens.read",
      "apptokens.create",
      "apptokens.revoke",
      "apptokens.delete",
      "apptokens.manage_any",
    ],
  },
  {
    path: "media",
    title: "Медиа",
    to: "/settings/media",
    icon: <Film className="size-4" />,
    element: <MediaSettingsPage />,
    anyPerm: ["settings.raw.read", "settings.raw.edit", "media.read", "media"],
  },
  {
    path: "currency",
    title: "Валюта и курсы",
    to: "/settings/currency",
    icon: <Coins className="size-4" />,
    element: <CurrencySettings />,
    anyPerm: ["settings.raw.read", "settings.raw.edit"],
  },
  {
    path: "branding",
    title: "Брендирование",
    to: "/settings/branding",
    icon: <Palette className="size-4" />,
    element: <SettingsBranding />,
    anyPerm: ["settings.raw.edit", "settings.raw.read", "branding"],
  },
  {
    path: "smtp",
    title: "Почта (SMTP)",
    to: "/settings/smtp",
    icon: <Mail className="size-4" />,
    element: <SmtpSettings />,
    anyPerm: ["settings.read", "settings.edit", "settings.raw.read"],
  },
  {
    path: "security",
    title: "Безопасность",
    to: "/settings/security",
    icon: <ShieldCheck className="size-4" />,
    element: <SecuritySettings />,
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
    title: "Заблок. домены",
    to: "/settings/domains",
    icon: <Ban className="size-4" />,
    element: <BannedDomainsSettings />,
    anyPerm: [
      "settings.email_domains.read",
      "settings.email_domains.edit",
      "settings.email_domains",
      "settings.raw.read",
    ],
  },
  {
    path: "raw",
    title: "Raw settings",
    to: "/settings/raw",
    icon: <SlidersHorizontal className="size-4" />,
    element: <RawSettingsEditor />,
    anyPerm: ["settings.raw.read", "settings.raw.edit"],
  },
  {
    path: "roles",
    title: "Роли",
    to: "/settings/roles",
    icon: <ShieldCheck className="size-4" />,
    element: <RolesPage />,
    anyPerm: ["roles.read", "roles"],
  },
  {
    path: "about",
    title: "О системе",
    to: "/settings/about",
    icon: <Info className="size-4" />,
    element: <AboutPage />,
  },
]

/** /settings — раздел с редко изменяемыми системными настройками, поэтому
 * с собственной под-навигацией, а не в общем сайдбаре. Вкладки фильтруются
 * строго по правам пользователя, с автоматическим редиректом на первую доступную. */
export function SettingsPage() {
  const { can } = useAuth()

  const visibleTabs = useMemo(() => {
    return SETTINGS_TABS.filter((tab) => {
      if (!tab.anyPerm || tab.anyPerm.length === 0) return true
      return tab.anyPerm.some((p) => can(p))
    })
  }, [can])

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
      <SectionTabs items={visibleTabs}>
        <Routes>
          <Route index element={<Navigate to={defaultTo} replace />} />
          {visibleTabs.map((tab) => (
            <Route key={tab.path} path={tab.path} element={tab.element} />
          ))}
          {/* Устаревшие алиасы */}
          <Route path="ratelimits" element={<Navigate to="/settings/security" replace />} />
          <Route path="adminui" element={<Navigate to="/settings/media" replace />} />
          <Route path="payment-providers" element={<Navigate to="/providers/payment" replace />} />
          {/* Защита: при попытке открыть недоступный подраздел редиректим на первый доступный */}
          <Route path="*" element={<Navigate to={defaultTo} replace />} />
        </Routes>
      </SectionTabs>
    </div>
  )
}
