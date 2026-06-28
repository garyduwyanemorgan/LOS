import { useQuery } from '@tanstack/react-query'
import { observationApi } from '@/lib/api'
import type { Observation, TimeSeriesPoint } from '@/types'
import { subDays, formatISO } from 'date-fns'

interface UseLatestObservationsOptions {
  lagoonId: string | null
  refetchInterval?: number
}

export function useLatestObservations({
  lagoonId,
  refetchInterval = 30_000,
}: UseLatestObservationsOptions) {
  return useQuery<Observation[]>({
    queryKey: ['observations', 'latest', lagoonId],
    queryFn: () => observationApi.getLatest(lagoonId!),
    enabled: !!lagoonId,
    refetchInterval,
    staleTime: 20_000,
  })
}

interface UseTimeSeriesOptions {
  lagoonId: string | null
  parameter: string
  daysBack?: number
  enabled?: boolean
}

export function useTimeSeries({
  lagoonId,
  parameter,
  daysBack = 7,
  enabled = true,
}: UseTimeSeriesOptions) {
  const end = new Date()
  const start = subDays(end, daysBack)

  const { data: rawData, ...rest } = useQuery<Observation[]>({
    queryKey: ['observations', 'timeseries', lagoonId, parameter, daysBack],
    queryFn: () =>
      observationApi.getTimeSeries(
        lagoonId!,
        parameter,
        formatISO(start),
        formatISO(end)
      ),
    enabled: !!lagoonId && !!parameter && enabled,
    staleTime: 5 * 60_000,
  })

  const timeSeriesData: TimeSeriesPoint[] =
    rawData?.map((obs) => ({
      timestamp: obs.timestamp,
      value: obs.value,
      confidence: obs.confidence,
      quality_flag: obs.quality_flag,
    })) ?? []

  return { data: timeSeriesData, rawData, ...rest }
}

// Extract a specific parameter's latest value from observation list
export function getLatestValue(
  observations: Observation[] | undefined,
  parameter: string
): Observation | undefined {
  if (!observations) return undefined
  return observations
    .filter((o) => o.parameter === parameter)
    .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())[0]
}

// Group observations by parameter
export function groupByParameter(
  observations: Observation[]
): Record<string, Observation[]> {
  return observations.reduce(
    (acc, obs) => {
      const existing = acc[obs.parameter] ?? []
      return { ...acc, [obs.parameter]: [...existing, obs] }
    },
    {} as Record<string, Observation[]>
  )
}
