import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { recommendationApi } from '@/lib/api'
import type { Recommendation, PaginatedResponse } from '@/types'
import { useNotificationStore } from '@/stores/notification.store'

interface UseRecommendationsOptions {
  lagoonId: string | null
  status?: string
}

export function useRecommendations({ lagoonId, status }: UseRecommendationsOptions) {
  return useQuery<PaginatedResponse<Recommendation>>({
    queryKey: ['recommendations', lagoonId, status],
    queryFn: () => recommendationApi.list(lagoonId!, status),
    enabled: !!lagoonId,
    staleTime: 60_000,
  })
}

export function usePendingRecommendations(lagoonId: string | null) {
  return useRecommendations({ lagoonId, status: 'pending' })
}

export function useApproveRecommendation() {
  const queryClient = useQueryClient()
  const { success, error } = useNotificationStore()

  return useMutation({
    mutationFn: ({ id, notes }: { id: string; notes?: string }) =>
      recommendationApi.approve(id, notes),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ['recommendations'] })
      success('Recommendation approved', `Action scheduled: ${updated.action}`)
    },
    onError: (err) => {
      const message = err instanceof Error ? err.message : 'Failed to approve'
      error('Approval failed', message)
    },
  })
}

export function useRejectRecommendation() {
  const queryClient = useQueryClient()
  const { success, error } = useNotificationStore()

  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      recommendationApi.reject(id, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['recommendations'] })
      success('Recommendation rejected')
    },
    onError: (err) => {
      const message = err instanceof Error ? err.message : 'Failed to reject'
      error('Rejection failed', message)
    },
  })
}
