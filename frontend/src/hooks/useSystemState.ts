import { useQuery } from '@tanstack/react-query'
import { lagoonApi } from '@/lib/api'
import type { SystemState } from '@/types'
import { useLagoonStore } from '@/stores/lagoon.store'

export function useSystemState(lagoonId: string | null, refetchInterval = 60_000) {
  const { updateLoopState } = useLagoonStore()

  return useQuery<SystemState>({
    queryKey: ['system-state', lagoonId],
    queryFn: async () => {
      const state = await lagoonApi.getStatus(lagoonId!)
      // Sync loops to store for cross-component access
      state.loops.forEach(updateLoopState)
      return state
    },
    enabled: !!lagoonId,
    refetchInterval,
    staleTime: 30_000,
  })
}

export function useChemicalState(lagoonId: string | null) {
  const { data } = useSystemState(lagoonId)
  return data?.chemical ?? null
}

export function useHydrologicalState(lagoonId: string | null) {
  const { data } = useSystemState(lagoonId)
  return data?.hydrological ?? null
}

export function useEcologicalState(lagoonId: string | null) {
  const { data } = useSystemState(lagoonId)
  return data?.ecological ?? null
}

export function useInfrastructureState(lagoonId: string | null) {
  const { data } = useSystemState(lagoonId)
  return data?.infrastructure ?? null
}

export function useHealthScore(lagoonId: string | null): number | null {
  const { data } = useSystemState(lagoonId)
  return data?.overall_health_score ?? null
}
