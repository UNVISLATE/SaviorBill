import { lazy, Suspense } from "react"
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"
import { Loader2 } from "lucide-react"

import { DashboardLayout } from "@/components/layout/DashboardLayout.tsx"
import { BrandingHead } from "@/components/layout/BrandingHead"
import { LoginPage } from "@/pages/login/LoginPage"
import { ProtectedRoute } from "@/routes/ProtectedRoute"
import { NotFoundPage } from "@/pages/errors/NotFoundPage"
import { useAuth } from "@/hooks/use-auth"
import { ProfileDialogProvider } from "@/hooks/use-profile-dialog"
import { ProfileDialogHost } from "@/components/profile/ProfileDialogHost"
import { TooltipProvider } from "@/components/shadsnui/tooltip"
import { Toaster } from "@/components/shadsnui/sonner"
import { ErrorBoundary } from "@/components/common/ErrorBoundary"

const DashboardPage = lazy(() => import("@/pages/dashboard/DashboardPage").then((m) => ({ default: m.DashboardPage })))
const UsersPage = lazy(() => import("@/pages/users/UsersPage").then((m) => ({ default: m.UsersPage })))
const SystemPage = lazy(() => import("@/pages/system/SystemPage").then((m) => ({ default: m.SystemPage })))
const SettingsPage = lazy(() => import("@/pages/settings/SettingsPage").then((m) => ({ default: m.SettingsPage })))
const LuaScriptsPage = lazy(() => import("@/pages/lua/LuaScriptsPage").then((m) => ({ default: m.LuaScriptsPage })))
const LuaManifestPage = lazy(() => import("@/pages/lua/LuaManifestPage").then((m) => ({ default: m.LuaManifestPage })))
const CatalogsPage = lazy(() => import("@/pages/catalog/CatalogsPage").then((m) => ({ default: m.CatalogsPage })))
const ServicesPage = lazy(() => import("@/pages/catalog/ServicesPage").then((m) => ({ default: m.ServicesPage })))
const ServiceEditorPage = lazy(() => import("@/pages/catalog/ServiceEditorPage").then((m) => ({ default: m.ServiceEditorPage })))
const ServiceInstructionPage = lazy(() => import("@/pages/catalog/ServiceInstructionPage").then((m) => ({ default: m.ServiceInstructionPage })))
const ServiceKeysPage = lazy(() => import("@/pages/catalog/ServiceKeysPage").then((m) => ({ default: m.ServiceKeysPage })))
const MediaLibraryPage = lazy(() => import("@/pages/media/MediaLibraryPage").then((m) => ({ default: m.MediaLibraryPage })))
const OrdersPage = lazy(() => import("@/pages/orders/OrdersPage").then((m) => ({ default: m.OrdersPage })))
const PurchasesPage = lazy(() => import("@/pages/purchases/PurchasesPage").then((m) => ({ default: m.PurchasesPage })))
const PromoPage = lazy(() => import("@/pages/promo/PromoPage").then((m) => ({ default: m.PromoPage })))
const TriggersPage = lazy(() => import("@/pages/triggers/TriggersPage").then((m) => ({ default: m.TriggersPage })))
const EmailTemplatesPage = lazy(() => import("@/pages/email/EmailTemplatesPage").then((m) => ({ default: m.EmailTemplatesPage })))
const OAuthProvidersPage = lazy(() => import("@/pages/oauth/OAuthProvidersPage").then((m) => ({ default: m.OAuthProvidersPage })))
const PaymentProvidersPage = lazy(() => import("@/pages/providers/PaymentProvidersPage").then((m) => ({ default: m.PaymentProvidersPage })))
const PluginHostPage = lazy(() => import("@/pages/plugins/PluginHostPage").then((m) => ({ default: m.PluginHostPage })))
const AboutPage = lazy(() => import("@/pages/settings/AboutPage").then((m) => ({ default: m.AboutPage })))

function ProvidersRedirect() {
  const { can } = useAuth()
  if (can("purchases.providers.read") || can("purchases.providers")) {
    return <Navigate to="/providers/payment" replace />
  }
  if (can("oauth.read") || can("oauth")) {
    return <Navigate to="/providers/oauth" replace />
  }
  return <Navigate to="/" replace />
}

export function App() {
  return (
    <ErrorBoundary>
      <TooltipProvider>
        <ProfileDialogProvider>
      <BrandingHead />
      <BrowserRouter>
        <Suspense
          fallback={
            <div className="flex h-screen items-center justify-center text-xs text-muted-foreground gap-2">
              <Loader2 className="size-4 animate-spin text-primary" /> Загрузка...
            </div>
          }
        >
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route element={<ProtectedRoute />}>
              <Route element={<DashboardLayout />}>
                <Route path="/" element={<DashboardPage />} />
                <Route path="/users" element={<UsersPage />} />
                <Route path="/users/:userId" element={<UsersPage />} />
                <Route path="/audit" element={<Navigate to="/system/audit" replace />} />
                <Route path="/about" element={<AboutPage />} />
                <Route path="/system/*" element={<SystemPage />} />
                <Route path="/settings/*" element={<SettingsPage />} />
                <Route path="/lua" element={<LuaScriptsPage />} />
                <Route path="/lua/:scriptId" element={<LuaScriptsPage />} />
                <Route path="/lua/:scriptId/manifest" element={<LuaManifestPage />} />
                <Route path="/plugins/:slug/*" element={<PluginHostPage />} />
                <Route path="/plugins/:slug" element={<PluginHostPage />} />
                <Route path="/catalog" element={<CatalogsPage />} />
                <Route path="/services" element={<ServicesPage />} />
                <Route path="/services/new" element={<ServiceEditorPage />} />
                <Route path="/services/:id" element={<ServiceEditorPage />} />
                <Route path="/services/:id/instruction" element={<ServiceInstructionPage />} />
                <Route path="/service-keys" element={<ServiceKeysPage />} />
                <Route path="/media" element={<MediaLibraryPage />} />
                <Route path="/orders" element={<OrdersPage />} />
                <Route path="/purchases" element={<PurchasesPage />} />
                <Route path="/promo" element={<PromoPage />} />
                <Route path="/triggers" element={<TriggersPage />} />
                <Route path="/emailtemplate" element={<EmailTemplatesPage />} />
                <Route path="/emailtemplate/:templateId" element={<EmailTemplatesPage />} />
                <Route path="/email-templates" element={<Navigate to="/emailtemplate" replace />} />
                <Route path="/providers" element={<ProvidersRedirect />} />
                <Route path="/providers/payment" element={<PaymentProvidersPage />} />
                <Route path="/providers/oauth" element={<OAuthProvidersPage />} />
                <Route path="/oauth" element={<Navigate to="/providers/oauth" replace />} />
                <Route path="/payment-providers" element={<ProvidersRedirect />} />
              </Route>
            </Route>
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </Suspense>
      </BrowserRouter>
      <ProfileDialogHost />
      <Toaster position="top-center" />
    </ProfileDialogProvider>
    </TooltipProvider>
    </ErrorBoundary>
  )
}

export default App
