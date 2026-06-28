import React, { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard,
  Activity,
  FlaskConical,
  TrendingUp,
  ClipboardList,
  Beaker,
  FileText,
  Settings,
  Menu,
  Bell,
  LogOut,
  User,
  ChevronLeft,
  ChevronRight,
  Waves,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/stores/auth.store'
import { LagoonSelector } from './LagoonSelector'
import { ToastProvider, ToastViewport } from '@/components/ui/toast'
import { useNotificationStore } from '@/stores/notification.store'
import { Toast, ToastTitle, ToastDescription, ToastClose } from '@/components/ui/toast'

interface NavItem {
  to: string
  icon: React.ReactNode
  label: string
  roles?: string[]
}

const NAV_ITEMS: NavItem[] = [
  { to: '/', icon: <LayoutDashboard className="h-5 w-5" />, label: 'Executive' },
  { to: '/operational', icon: <Activity className="h-5 w-5" />, label: 'Operational' },
  { to: '/science', icon: <FlaskConical className="h-5 w-5" />, label: 'Scientific' },
  { to: '/predictive', icon: <TrendingUp className="h-5 w-5" />, label: 'Predictive' },
  { to: '/recommendations', icon: <ClipboardList className="h-5 w-5" />, label: 'Recommendations' },
  { to: '/sampling', icon: <Beaker className="h-5 w-5" />, label: 'Sampling' },
  { to: '/reports', icon: <FileText className="h-5 w-5" />, label: 'Reports' },
  { to: '/admin', icon: <Settings className="h-5 w-5" />, label: 'Admin', roles: ['superadmin', 'admin'] },
]

export const Layout: React.FC = () => {
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [mobileOpen, setMobileOpen] = useState(false)
  const { user, logout } = useAuthStore()
  const { toasts, removeToast } = useNotificationStore()
  const navigate = useNavigate()

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  const filteredNav = NAV_ITEMS.filter(
    (item) => !item.roles || (user && item.roles.includes(user.role))
  )

  const Sidebar = ({ mobile = false }: { mobile?: boolean }) => (
    <div
      className={cn(
        'flex flex-col h-full bg-[#0D2137] text-white transition-all duration-300',
        !mobile && (sidebarOpen ? 'w-56' : 'w-16')
      )}
    >
      {/* Logo */}
      <div className="flex items-center gap-3 px-4 py-5 border-b border-white/10">
        <div className="shrink-0 w-8 h-8 bg-[#0891B2] rounded-lg flex items-center justify-center">
          <Waves className="h-5 w-5 text-white" />
        </div>
        {(sidebarOpen || mobile) && (
          <div>
            <div className="font-bold text-sm leading-none">LOS</div>
            <div className="text-xs text-white/50 leading-none mt-0.5">Lagoons OS</div>
          </div>
        )}
        {!mobile && (
          <button
            onClick={() => setSidebarOpen((o) => !o)}
            className="ml-auto text-white/40 hover:text-white transition-colors"
          >
            {sidebarOpen ? (
              <ChevronLeft className="h-4 w-4" />
            ) : (
              <ChevronRight className="h-4 w-4" />
            )}
          </button>
        )}
      </div>

      {/* Lagoon selector */}
      {(sidebarOpen || mobile) && (
        <div className="px-3 py-3 border-b border-white/10">
          <LagoonSelector />
        </div>
      )}

      {/* Nav */}
      <nav className="flex-1 px-2 py-3 space-y-0.5 overflow-y-auto">
        {filteredNav.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors',
                isActive
                  ? 'bg-[#0891B2] text-white'
                  : 'text-white/70 hover:bg-white/10 hover:text-white'
              )
            }
            onClick={() => setMobileOpen(false)}
          >
            {item.icon}
            {(sidebarOpen || mobile) && <span>{item.label}</span>}
          </NavLink>
        ))}
      </nav>

      {/* User footer */}
      <div className="border-t border-white/10 p-3">
        {(sidebarOpen || mobile) ? (
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 bg-[#0891B2] rounded-full flex items-center justify-center shrink-0">
              <User className="h-4 w-4" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium truncate">{user?.full_name ?? 'User'}</p>
              <p className="text-xs text-white/40 truncate capitalize">{user?.role}</p>
            </div>
            <button
              onClick={handleLogout}
              className="text-white/40 hover:text-white transition-colors"
              title="Logout"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        ) : (
          <button
            onClick={handleLogout}
            className="w-full flex items-center justify-center text-white/40 hover:text-white transition-colors py-1"
            title="Logout"
          >
            <LogOut className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  )

  return (
    <ToastProvider>
      <div className="flex h-screen overflow-hidden bg-[#F8FAFC]">
        {/* Desktop sidebar */}
        <div className="hidden md:flex shrink-0">
          <Sidebar />
        </div>

        {/* Mobile sidebar overlay */}
        {mobileOpen && (
          <div className="fixed inset-0 z-50 md:hidden">
            <div
              className="absolute inset-0 bg-black/50"
              onClick={() => setMobileOpen(false)}
            />
            <div className="absolute left-0 top-0 h-full w-64">
              <Sidebar mobile />
            </div>
          </div>
        )}

        {/* Main content */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Header */}
          <header className="bg-white border-b border-slate-200 px-4 py-3 flex items-center gap-4 shrink-0">
            <button
              className="md:hidden text-slate-500 hover:text-slate-700"
              onClick={() => setMobileOpen(true)}
            >
              <Menu className="h-5 w-5" />
            </button>

            <div className="flex-1" />

            <button className="relative text-slate-500 hover:text-slate-700 transition-colors">
              <Bell className="h-5 w-5" />
              <span className="absolute -top-0.5 -right-0.5 w-2 h-2 bg-red-500 rounded-full" />
            </button>

            <div className="flex items-center gap-2 text-sm text-slate-600">
              <div className="w-7 h-7 bg-[#0D2137] rounded-full flex items-center justify-center">
                <User className="h-4 w-4 text-white" />
              </div>
              <span className="hidden sm:block font-medium">{user?.full_name ?? 'User'}</span>
            </div>
          </header>

          {/* Page content */}
          <main className="flex-1 overflow-y-auto">
            <Outlet />
          </main>
        </div>
      </div>

      {/* Toast notifications */}
      <ToastViewport />
      {toasts.map((toast) => (
        <Toast
          key={toast.id}
          variant={
            toast.variant === 'success'
              ? 'success'
              : toast.variant === 'error'
                ? 'destructive'
                : toast.variant === 'warning'
                  ? 'warning'
                  : toast.variant === 'info'
                    ? 'info'
                    : 'default'
          }
        >
          <div className="grid gap-1">
            <ToastTitle>{toast.title}</ToastTitle>
            {toast.description && <ToastDescription>{toast.description}</ToastDescription>}
          </div>
          <ToastClose onClick={() => removeToast(toast.id)} />
        </Toast>
      ))}
    </ToastProvider>
  )
}
