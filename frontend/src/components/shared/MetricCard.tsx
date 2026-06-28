import React from 'react'
import { TrendingUp, TrendingDown, Minus } from 'lucide-react'
import { cn, formatValue, statusBg, confidenceBg } from '@/lib/utils'
import { Card, CardContent } from '@/components/ui/card'
interface MetricCardProps {
  title: string
  value: number | null
  unit: string
  trend?: 'up' | 'down' | 'stable'
  trendPositive?: boolean
  confidence?: number
  status?: 'good' | 'warning' | 'critical' | 'unknown'
  threshold?: { critical: number; warning: number; good: number }
  invertThreshold?: boolean
  sparklineData?: number[]
  precision?: number
  subtitle?: string
  className?: string
  onClick?: () => void
}

const STATUS_MAP: Record<string, string> = {
  good: 'healthy',
  warning: 'warning',
  critical: 'critical',
  unknown: 'unknown',
}

function deriveStatus(
  value: number | null,
  threshold?: { critical: number; warning: number; good: number },
  invert?: boolean
): 'good' | 'warning' | 'critical' | undefined {
  if (!threshold || value === null) return undefined
  const v = invert ? -value : value
  const t = invert
    ? { critical: -threshold.critical, warning: -threshold.warning, good: -threshold.good }
    : threshold
  if (v <= t.critical) return 'critical'
  if (v <= t.warning) return 'warning'
  return 'good'
}

export const MetricCard: React.FC<MetricCardProps> = ({
  title,
  value,
  unit,
  trend,
  trendPositive = true,
  confidence,
  status: statusProp,
  threshold,
  invertThreshold,
  sparklineData,
  precision = 2,
  subtitle,
  className,
  onClick,
}) => {
  const status = statusProp ?? deriveStatus(value, threshold, invertThreshold)
  const TrendIcon =
    trend === 'up' ? TrendingUp : trend === 'down' ? TrendingDown : Minus

  const trendColor =
    trend === 'stable'
      ? 'text-slate-500'
      : trendPositive
        ? trend === 'up'
          ? 'text-green-600'
          : 'text-red-600'
        : trend === 'up'
          ? 'text-red-600'
          : 'text-green-600'

  return (
    <Card
      className={cn(
        'relative overflow-hidden transition-shadow',
        onClick && 'cursor-pointer hover:shadow-md',
        className
      )}
      onClick={onClick}
    >
      <CardContent className="p-4">
        <div className="flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wide truncate">
              {title}
            </p>
            <div className="flex items-baseline gap-1.5 mt-1">
              <span className="text-2xl font-bold text-slate-900 tabular-nums">
                {formatValue(value, '', precision)}
              </span>
              {value !== null && (
                <span className="text-sm text-slate-500">{unit}</span>
              )}
            </div>
            {subtitle && (
              <p className="text-xs text-slate-400 mt-0.5">{subtitle}</p>
            )}
          </div>

          <div className="flex flex-col items-end gap-1 ml-2 shrink-0">
            {trend && (
              <TrendIcon className={cn('h-4 w-4', trendColor)} />
            )}
            {status && (
              <span
                className={cn(
                  'text-xs font-medium px-1.5 py-0.5 rounded-full',
                  statusBg(STATUS_MAP[status] ?? status)
                )}
              >
                {status}
              </span>
            )}
            {confidence !== undefined && (
              <span
                className={cn(
                  'text-xs px-1.5 py-0.5 rounded-full',
                  confidenceBg(confidence)
                )}
              >
                {Math.round(confidence * 100)}%
              </span>
            )}
          </div>
        </div>

        {sparklineData && sparklineData.length > 1 && (
          <div className="mt-3 h-10">
            <SparklineChart data={sparklineData} color={
              status === 'critical' ? '#DC2626'
              : status === 'warning' ? '#D97706'
              : '#0891B2'
            } />
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// Internal sparkline — lightweight Recharts line
import { LineChart, Line, ResponsiveContainer } from 'recharts'

export const SparklineChart: React.FC<{ data: number[]; color?: string }> = ({
  data,
  color = '#0891B2',
}) => {
  const chartData = data.map((v, i) => ({ i, v }))
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={chartData} margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
        <Line
          type="monotone"
          dataKey="v"
          stroke={color}
          strokeWidth={1.5}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
