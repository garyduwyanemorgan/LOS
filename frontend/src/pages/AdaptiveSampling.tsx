import { useQuery } from '@tanstack/react-query'
import { useLagoonStore } from '@/stores/lagoon.store'
import { api } from '@/lib/api'
import { ConfidenceIndicator } from '@/components/shared/ConfidenceIndicator'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { MapPin, Calendar, AlertTriangle } from 'lucide-react'

export default function AdaptiveSampling() {
  const { selectedLagoon } = useLagoonStore()

  const { data: sensors } = useQuery({
    queryKey: ['sensors', selectedLagoon?.id],
    queryFn: () => api.sensors.list(selectedLagoon!.id),
    enabled: !!selectedLagoon,
  })

  const { data: systemState } = useQuery({
    queryKey: ['system-state', selectedLagoon?.id],
    queryFn: () => api.lagoons.getSystemState(selectedLagoon!.id),
    enabled: !!selectedLagoon,
    refetchInterval: 120_000,
  })

  if (!selectedLagoon) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-muted-foreground">Select a lagoon to view adaptive sampling.</p>
      </div>
    )
  }

  const sensorCoverage = systemState?.infrastructure?.sensor_coverage_pct ?? 0

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold">Adaptive Sampling</h1>
        <p className="text-muted-foreground text-sm mt-1">
          {selectedLagoon.name} — Sensor network, sampling schedule, and coverage optimisation
        </p>
      </div>

      {/* Coverage summary */}
      <div className="grid grid-cols-3 gap-4">
        <Card>
          <CardContent className="p-6">
            <p className="text-sm text-muted-foreground">Sensor Coverage</p>
            <p className="text-3xl font-mono font-semibold mt-2">{sensorCoverage.toFixed(0)}%</p>
            <Progress value={sensorCoverage} className="mt-3" />
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-6">
            <p className="text-sm text-muted-foreground">Active Sensors</p>
            <p className="text-3xl font-mono font-semibold mt-2">
              {sensors?.filter((s: any) => s.is_active).length ?? '—'}
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              of {sensors?.length ?? 0} installed
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-6">
            <p className="text-sm text-muted-foreground">System Confidence</p>
            <ConfidenceIndicator confidence={systemState?.overall_confidence ?? 0} size="md" showValue />
          </CardContent>
        </Card>
      </div>

      {/* Sensor list */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">Sensor Network</CardTitle>
          <CardDescription>All installed sensors and their current status</CardDescription>
        </CardHeader>
        <CardContent>
          {sensors && sensors.length > 0 ? (
            <div className="space-y-3">
              {sensors.map((sensor: any) => (
                <div
                  key={sensor.id}
                  className="flex items-center gap-4 p-3 rounded-lg bg-muted/50"
                >
                  <div className={`h-2 w-2 rounded-full flex-shrink-0 ${
                    sensor.is_active ? 'bg-emerald-400' : 'bg-red-400'
                  }`} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{sensor.name}</p>
                    <div className="flex items-center gap-2 mt-0.5">
                      <MapPin className="h-3 w-3 text-muted-foreground" />
                      <span className="text-xs text-muted-foreground">
                        {sensor.location_description ?? `Depth: ${sensor.installation_depth_m ?? 0}m`}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <Badge variant="outline" className="text-xs capitalize">
                      {sensor.sensor_type?.replace(/_/g, ' ') ?? 'Unknown'}
                    </Badge>
                    <Badge
                      variant={sensor.is_active ? 'default' : 'destructive'}
                      className="text-xs"
                    >
                      {sensor.is_active ? 'Active' : 'Offline'}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground text-center py-8">
              No sensors configured for this lagoon.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Sampling recommendations */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Calendar className="h-4 w-4" />
            Adaptive Sampling Recommendations
          </CardTitle>
          <CardDescription>
            Sampling schedule adjusted based on current system confidence and conditions
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {[
              {
                parameter: 'Dissolved Oxygen',
                current_interval: '15 min',
                recommended_interval: systemState?.chemical?.do_mg_l != null && systemState.chemical.do_mg_l < 4
                  ? '5 min'
                  : '15 min',
                reason: systemState?.chemical?.do_mg_l != null && systemState.chemical.do_mg_l < 4
                  ? 'Low DO — increase monitoring frequency'
                  : 'Normal conditions',
                priority: systemState?.chemical?.do_mg_l != null && systemState.chemical.do_mg_l < 4 ? 'high' : 'normal',
              },
              {
                parameter: 'Chlorophyll-a',
                current_interval: '30 min',
                recommended_interval: (systemState?.ecological?.bloom_probability ?? 0) > 0.4 ? '10 min' : '30 min',
                reason: (systemState?.ecological?.bloom_probability ?? 0) > 0.4
                  ? 'Elevated bloom risk — increase monitoring'
                  : 'Normal conditions',
                priority: (systemState?.ecological?.bloom_probability ?? 0) > 0.4 ? 'high' : 'normal',
              },
              {
                parameter: 'Laboratory Analysis (grab sample)',
                current_interval: 'Weekly',
                recommended_interval: 'Weekly',
                reason: 'Standard programme',
                priority: 'normal',
              },
            ].map(item => (
              <div key={item.parameter} className="flex items-start gap-3 p-3 rounded-lg bg-muted/50">
                {item.priority === 'high' && (
                  <AlertTriangle className="h-4 w-4 text-amber-400 mt-0.5 flex-shrink-0" />
                )}
                <div className="flex-1">
                  <p className="text-sm font-medium">{item.parameter}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">{item.reason}</p>
                </div>
                <div className="text-right flex-shrink-0">
                  {item.current_interval !== item.recommended_interval ? (
                    <>
                      <p className="text-xs text-muted-foreground line-through">{item.current_interval}</p>
                      <p className="text-sm font-medium text-amber-400">{item.recommended_interval}</p>
                    </>
                  ) : (
                    <p className="text-sm text-muted-foreground">{item.current_interval}</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
