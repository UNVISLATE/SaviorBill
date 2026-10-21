import { Navigate, Outlet, useLocation } from "react-router-dom"

import { useAuth } from "@/hooks/use-auth"
import { AnimatedLoader } from "@/components/animbits/AnimatedLoader"
import { BackendUnavailablePage } from "@/pages/errors/BackendUnavailablePage"

export function ProtectedRoute() {
  const { isAuthenticated, isLoading, isBackendUnavailable, refetchMe, error } = useAuth()
  const location = useLocation()

  if (isBackendUnavailable) {
    return (
      <BackendUnavailablePage
        onRetry={refetchMe}
        errorMessage={error instanceof Error ? error.message : undefined}
      />
    )
  }

  if (isLoading) {
    return (
      <div className="flex min-h-svh items-center justify-center">
        <AnimatedLoader className="min-h-40" />
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />
  }

  return <Outlet />
}
