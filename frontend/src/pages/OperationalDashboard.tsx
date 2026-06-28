import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useLagoonStore } from '@/stores/lagoon.store'
import { api } from '@/lib/api'
import { MetricCard } from '@/components/shared/MetricCard'
import { ScientificLoopStatus } from '@/components/shared/ScientificLoopStatus'
import { EventFeed } from '@/components/shared/EventFeed'
import { RecommendationCard } from '@/components/shared/RecommendationCard'
import { TimeSeriesChart } from '@/components/charts/TimeSeriesChart'
import { ConfidenceGauge } from '@/components/charts/ConfidenceGauge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

export default function OperationalDashboard() {
  const { selectedLagoon } = useLagoonStore()
  const [activeTab, setActiveTab] = useState('overview')

  const { data: systemState } = useQuery({
    queryKey: ['system-state', selectedLagoon?.id],
    queryFn: () => api.lagoons.getSystemState(selectedLagoon!.id),
    enabled: !!selectedLagoon,
    refetchInterval: 60_000,
  })

  const { data: recommendations } = useQuery({
    queryKey: ['recommendations', selectedLagoon?.id, 'pending'],
    queryFn: () => api.recommendations.list(selectedLagoon!.id, { status: 'pending', limit: 5 }),
    enabled: !!selectedLagoon,
    refetchInterval: 120_000,
  })

  const { data: recentObs } = useQuery({
    queryKey: ['observations-recent', selectedLagoon?.id],
    queryFn: () => api.observations.getRecent(selectedLagoon!.id, { hours: 24, limit: 200 }),
    enabled: !!selectedLagoon,
    refetchInterval: 300_000,
  })

  const { data: recentEvents } = useQuery({
    queryKey: ['events-recent', selectedLagoon?.id],
    queryFn: () => api.events.listByLagoon(selectedLagoon!.id, { limit: 8 }),
    enabled: !!selectedLagoon,
    refetchInterval: 60_000,
  })

  if (!selectedLagoon) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-muted-foreground">Select a lagoon to view the operational dashboard.</p>
      </div>
    )
  }

  const chemical = systemState?.chemical
  const ecological = systemState?.ecological
  const hydrological = systemState?.hydrological
  const infrastructure = systemState?.infrastructure

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{selectedLagoon.name}</h1>
          <p className="text-muted-foreground text-sm mt-1">Operational Dashboard — Real-time Monitoring</p>
        </div>
        <div className="flex items-center gap-2">
          <div className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-sm text-muted-foreground">Live</span>
        </div>
      </div>

      {/* Scientific Loop Status Row */}
      <ScientificLoopStatus loops={systemState?.loops ?? []} />

      {/* Key metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          title="Dissolved Oxygen"
          value={chemical?.do_mg_l ?? null}
          unit="mg/L"
          threshold={{ critical: 2, warning: 4, good: 6 }}
          precision={1}
        />
        <MetricCard
          title="ORP"
          value={chemical?.orp_mv ?? null}
          unit="mV"
          threshold={{ critical: -200, warning: 0, good: 200 }}
          precision={0}
        />
        <MetricCard
          title="Bloom Probability"
          value={ecological?.bloom_probability != null ? ecological.bloom_probability * 100 : null}
          unit="%"
          threshold={{ critical: 70, warning: 40, good: 20 }}
          precision={0}
          invertThreshold
        />
        <MetricCard
          title="Residence Time"
          value={hydrological?.residence_time_days ?? null}
          unit="days"
          threshold={{ critical: 30, warning: 20, good: 10 }}
          precision={1}
          invertThreshold
        />
      </div>

      {/* Main content tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="chemical">Chemical</TabsTrigger>
          <TabsTrigger value="ecological">Ecological</TabsTrigger>
          <TabsTrigger value="infrastructure">Infrastructure</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="mt-4">
          <div className="grid grid-cols-3 gap-6">
            <div className="col-span-2 space-y-4">
              {/* DO time series */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm font-medium">Dissolved Oxygen — 24h Trend</CardTitle>
                </CardHeader>
                <CardContent>
                  <TimeSeriesChart
                    series={[{
                      name: 'Dissolved Oxygen',
                      data: (recentObs ?? []).filter(o => o.parameter === 'dissolved_oxygen'),
                      unit: 'mg/L',
                    }]}
                    thresholds={[
                      { value: 2, label: 'Critical', color: '#DC2626' },
                      { value: 4, label: 'Warning', color: '#D97706' },
                    ]}
                    height={200}
                  />
                </CardContent>
              </Card>

              {/* Pending recommendations */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm font-medium flex items-center gap-2">
                    Pending Recommendations
                    {(recommendations?.length ?? 0) > 0 && (
                      <Badge variant="destructive" className="text-xs">
                        {recommendations?.length}
                      </Badge>
                    )}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {recommendations?.map(rec => (
                    <RecommendationCard key={rec.id} recommendation={rec} showActions={false} />
                  ))}
                  {(!recommendations || recommendations.length === 0) && (
                    <p className="text-sm text-muted-foreground text-center py-4">
                      No pending recommendations.
                    </p>
                  )}
                </CardContent>
              </Card>
            </div>

            <div className="space-y-4">
              {/* System confidence gauge */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm font-medium">System Confidence</CardTitle>
                </CardHeader>
                <CardContent>
                  <ConfidenceGauge value={systemState?.overall_confidence ?? 0} size={150} />
                </CardContent>
              </Card>

              {/* Live event feed */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm font-medium">Live Events</CardTitle>
                </CardHeader>
                <CardContent>
                  <EventFeed events={recentEvents ?? []} maxItems={8} compact />
                </CardContent>
              </Card>
            </div>
          </div>
        </TabsContent>

        <TabsContent value="chemical" className="mt-4">
          <div className="grid grid-cols-2 gap-6">
            {[
              { param: 'dissolved_oxygen', label: 'Dissolved Oxygen', unit: 'mg/L' },
              { param: 'ph', label: 'pH', unit: '' },
              { param: 'orp', label: 'ORP', unit: 'mV' },
              { param: 'electrical_conductivity', label: 'Electrical Conductivity', unit: 'μS/cm' },
            ].map(({ param, label, unit }) => (
              <Card key={param}>
                <CardHeader>
                  <CardTitle className="text-sm font-medium">{label}</CardTitle>
                </CardHeader>
                <CardContent>
                  <TimeSeriesChart
                    series={[{
                      name: label,
                      data: (recentObs ?? []).filter(o => o.parameter === param),
                      unit,
                    }]}
                    height={160}
                  />
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="ecological" className="mt-4">
          <div className="grid grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-medium">Ecological State</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {ecological ? (
                  <>
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">Bloom Probability</span>
                      <span className="font-mono">{((ecological.bloom_probability ?? 0) * 100).toFixed(1)}%</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">Cyanobacteria Risk</span>
                      <Badge variant={ecological.cyanobacteria_risk === 'critical' ? 'destructive' : 'secondary'}>
                        {ecological.cyanobacteria_risk ?? 'unknown'}
                      </Badge>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">Stability Score</span>
                      <span className="font-mono">{ecological.ecological_stability_score?.toFixed(2) ?? '—'}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">Recovery Potential</span>
                      <span className="capitalize">{ecological.recovery_potential ?? 'unknown'}</span>
                    </div>
                  </>
                ) : (
                  <p className="text-muted-foreground text-sm">No ecological data available.</p>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-medium">Chlorophyll-a Trend</CardTitle>
              </CardHeader>
              <CardContent>
                <TimeSeriesChart
                  series={[{
                    name: 'Chlorophyll-a',
                    data: (recentObs ?? []).filter(o => o.parameter === 'chlorophyll_a'),
                    unit: 'μg/L',
                  }]}
                  height={160}
                />
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="infrastructure" className="mt-4">
          <div className="grid grid-cols-2 gap-4">
            {[
              { label: 'Aeration System', status: infrastructure?.aeration_status },
              { label: 'Pump System', status: infrastructure?.pump_status },
            ].map(({ label, status }) => (
              <Card key={label}>
                <CardContent className="flex items-center gap-4 p-6">
                  <div className={`h-3 w-3 rounded-full ${
                    status === 'online' ? 'bg-emerald-400' :
                    status === 'degraded' ? 'bg-amber-400' :
                    status === 'offline' ? 'bg-red-400' : 'bg-slate-400'
                  }`} />
                  <div>
                    <p className="font-medium text-sm">{label}</p>
                    <p className="text-xs text-muted-foreground capitalize">{status ?? 'unknown'}</p>
                  </div>
                </CardContent>
              </Card>
            ))}
            <Card>
              <CardContent className="p-6">
                <p className="text-sm text-muted-foreground">Sensor Coverage</p>
                <p className="text-2xl font-mono font-semibold mt-1">
                  {infrastructure?.sensor_coverage_pct?.toFixed(0) ?? '—'}%
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-6">
                <p className="text-sm text-muted-foreground">Active Alerts</p>
                <p className="text-2xl font-mono font-semibold mt-1">
                  {infrastructure?.active_alerts ?? 0}
                </p>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  )
}
