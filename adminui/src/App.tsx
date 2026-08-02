import { BrowserRouter, Route, Routes } from "react-router-dom"

import { DashboardLayout } from "@/components/layout/DashboardLayout.tsx"
import { BrandingHead } from "@/components/layout/BrandingHead"
import { LoginPage } from "@/pages/login/LoginPage"
import { DashboardPage } from "@/pages/dashboard/DashboardPage"
import { UsersPage } from "@/pages/users/UsersPage"
import { AuditPage } from "@/pages/audit/AuditPage"
import { SystemPage } from "@/pages/system/SystemPage"
import { SettingsPage } from "@/pages/settings/SettingsPage"
import { LuaScriptsPage } from "@/pages/lua/LuaScriptsPage"
import { CatalogsPage } from "@/pages/catalog/CatalogsPage"
import { ServicesPage } from "@/pages/catalog/ServicesPage"
import { ServiceDetailPage } from "@/pages/catalog/ServiceDetailPage"
import { OrdersPage } from "@/pages/orders/OrdersPage"
import { PurchasesPage } from "@/pages/purchases/PurchasesPage"
import { PromoPage } from "@/pages/promo/PromoPage"
import { TriggersPage } from "@/pages/triggers/TriggersPage"
import { EmailTemplatesPage } from "@/pages/email/EmailTemplatesPage"
import { OAuthProvidersPage } from "@/pages/oauth/OAuthProvidersPage"
import { ProtectedRoute } from "@/routes/ProtectedRoute"
import { ProfileDialogProvider } from "@/hooks/use-profile-dialog"
import { ProfileDialogHost } from "@/components/profile/ProfileDialogHost"
import { TooltipProvider } from "@/components/shadsnui/tooltip"
import { Toaster } from "@/components/shadsnui/sonner"

export function App() {
  return (
    <TooltipProvider>
    <ProfileDialogProvider>
      <BrandingHead />
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<ProtectedRoute />}>
            <Route element={<DashboardLayout />}>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/users" element={<UsersPage />} />
              <Route path="/audit" element={<AuditPage />} />
              <Route path="/system/*" element={<SystemPage />} />
              <Route path="/settings/*" element={<SettingsPage />} />
              <Route path="/lua" element={<LuaScriptsPage />} />
              <Route path="/lua/:scriptId" element={<LuaScriptsPage />} />
              <Route path="/catalog" element={<CatalogsPage />} />
              <Route path="/services" element={<ServicesPage />} />
              <Route path="/services/:id" element={<ServiceDetailPage />} />
              <Route path="/orders" element={<OrdersPage />} />
              <Route path="/purchases" element={<PurchasesPage />} />
              <Route path="/promo" element={<PromoPage />} />
              <Route path="/triggers" element={<TriggersPage />} />
              <Route path="/email-templates" element={<EmailTemplatesPage />} />
              <Route path="/oauth" element={<OAuthProvidersPage />} />
            </Route>
          </Route>
        </Routes>
      </BrowserRouter>
      <ProfileDialogHost />
      <Toaster position="top-center" />
    </ProfileDialogProvider>
    </TooltipProvider>
  )
}

export default App
