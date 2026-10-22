import { Navigate, Route, Routes } from "react-router-dom"
import { Ban, Coins, Film, Gauge, Info, Mail, Palette, Settings2, ShieldCheck, SlidersHorizontal } from "lucide-react"

import { SectionTabs } from "@/components/layout/SectionTabs"
import { SettingsGeneral } from "./SettingsGeneral"
import { CurrencySettings } from "./CurrencySettings"
import { SettingsBranding } from "./SettingsBranding"
import { RateLimitSettings } from "./RateLimitSettings"
import { RawSettingsEditor } from "./RawSettingsEditor"
import { BannedDomainsSettings } from "./BannedDomainsSettings"
import { RolesPage } from "@/pages/roles/RolesPage"
import { AboutPage } from "./AboutPage"
import { SmtpSettings } from "./SmtpSettings"
import { MediaSettingsPage } from "./MediaSettingsPage"

/** /settings — раздел с редко изменяемыми системными настройками, поэтому
 * с собственной под-навигацией, а не в общем сайдбаре (см.
 * IMPLEMENTATION_PLAN.md §4). */
export function SettingsPage() {
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Настройки</h1>
      <SectionTabs
        items={[
          { title: "Основное", to: "/settings/general", icon: <Settings2 className="size-4" /> },
          { title: "Медиа", to: "/settings/media", icon: <Film className="size-4" /> },
          { title: "Валюта и курсы", to: "/settings/currency", icon: <Coins className="size-4" /> },
          { title: "Брендирование", to: "/settings/branding", icon: <Palette className="size-4" /> },
          { title: "Почта (SMTP)", to: "/settings/smtp", icon: <Mail className="size-4" /> },
          { title: "Rate limiting", to: "/settings/ratelimits", icon: <Gauge className="size-4" /> },
          { title: "Заблок. домены", to: "/settings/domains", icon: <Ban className="size-4" /> },
          { title: "Raw settings", to: "/settings/raw", icon: <SlidersHorizontal className="size-4" /> },
          { title: "Роли", to: "/settings/roles", icon: <ShieldCheck className="size-4" /> },
          { title: "О системе", to: "/settings/about", icon: <Info className="size-4" /> },
        ]}
      >
        <Routes>
          <Route index element={<Navigate to="general" replace />} />
          <Route path="general" element={<SettingsGeneral />} />
          <Route path="media" element={<MediaSettingsPage />} />
          <Route path="adminui" element={<Navigate to="/settings/media" replace />} />
          <Route path="currency" element={<CurrencySettings />} />
          <Route path="branding" element={<SettingsBranding />} />
          <Route path="smtp" element={<SmtpSettings />} />
          <Route path="ratelimits" element={<RateLimitSettings />} />
          <Route path="domains" element={<BannedDomainsSettings />} />
          <Route path="payment-providers" element={<Navigate to="/providers/payment" replace />} />
          <Route path="raw" element={<RawSettingsEditor />} />
          <Route path="roles" element={<RolesPage />} />
          <Route path="about" element={<AboutPage />} />
        </Routes>
      </SectionTabs>
    </div>
  )
}
