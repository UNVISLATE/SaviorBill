import { Navigate, Route, Routes } from "react-router-dom"
import { Ban, Coins, CreditCard, Gauge, Palette, Settings2, ShieldCheck, SlidersHorizontal } from "lucide-react"

import { SectionTabs } from "@/components/layout/SectionTabs"
import { SettingsGeneral } from "./SettingsGeneral"
import { CurrencySettings } from "./CurrencySettings"
import { SettingsBranding } from "./SettingsBranding"
import { RateLimitSettings } from "./RateLimitSettings"
import { RawSettingsEditor } from "./RawSettingsEditor"
import { BannedDomainsSettings } from "./BannedDomainsSettings"
import { PaymentProvidersSettings } from "./PaymentProvidersSettings"
import { RolesPage } from "@/pages/roles/RolesPage"

/** /settings — раздел с редко изменяемыми системными настройками, поэтому
 * с собственной под-навигацией, а не в общем сайдбаре (см.
 * IMPLEMENTATION_PLAN.md §4). Роли живут здесь же, а не на верхнем уровне —
 * их редактируют нечасто. */
export function SettingsPage() {
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Настройки</h1>
      <SectionTabs
        items={[
          { title: "Основное", to: "/settings/general", icon: <Settings2 className="size-4" /> },
          { title: "Валюта и курсы", to: "/settings/currency", icon: <Coins className="size-4" /> },
          { title: "Брендирование", to: "/settings/branding", icon: <Palette className="size-4" /> },
          { title: "Rate limiting", to: "/settings/ratelimits", icon: <Gauge className="size-4" /> },
          { title: "Заблок. домены", to: "/settings/domains", icon: <Ban className="size-4" /> },
          { title: "Платёжные провайдеры", to: "/settings/payment-providers", icon: <CreditCard className="size-4" /> },
          { title: "Raw settings", to: "/settings/raw", icon: <SlidersHorizontal className="size-4" /> },
          { title: "Роли", to: "/settings/roles", icon: <ShieldCheck className="size-4" /> },
        ]}
      >
        <Routes>
          <Route index element={<Navigate to="general" replace />} />
          <Route path="general" element={<SettingsGeneral />} />
          <Route path="currency" element={<CurrencySettings />} />
          <Route path="branding" element={<SettingsBranding />} />
          <Route path="ratelimits" element={<RateLimitSettings />} />
          <Route path="domains" element={<BannedDomainsSettings />} />
          <Route path="payment-providers" element={<PaymentProvidersSettings />} />
          <Route path="raw" element={<RawSettingsEditor />} />
          <Route path="roles" element={<RolesPage />} />
        </Routes>
      </SectionTabs>
    </div>
  )
}

