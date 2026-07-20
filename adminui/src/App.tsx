import { BrowserRouter, Route, Routes } from "react-router-dom"

import { DashboardLayout } from "@/components/layout/DashboardLayout.tsx"
import { LoginPage } from "@/pages/login/LoginPage"
import { DashboardPage } from "@/pages/dashboard/DashboardPage"
import { UsersPage } from "@/pages/users/UsersPage"
import { ProtectedRoute } from "@/routes/ProtectedRoute"
import { ProfileDialogProvider } from "@/hooks/use-profile-dialog"
import { ProfileDialogHost } from "@/components/profile/ProfileDialogHost"

export function App() {
  return (
    <ProfileDialogProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<ProtectedRoute />}>
            <Route element={<DashboardLayout />}>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/users" element={<UsersPage />} />
            </Route>
          </Route>
        </Routes>
      </BrowserRouter>
      <ProfileDialogHost />
    </ProfileDialogProvider>
  )
}

export default App
