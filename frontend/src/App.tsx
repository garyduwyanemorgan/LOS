import { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useAuthStore } from '@/stores/auth.store'
import { Layout } from '@/components/shared/Layout'
import { ErrorBoundary } from '@/components/shared/ErrorBoundary'

// Pages
import Login from '@/pages/Login'
import ExecutiveDashboard from '@/pages/ExecutiveDashboard'
import OperationalDashboard from '@/pages/OperationalDashboard'
import ScientificWorkspace from '@/pages/ScientificWorkspace'
import PredictiveMonitoring from '@/pages/PredictiveMonitoring'
import Recommendations from '@/pages/Recommendations'
import AdaptiveSampling from '@/pages/AdaptiveSampling'
import Reports from '@/pages/Reports'
import Administration from '@/pages/Administration'
import NotFound from '@/pages/NotFound'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,       // 30s — scientific data has short stale windows
      gcTime: 300_000,         // 5m cache
      retry: 2,
      refetchOnWindowFocus: false,
    },
  },
})

function AuthGuard({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading, fetchMe } = useAuthStore()

  useEffect(() => {
    fetchMe()
  }, [fetchMe])

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <div className="text-center">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent mx-auto mb-4" />
          <p className="text-muted-foreground text-sm">Initialising LOS...</p>
        </div>
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  return <>{children}</>
}

export default function App() {
  return (
    <ErrorBoundary>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />

          <Route
            path="/"
            element={
              <AuthGuard>
                <Layout />
              </AuthGuard>
            }
          >
            <Route index element={<Navigate to="/dashboard/executive" replace />} />
            <Route path="dashboard/executive" element={<ExecutiveDashboard />} />
            <Route path="dashboard/operational" element={<OperationalDashboard />} />
            <Route path="workspace/scientific" element={<ScientificWorkspace />} />
            <Route path="workspace/predictive" element={<PredictiveMonitoring />} />
            <Route path="recommendations" element={<Recommendations />} />
            <Route path="sampling" element={<AdaptiveSampling />} />
            <Route path="reports" element={<Reports />} />
            <Route path="admin" element={<Administration />} />
          </Route>

          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
    </ErrorBoundary>
  )
}
