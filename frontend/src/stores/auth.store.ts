import { create } from 'zustand'
import { persist } from 'zustand/middleware'
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
          await get().fetchMe()
        } catch (err) {
          const message = err instanceof Error ? err.message : 'Login failed'
          set({ isLoading: false, error: message, isAuthenticated: false })
          throw err
        }
      },

      logout: async () => {
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
    }
  )
)
