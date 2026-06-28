import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import axios from 'axios'
import type { User } from '@/types'
import { authApi, userApi } from '@/lib/api'

interface AuthState {
  user: User | null
  accessToken: string | null
  refreshToken: string | null
  isAuthenticated: boolean
  isLoading: boolean
  error: string | null
}

interface AuthActions {
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  fetchMe: () => Promise<void>
  setTokens: (accessToken: string, refreshToken: string) => void
  clearError: () => void
}

// ---------------------------------------------------------------------------
// Proactive token refresh timer
// Uses plain axios (not the intercepted http instance) to avoid retry loops.
// ---------------------------------------------------------------------------
let _refreshTimer: ReturnType<typeof setTimeout> | null = null

function _scheduleRefresh(expiresInMs: number): void {
  if (_refreshTimer) {
    clearTimeout(_refreshTimer)
    _refreshTimer = null
  }

  // Fire 5 minutes before expiry; never sooner than 60 s from now.
  const delay = Math.max(expiresInMs - 300_000, 60_000)

  _refreshTimer = setTimeout(async () => {
    const refreshToken = localStorage.getItem('los_refresh_token')
    if (!refreshToken) {
      localStorage.removeItem('los_access_token')
      useAuthStore.setState({ user: null, accessToken: null, refreshToken: null, isAuthenticated: false })
      window.location.href = '/login'
      return
    }

    try {
      const { data } = await axios.post<{ access_token: string }>('/api/v1/auth/refresh', {
        refresh_token: refreshToken,
      })
      localStorage.setItem('los_access_token', data.access_token)
      useAuthStore.setState({ accessToken: data.access_token })
      // Reschedule for the next full 8-hour window.
      _scheduleRefresh(480 * 60 * 1000)
    } catch {
      // 401 or network error — kill the session.
      localStorage.removeItem('los_access_token')
      localStorage.removeItem('los_refresh_token')
      useAuthStore.setState({ user: null, accessToken: null, refreshToken: null, isAuthenticated: false })
      window.location.href = '/login'
    }
  }, delay)
}
// ---------------------------------------------------------------------------

export const useAuthStore = create<AuthState & AuthActions>()(
  persist(
    (set, get) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,

      login: async (email, password) => {
        set({ isLoading: true, error: null })
        try {
          const { access_token, refresh_token } = await authApi.login(email, password)
          localStorage.setItem('los_access_token', access_token)
          localStorage.setItem('los_refresh_token', refresh_token)
          set({
            accessToken: access_token,
            refreshToken: refresh_token,
            isAuthenticated: true,
            isLoading: false,
          })
          _scheduleRefresh(480 * 60 * 1000)
          await get().fetchMe()
        } catch (err) {
          const message = err instanceof Error ? err.message : 'Login failed'
          set({ isLoading: false, error: message, isAuthenticated: false })
          throw err
        }
      },

      logout: async () => {
        if (_refreshTimer) { clearTimeout(_refreshTimer); _refreshTimer = null }
        try {
          await authApi.logout()
        } catch {
          // ignore
        }
        localStorage.removeItem('los_access_token')
        localStorage.removeItem('los_refresh_token')
        set({
          user: null,
          accessToken: null,
          refreshToken: null,
          isAuthenticated: false,
        })
      },

      fetchMe: async () => {
        set({ isLoading: true })
        try {
          const user = await userApi.me()
          set({ user, isLoading: false })
        } catch {
          set({ isLoading: false })
        }
      },

      setTokens: (accessToken, refreshToken) => {
        localStorage.setItem('los_access_token', accessToken)
        localStorage.setItem('los_refresh_token', refreshToken)
        set({ accessToken, refreshToken, isAuthenticated: true })
      },

      clearError: () => set({ error: null }),
    }),
    {
      name: 'los-auth',
      partialize: (state) => ({
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        isAuthenticated: state.isAuthenticated,
        user: state.user,
      }),
      onRehydrateStorage: () => (state) => {
        // Re-sync plain localStorage keys so the API interceptor can find them
        if (state?.accessToken) localStorage.setItem('los_access_token', state.accessToken)
        if (state?.refreshToken) localStorage.setItem('los_refresh_token', state.refreshToken)
        // Re-arm the proactive refresh timer for returning users.
        if (state?.accessToken) _scheduleRefresh(480 * 60 * 1000)
      },
    }
  )
)
