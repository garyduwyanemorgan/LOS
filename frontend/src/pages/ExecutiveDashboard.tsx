import React from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, Droplets, Activity, Award, ClipboardList } from 'lucide-react'
import { useLagoon, useObjectives, usePerformance } from '@/hooks/useLagoon'
import { usePendingRecommendations } from '@/hooks/useRecommendations'
import { ScientificLoopStatus } from '@/components/shared/ScientificLoopStatus'
import { RecommendationCard } from '@/components/shared/RecommendationCard'
import { MetricCard } from '@/components/shared/MetricCard'
import { ConfidenceGauge } from '@/components/charts/ConfidenceGauge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import {
  formatDate,
  trendIcon,
  trendColor,
  healthScoreColor,
  formatPercent,
  formatValue,
} from '@/lib/utils'
import { useApproveRecommendation, useRejectRecommendation } from '@/hooks/useRecommendations'
import { useRealtimeEvents } from '@/hooks/useRealtimeEvents'
import { EventFeed } from '@/components/shared/EventFeed'

// Mock 30-day trend data (replace with real data when API supports it)
function generate30DayTrend() {
  const data = []
  const now = new Date()
  for (let i = 29; i >= 0; i--) {
    const date = new Date(now)
    date.setDate(date.getDate() - i)
    data.push({
      date: date.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' }),
      wqi: 60 + Math.random() * 25 - i * 0.3,
      bloom: Math.max(0, Math.random() * 60 - i * 0.5),
    })
  }
  return data
}

const trendData = generate30DayTrend()

export default function ExecutiveDashboard() {
  const navigate = useNavigate()
  const { selectedLagoonId, selectedLagoon, loops, chemical, ecological, healthScore } = useLagoon()
  const { data: objectivesData } = useObjectives(selectedLagoonId)
  const { data: performance } = usePerformance(selectedLagoonId, 30)
  const { data: recommendationsData } = usePendingRecommendations(selectedLagoonId)
  const { events } = useRealtimeEvents({ maxEvents: 5 })
  const approveMutation = useApproveRecommendation()
  const rejectMutation = useRejectRecommendation()

  const topRecommendations = (recommendationsData?.items ?? []).slice(0, 3)
  const objectives = objectivesData ?? []

  return (
    <div className="p-6 space-y-6 max-w-screen-2xl mx-auto">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[#0D2137]">Executive Dashboard</h1>
          <p className="text-slate-500 text-sm mt-0.5">
            {selectedLagoon
              ? `${selectedLagoon.name} — ${selectedLagoon.location.city}, ${selectedLagoon.location.country}`
              : 'Select a lagoon to view data'}
          </p>
        </div>
        <div className="text-xs text-slate-400">
          {new Date().toLocaleDateString('en-GB', {
            weekday: 'long',
            day: 'numeric',
            month: 'long',
            year: 'numeric',
          })}
        </div>
      </div>

      {/* Top row: Health score + KPIs */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        {/* Health score gauge */}
        <Card className="lg:col-span-1 flex items-center justify-center py-4">
          <div className="text-center">
            <ConfidenceGauge
              value={healthScore ?? 0}
              label="Lagoon Health"
              size={180}
              isScore
            />
            <p className="text-xs text-slate-500 mt-1">Overall system score</p>
          </div>
        </Card>

        {/* KPI cards */}
        <div className="lg:col-span-4 grid grid-cols-2 xl:grid-cols-4 gap-4">
          <MetricCard
            title="Water Quality Index"
            value={performance?.water_quality_index ?? null}
            unit="/100"
            precision={0}
            trend={
              performance?.trend_wqi === 'improving'
                ? 'up'
                : performance?.trend_wqi === 'deteriorating'
                  ? 'down'
                  : 'stable'
            }
            status={
              (performance?.water_quality_index ?? 0) >= 70
                ? 'good'
                : (performance?.water_quality_index ?? 0) >= 50
                  ? 'warning'
                  : 'critical'
            }
          />
          <MetricCard
            title="Bloom Risk"
            value={
              ecological?.bloom_probability !== null && ecological?.bloom_probability !== undefined
                ? Math.round(ecological.bloom_probability * 100)
                : null
            }
            unit="%"
            precision={0}
            status={
              ecological?.cyanobacteria_risk === 'critical'
                ? 'critical'
                : ecological?.cyanobacteria_risk === 'high'
                  ? 'warning'
                  : 'good'
            }
            trend={ecological?.bloom_detected ? 'up' : 'stable'}
            trendPositive={false}
          />
          <MetricCard
            title="Compliance Score"
            value={performance?.compliance_score ?? null}
            unit="%"
            precision={0}
            status={
              (performance?.compliance_score ?? 0) >= 90
                ? 'good'
                : (performance?.compliance_score ?? 0) >= 70
                  ? 'warning'
                  : 'critical'
            }
          />
          <MetricCard
            title="Active Recommendations"
            value={recommendationsData?.total ?? 0}
            unit="pending"
            precision={0}
            status={
              (recommendationsData?.total ?? 0) === 0
                ? 'good'
                : (recommendationsData?.total ?? 0) <= 3
                  ? 'warning'
                  : 'critical'
            }
          />
        </div>
      </div>

      {/* Scientific loop status */}
      <div>
        <h2 className="text-sm font-semibold text-slate-700 uppercase tracking-wide mb-3">
          Scientific Loop Status
        </h2>
        <ScientificLoopStatus loops={loops} />
      </div>

      {/* Middle row: Trend chart + Recommendations */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        {/* 30-day trend */}
        <Card className="xl:col-span-2">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">30-Day Water Quality Trend</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={trendData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 10 }}
                  tickLine={false}
                  interval={6}
                />
                <YAxis tick={{ fontSize: 10 }} tickLine={false} />
                <Tooltip
                  contentStyle={{ fontSize: '12px', border: '1px solid #E2E8F0' }}
                />
                <Legend wrapperStyle={{ fontSize: '12px' }} />
                <Line
                  type="monotone"
                  dataKey="wqi"
                  name="WQI"
                  stroke="#0891B2"
                  strokeWidth={2}
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="bloom"
                  name="Bloom Risk %"
                  stroke="#DC2626"
                  strokeWidth={1.5}
                  dot={false}
                  strokeDasharray="4 2"
                />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Top recommendations */}
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Top Recommendations</CardTitle>
              <Button
                size="xs"
                variant="ghost"
                onClick={() => navigate('/recommendations')}
                className="text-[#0891B2]"
              >
                View all <ArrowRight className="h-3 w-3 ml-1" />
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-3 pt-0">
            {topRecommendations.length === 0 ? (
              <div className="text-center py-6 text-slate-400 text-sm">
                No pending recommendations
              </div>
            ) : (
              topRecommendations.map((rec) => (
                <RecommendationCard
                  key={rec.id}
                  recommendation={rec}
                  showActions={false}
                  className="!shadow-none border"
                />
              ))
            )}
          </CardContent>
        </Card>
      </div>

      {/* Bottom row: Objectives + Events */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        {/* Operating objectives */}
        <Card className="xl:col-span-2">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Operating Objectives</CardTitle>
          </CardHeader>
          <CardContent>
            {objectives.length === 0 ? (
              <div className="text-center py-6 text-slate-400 text-sm">
                No objectives configured
              </div>
            ) : (
              <div className="space-y-3">
                {objectives.slice(0, 6).map((obj) => {
                  const pct = Math.min(
                    100,
                    (obj.current_value / Math.max(obj.target_value, 0.001)) * 100
                  )
                  const progressColor =
                    pct >= 80 ? 'bg-green-500' : pct >= 50 ? 'bg-amber-400' : 'bg-red-500'

                  return (
                    <div key={obj.id}>
                      <div className="flex items-center justify-between mb-1">
                        <div className="flex items-center gap-2">
                          <span className="text-sm text-slate-700 font-medium">{obj.name}</span>
                          <span className={`text-xs ${trendColor(obj.trend)}`}>
                            {trendIcon(obj.trend)}
                          </span>
                        </div>
                        <span className="text-xs text-slate-500">
                          {formatValue(obj.current_value, obj.unit, 1)} /{' '}
                          {formatValue(obj.target_value, obj.unit, 1)}
                        </span>
                      </div>
                      <Progress
                        value={pct}
                        className="h-2"
                        indicatorClassName={progressColor}
                      />
                    </div>
                  )
                })}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Recent events */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Recent Events</CardTitle>
          </CardHeader>
          <CardContent className="pt-0 p-0">
            <EventFeed events={events} maxItems={5} compact className="border-0 rounded-none" />
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
