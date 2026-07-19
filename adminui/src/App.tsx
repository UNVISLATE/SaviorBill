import { BrowserRouter, Route, Routes } from "react-router-dom"

import { AppLayout } from "@/components/layout/AppLayout"
import { LoginPage } from "@/pages/login/LoginPage"
import { DashboardPage } from "@/pages/dashboard/DashboardPage"
import { UsersPage } from "@/pages/users/UsersPage"
import { ProtectedRoute } from "@/routes/ProtectedRoute"

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<ProtectedRoute />}>
          <Route element={<AppLayout />}>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/users" element={<UsersPage />} />
            {/* Остальные разделы из nav-config.ts подключаются по мере готовности
                соответствующих страниц — см. IMPLEMENTATION_PLAN.md/AUDIT.md. */}
          </Route>
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
