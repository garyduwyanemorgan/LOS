import { useCallback } from 'react'
import { useAuthStore } from '@/stores/auth.store'
import type { User } from '@/types'

export function useAuth() {
  const {
    user,
    isAuthenticated,
    isLoading,
    error,
    login,
    logout,
    fetchMe,
    clearError,
  } = useAuthStore()

  const hasRole = useCallback(
    (roles: User['role'][]): boolean => {
      if (!user) return false
      return roles.includes(user.role)
    },
    [user]
  )

  const isAdmin = useCallback(
    () => hasRole(['superadmin', 'admin']),
    [hasRole]
  )

  const canEdit = useCallback(
    () => hasRole(['superadmin', 'admin', 'engineer', 'scientist']),
    [hasRole]
  )

  const canApprove = useCallback(
    () => hasRole(['superadmin', 'admin', 'engineer']),
    [hasRole]
  )

  return {
    user,
    isAuthenticated,
    isLoading,
    error,
    login,
    logout,
    fetchMe,
    clearError,
    hasRole,
    isAdmin,
    canEdit,
    canApprove,
  }
}
