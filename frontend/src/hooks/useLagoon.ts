import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useLagoonStore } from '@/stores/lagoon.store'
import { lagoonApi } from '@/lib/api'
import type { OperatingObjective, LagoonPerformance } from '@/types'

export function useLagoon() {
  const {
    lagoons,
    selectedLagoonId,
    selectedLagoon,
    systemState,
    isLoadingLagoons,
    fetchLagoons,
    selectLagoon,
    fetchSystemState,
  } = useLagoonStore()

  // Fetch lagoons on mount
  useEffect(() => {
    if (!lagoons.length) {
      void fetchLagoons()
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-refresh system state every 60s
  useEffect(() => {
    if (!selectedLagoonId) return
    void fetchSystemState(selectedLagoonId)
    const interval = setInterval(() => {
      void fetchSystemState(selectedLagoonId)
    }, 60_000)
    return () => clearInterval(interval)
  }, [selectedLagoonId]) // eslint-disable-line react-hooks/exhaustive-deps

  return {
    lagoons,
    selectedLagoonId,
    selectedLagoon,
    systemState,
    isLoadingLagoons,
    selectLagoon,
    loops: systemState?.loops ?? [],
    chemical: systemState?.chemical ?? null,
    hydrological: systemState?.hydrological ?? null,
    ecological: systemState?.ecological ?? null,
    infrastructure: systemState?.infrastructure ?? null,
    healthScore: systemState?.overall_health_score ?? null,
  }
}

export function useObjectives(lagoonId: string | null) {
  return useQuery<OperatingObjective[]>({
    queryKey: ['objectives', lagoonId],
    queryFn: () => lagoonApi.getObjectives(lagoonId!),
    enabled: !!lagoonId,
    staleTime: 5 * 60_000,
  })
}

export function usePerformance(lagoonId: string | null, days = 30) {
  return useQuery<LagoonPerformance>({
    queryKey: ['performance', lagoonId, days],
    queryFn: () => lagoonApi.getPerformance(lagoonId!, days),
    enabled: !!lagoonId,
    staleTime: 5 * 60_000,
  })
}
