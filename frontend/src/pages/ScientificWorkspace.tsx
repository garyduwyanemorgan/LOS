import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useLagoonStore } from '@/stores/lagoon.store'
import { api, observationApi } from '@/lib/api'
import { TimeSeriesChart } from '@/components/charts/TimeSeriesChart'
import { WaterQualityRadar } from '@/components/charts/WaterQualityRadar'
import { LoopInteractionDiagram } from '@/components/charts/LoopInteractionDiagram'
import { ConfidenceGauge } from '@/components/charts/ConfidenceGauge'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

const PARAMETERS = [
  { value: 'dissolved_oxygen', label: 'Dissolved Oxygen', unit: 'mg/L' },
  { value: 'orp', label: 'ORP / Redox', unit: 'mV' },
  { value: 'ph', label: 'pH', unit: '' },
  { value: 'conductivity', label: 'Electrical Conductivity', unit: 'μS/cm' },
  { value: 'water_temperature', label: 'Water Temperature', unit: '°C' },
  { value: 'turbidity', label: 'Turbidity', unit: 'NTU' },
  { value: 'chlorophyll_a', label: 'Chlorophyll-a', unit: 'μg/L' },
  { value: 'tn_mg_l', label: 'Total Nitrogen', unit: 'mg/L' },
  { value: 'tp_mg_l', label: 'Total Phosphorus', unit: 'mg/L' },
  { value: 'nh4_mg_l', label: 'Ammonia-N', unit: 'mg/L' },
  { value: 'no3_mg_l', label: 'Nitrate-N', unit: 'mg/L' },
]

const TIME_WINDOWS = [
  { value: '24', label: 'Last 24 hours' },
  { value: '72', label: 'Last 3 days' },
  { value: '168', label: 'Last 7 days' },
  { value: '720', label: 'Last 30 days' },
]

export default function ScientificWorkspace() {
  const { selectedLagoon, systemState } = useLagoonStore()
  const [selectedParam, setSelectedParam] = useState('dissolved_oxygen')
  const [timeWindow, setTimeWindow] = useState('72')

  const { data: observations, isLoading } = useQuery({
    queryKey: ['timeseries', selectedLagoon?.id, selectedParam, timeWindow],
    queryFn: () => {
      const now = new Date()
      const start = new Date(now.getTime() - parseInt(timeWindow) * 3600 * 1000)
      return observationApi.getTimeSeries(
        selectedLagoon!.id,
        selectedParam,
        start.toISOString(),
        now.toISOString(),
      )
    },
    enabled: !!selectedLagoon,
  })

  const { data: labResults } = useQuery({
    queryKey: ['lab-results', selectedLagoon?.id],
    queryFn: () => api.observations.getLabResults(selectedLagoon!.id, { days: 30 }),
    enabled: !!selectedLagoon,
  })

  if (!selectedLagoon) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-muted-foreground">Select a lagoon to open the scientific workspace.</p>
      </div>
    )
  }

  const paramConfig = PARAMETERS.find(p => p.value === selectedParam)

  const radarParameters = useMemo(() => {
    if (!systemState) return []
    const chem = systemState.chemical
    const eco = systemState.ecological
    const params: Array<{ parameter: string; current: number | null; target: number; unit: string; maxValue: number }> = [
      { parameter: 'DO', current: chem?.do_mg_l ?? null, target: 7.0, unit: 'mg/L', maxValue: 15 },
      { parameter: 'pH', current: chem?.ph ?? null, target: 8.0, unit: '', maxValue: 14 },
      { parameter: 'ORP', current: chem?.orp_mv != null ? chem.orp_mv + 400 : null, target: 600, unit: 'mV', maxValue: 800 },
      { parameter: 'Bloom Risk', current: eco?.bloom_probability != null ? (1 - eco.bloom_probability) * 100 : null, target: 90, unit: '%', maxValue: 100 },
      { parameter: 'Stability', current: eco?.ecological_stability_score != null ? eco.ecological_stability_score * 100 : null, target: 70, unit: '%', maxValue: 100 },
    ]
    return params.filter(p => p.current !== null) as Array<{ parameter: string; current: number; target: number; unit: string; maxValue: number }>
  }, [systemState])

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Scientific Workspace</h1>
          <p className="text-muted-foreground text-sm mt-1">
            {selectedLagoon.name} — Deep scientific analysis and model inspection
          </p>
        </div>
        <div className="flex gap-2">
          <Select value={selectedParam} onValueChange={setSelectedParam}>
            <SelectTrigger className="w-[220px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PARAMETERS.map(p => (
                <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={timeWindow} onValueChange={setTimeWindow}>
            <SelectTrigger className="w-[160px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {TIME_WINDOWS.map(t => (
                <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-4">
        <div className="col-span-3">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">
                {paramConfig?.label} {paramConfig?.unit && `(${paramConfig.unit})`}
              </CardTitle>
              <CardDescription>
                Sensor observations with quality flags and anomaly markers
              </CardDescription>
            </CardHeader>
            <CardContent>
              <TimeSeriesChart
                series={observations && observations.length > 0
                  ? [{
                      name: paramConfig?.label ?? selectedParam,
                      data: observations.map((o) => ({
                        timestamp: o.timestamp,
                        value: o.value,
                        confidence: o.confidence,
                        quality_flag: o.quality_flag,
                      })),
                      unit: paramConfig?.unit ?? '',
                    }]
                  : []}
                height={280}
              />
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">System Confidence</CardTitle>
            </CardHeader>
            <CardContent>
              <ConfidenceGauge value={systemState?.overall_confidence || 0} size={150} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">Data Quality</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {['good', 'suspect', 'bad', 'missing'].map(flag => {
                const count = (observations ?? []).filter(o => o.quality_flag === flag).length
                return (
                  <div key={flag} className="flex justify-between">
                    <span className="capitalize text-muted-foreground">{flag}</span>
                    <span className="font-mono">{count}</span>
                  </div>
                )
              })}
            </CardContent>
          </Card>
        </div>
      </div>

      <Tabs defaultValue="multivariate">
        <TabsList>
          <TabsTrigger value="multivariate">Multi-Parameter</TabsTrigger>
          <TabsTrigger value="loops">Loop Interactions</TabsTrigger>
          <TabsTrigger value="laboratory">Laboratory Results</TabsTrigger>
        </TabsList>

        <TabsContent value="multivariate" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">Water Quality Profile</CardTitle>
              <CardDescription>Multi-parameter radar — current conditions vs. targets</CardDescription>
            </CardHeader>
            <CardContent>
              <WaterQualityRadar parameters={radarParameters} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="loops" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">Scientific Loop Interactions</CardTitle>
              <CardDescription>
                Cause-effect relationships active in the current system state
              </CardDescription>
            </CardHeader>
            <CardContent>
              <LoopInteractionDiagram loops={(systemState as any)?.loops ?? []} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="laboratory" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">Laboratory Results — Last 30 days</CardTitle>
            </CardHeader>
            <CardContent>
              {labResults && labResults.length > 0 ? (
                <div className="overflow-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border">
                        <th className="text-left py-2 text-muted-foreground font-medium">Date</th>
                        <th className="text-left py-2 text-muted-foreground font-medium">Parameter</th>
                        <th className="text-right py-2 text-muted-foreground font-medium">Value</th>
                        <th className="text-right py-2 text-muted-foreground font-medium">Unit</th>
                        <th className="text-center py-2 text-muted-foreground font-medium">Quality</th>
                      </tr>
                    </thead>
                    <tbody>
                      {labResults.map((r: any) => (
                        <tr key={r.id} className="border-b border-border/50">
                          <td className="py-2 text-muted-foreground">
                            {new Date(r.timestamp).toLocaleDateString()}
                          </td>
                          <td className="py-2 capitalize">{r.parameter.replace(/_/g, ' ')}</td>
                          <td className="py-2 text-right font-mono data-cell">{r.value}</td>
                          <td className="py-2 text-right text-muted-foreground">{r.unit}</td>
                          <td className="py-2 text-center">
                            <Badge
                              variant={r.quality_flag === 'good' ? 'default' : 'secondary'}
                              className="text-xs"
                            >
                              {r.quality_flag}
                            </Badge>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-muted-foreground text-sm text-center py-8">
                  No laboratory results in the selected period.
                </p>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
