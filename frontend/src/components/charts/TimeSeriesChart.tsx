import React, { useMemo } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  ReferenceLine,
} from 'recharts'
import type { TimeSeriesPoint } from '@/types'

interface Series {
  name: string
  data: TimeSeriesPoint[]
  unit: string
  color?: string
  showConfidence?: boolean
  yAxis?: 'y' | 'y2'
}

interface TimeSeriesChartProps {
  series: Series[]
  title?: string
  height?: number
  showRangeSelector?: boolean
  thresholds?: Array<{ value: number; label: string; color: string; yAxis?: 'y' | 'y2' }>
}

const DEFAULT_COLORS = ['#0891B2', '#16A34A', '#D97706', '#DC2626', '#7C3AED', '#EC4899']

function formatTimestamp(ts: string): string {
  try {
    const d = new Date(ts)
    return d.toLocaleString('en-GB', {
      month: 'short', day: '2-digit',
      hour: '2-digit', minute: '2-digit',
      hour12: false,
    })
  } catch {
    return ts
  }
}

export const TimeSeriesChart: React.FC<TimeSeriesChartProps> = ({
  series,
  height = 350,
  thresholds = [],
}) => {
  const isEmpty = !series.length || series.every((s) => !s.data.length)

  // Merge all series into a single dataset keyed by timestamp
  const chartData = useMemo(() => {
    if (isEmpty) return []
    // Use the first series timestamps as the x-axis spine
    return series[0].data.map((point, i) => {
      const row: Record<string, unknown> = { timestamp: point.timestamp }
      series.forEach((s) => {
        row[s.name] = s.data[i]?.value ?? null
      })
      return row
    })
  }, [series, isEmpty])

  if (isEmpty) {
    return (
      <div
        className="flex items-center justify-center text-slate-400 text-sm"
        style={{ height }}
      >
        No data available
      </div>
    )
  }

  const unit = series[0]?.unit ?? ''

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={chartData} margin={{ top: 8, right: 24, bottom: 8, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
        <XAxis
          dataKey="timestamp"
          tickFormatter={formatTimestamp}
          tick={{ fontSize: 10, fill: '#64748B' }}
          tickLine={false}
          interval="preserveStartEnd"
          minTickGap={60}
        />
        <YAxis
          tick={{ fontSize: 10, fill: '#64748B' }}
          tickLine={false}
          unit={unit ? ` ${unit}` : ''}
          width={55}
        />
        <Tooltip
          contentStyle={{ fontSize: '12px', border: '1px solid #E2E8F0', borderRadius: '6px' }}
          formatter={(value: number, name: string) => [`${value?.toFixed(3)} ${unit}`, name]}
          labelFormatter={(label: string) => formatTimestamp(label)}
        />
        <Legend wrapperStyle={{ fontSize: '12px' }} />
        {thresholds.map((t) => (
          <ReferenceLine
            key={t.label}
            y={t.value}
            stroke={t.color}
            strokeDasharray="4 2"
            label={{ value: t.label, fontSize: 10, fill: t.color }}
          />
        ))}
        {series.map((s, i) => (
          <Line
            key={s.name}
            type="monotone"
            dataKey={s.name}
            stroke={s.color ?? DEFAULT_COLORS[i % DEFAULT_COLORS.length]}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
            connectNulls={false}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}
