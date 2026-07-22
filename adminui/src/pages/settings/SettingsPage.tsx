import { Navigate, Route, Routes } from "react-router-dom"
import { Gauge, ShieldCheck, SlidersHorizontal } from "lucide-react"

import { SectionTabs } from "@/components/layout/SectionTabs"
import { RateLimitSettings } from "./RateLimitSettings"
import { RawSettingsEditor } from "./RawSettingsEditor"
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
          { title: "Rate limiting", to: "/settings/ratelimits", icon: <Gauge className="size-4" /> },
          { title: "Raw settings", to: "/settings/raw", icon: <SlidersHorizontal className="size-4" /> },
          { title: "Роли", to: "/settings/roles", icon: <ShieldCheck className="size-4" /> },
        ]}
      >
        <Routes>
          <Route index element={<Navigate to="ratelimits" replace />} />
          <Route path="ratelimits" element={<RateLimitSettings />} />
          <Route path="raw" element={<RawSettingsEditor />} />
          <Route path="roles" element={<RolesPage />} />
        </Routes>
      </SectionTabs>
    </div>
  )
}
