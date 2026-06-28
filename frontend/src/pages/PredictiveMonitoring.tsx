import { useQuery } from '@tanstack/react-query'
import { useLagoonStore } from '@/stores/lagoon.store'
import { api } from '@/lib/api'
import { BloomProbabilityChart } from '@/components/charts/BloomProbabilityChart'
import { ConfidenceGauge } from '@/components/charts/ConfidenceGauge'
import { ConfidenceIndicator } from '@/components/shared/ConfidenceIndicator'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { AlertCircle, TrendingUp, TrendingDown, Minus } from 'lucide-react'
import { cn } from '@/lib/utils'

export default function PredictiveMonitoring() {
  const { selectedLagoon } = useLagoonStore()

  const { data: predictions } = useQuery({
    queryKey: ['predictions', selectedLagoon?.id],
    queryFn: () => api.simulations.getPredictions(selectedLagoon!.id, { horizon_hours: 72 }),
    enabled: !!selectedLagoon,
    refetchInterval: 300_000,
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
        <p className="text-muted-foreground">Select a lagoon to view predictive monitoring.</p>
      </div>
    )
  }

  const eco = systemState?.ecological
  const bloomProb = eco?.bloom_probability ?? 0
  const cyanoRisk = eco?.cyanobacteria_risk ?? 'unknown'

  const riskColor = {
    low: 'text-emerald-400',
    medium: 'text-amber-400',
    high: 'text-orange-400',
    critical: 'text-red-400',
    unknown: 'text-slate-400',
  }[cyanoRisk] ?? 'text-slate-400'

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold">Predictive Monitoring</h1>
        <p className="text-muted-foreground text-sm mt-1">
          {selectedLagoon.name} — 72-hour ecological and chemical forecasts
        </p>
      </div>

      {/* Bloom risk header */}
      <div className="grid grid-cols-3 gap-4">
        <Card className={cn(
          'border-2 transition-colors',
          bloomProb > 0.7 ? 'border-red-500/50' :
          bloomProb > 0.4 ? 'border-amber-500/50' :
          'border-emerald-500/50'
        )}>
          <CardContent className="p-6">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Bloom Probability</p>
                <p className="text-4xl font-mono font-bold mt-2">
                  {(bloomProb * 100).toFixed(0)}%
                </p>
              </div>
              {bloomProb > 0.5 && (
                <AlertCircle className="h-6 w-6 text-red-400 mt-1" />
              )}
            </div>
            <Progress
              value={bloomProb * 100}
              className="mt-4"
            />
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <p className="text-sm text-muted-foreground">Cyanobacteria Risk</p>
            <p className={cn('text-2xl font-semibold mt-2 capitalize', riskColor)}>
              {cyanoRisk}
            </p>
            <p className="text-xs text-muted-foreground mt-3">
              {cyanoRisk === 'critical' && 'Immediate intervention required'}
              {cyanoRisk === 'high' && 'Intervention recommended within 24 hours'}
              {cyanoRisk === 'medium' && 'Monitor closely; prepare intervention'}
              {cyanoRisk === 'low' && 'No immediate concern'}
              {cyanoRisk === 'unknown' && 'Insufficient data'}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <p className="text-sm text-muted-foreground">Model Confidence</p>
            <ConfidenceGauge value={systemState?.overall_confidence ?? 0} size={150} />
          </CardContent>
        </Card>
      </div>

      {/* 72-hour bloom probability forecast */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">72-Hour Bloom Risk Forecast</CardTitle>
          <CardDescription>
            Probabilistic forecast combining hydrological, chemical, and ecological models
          </CardDescription>
        </CardHeader>
        <CardContent>
          <BloomProbabilityChart
            data={(predictions as any)?.bloom_risk_timeseries ?? []}
            height={240}
          />
        </CardContent>
      </Card>

      {/* Parameter forecasts */}
      <div className="grid grid-cols-2 gap-4">
        {[
          { param: 'do_mg_l', label: 'DO Forecast', unit: 'mg/L' },
          { param: 'bloom_probability', label: 'Bloom Probability Forecast', unit: '%' },
        ].map(({ param, label, unit }) => (
          <Card key={param}>
            <CardHeader>
              <CardTitle className="text-sm font-medium">{label}</CardTitle>
            </CardHeader>
            <CardContent>
              {predictions ? (
                <div className="space-y-2">
                  {(['24h', '48h', '72h'] as const).map(horizon => {
                    const value = (predictions as any)[`${param}_${horizon}`] as number | null
                    const confidence = ((predictions as any)[`${param}_${horizon}_confidence`] as number) ?? 0.5
                    return (
                      <div key={horizon} className="flex items-center justify-between">
                        <span className="text-sm text-muted-foreground">+{horizon}</span>
                        <div className="flex items-center gap-3">
                          <ConfidenceIndicator confidence={confidence} size="sm" />
                          <span className="font-mono text-sm">
                            {value != null ? `${value.toFixed(1)} ${unit}` : '—'}
                          </span>
                        </div>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground text-center py-4">
                  Forecast not available
                </p>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Early warning triggers */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">Early Warning Triggers</CardTitle>
          <CardDescription>
            Conditions being monitored for early intervention signals
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {[
              {
                trigger: 'DO < 4 mg/L for > 2 hours',
                active: (systemState?.chemical?.do_mg_l ?? 99) < 4,
                severity: 'warning',
              },
              {
                trigger: 'DO < 2 mg/L (critical hypoxia)',
                active: (systemState?.chemical?.do_mg_l ?? 99) < 2,
                severity: 'critical',
              },
              {
                trigger: 'Bloom probability > 70%',
                active: bloomProb > 0.7,
                severity: 'critical',
              },
              {
                trigger: 'ORP < -100 mV (anaerobic conditions)',
                active: (systemState?.chemical?.orp_mv ?? 999) < -100,
                severity: 'critical',
              },
              {
                trigger: 'Cyanobacteria risk elevated',
                active: ['high', 'critical'].includes(cyanoRisk),
                severity: 'warning',
              },
            ].map(({ trigger, active, severity }) => (
              <div key={trigger} className="flex items-center gap-3">
                <div className={cn(
                  'h-2 w-2 rounded-full flex-shrink-0',
                  active
                    ? severity === 'critical' ? 'bg-red-400 animate-pulse' : 'bg-amber-400 animate-pulse'
                    : 'bg-slate-600'
                )} />
                <span className={cn(
                  'text-sm flex-1',
                  active ? (severity === 'critical' ? 'text-red-400' : 'text-amber-400') : 'text-muted-foreground'
                )}>
                  {trigger}
                </span>
                <Badge variant={active ? (severity === 'critical' ? 'destructive' : 'secondary') : 'outline'}>
                  {active ? 'ACTIVE' : 'OK'}
                </Badge>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
